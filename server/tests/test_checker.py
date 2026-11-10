import asyncio

import pytest

from app import rules
from app.checker import Checker, calibrate, grade
from app.domaininfo import DomainInfo
from app.lists import Lists
from app.normalize import extract_urls, normalize, registered_domain
from app.unshorten import TraceResult


class FakeScorer:
    def __init__(self, p=None):
        self.p, self.ready, self.model_id, self.error = p, p is not None, 'fake', ''
        self.caution_p = 0.05

    def predict(self, url):
        return self.p


def make_lists(white=(), black_dom=(), black_url=(), popular=()):
    ls = Lists.__new__(Lists)
    ls.popular = set(popular)
    ls.whitelist = set(white)
    ls.black_domains = set(black_dom)
    ls.black_urls = {Lists._key(u) for u in black_url}
    return ls


def fake_trace(result):
    async def _t(url, **kw):
        return result
    return _t


def C(*a, info=None, **kw):
    """시험에서는 실제 DNS·RDAP 조회를 하지 않는다."""
    async def _d(host, **kw):
        return info or DomainInfo()
    return Checker(*a, domain_fn=_d, **kw)


def run(c, url):
    return asyncio.run(c.check(url))


# --- 정규화 ---
def test_normalize_adds_scheme_and_lowercases():
    assert normalize('CJ-Delivery.TOP/Kr/') == 'http://cj-delivery.top/Kr'


def test_normalize_rejects_other_schemes():
    with pytest.raises(ValueError):
        normalize('javascript:alert(1)')


def test_extract_urls_from_sms():
    sms = '[CJ대한통운] 주소지 불일치로 보관 중. 확인 bit.ly/3xYzAb 감사합니다.'
    assert extract_urls(sms) == ['bit.ly/3xYzAb']


def test_registered_domain_kr():
    assert registered_domain('www.nhis.or.kr') == 'nhis.or.kr'


# --- 규칙 ---
def codes(url, hops=0):
    return {r.code for r in rules.find_reasons(normalize(url), hops)}


def test_brand_lookalike_with_digit():
    assert 'brand_similar' in codes('cj-1ogistics.top/kr') or 'brand_in_domain' in codes('cj-1ogistics.top/kr')
    assert 'risky_tld' in codes('cj-1ogistics.top/kr')


def test_official_domain_has_no_brand_reason():
    assert not codes('https://www.cjlogistics.com/ko/tool/parcel/tracking') & {'brand_similar', 'brand_in_domain'}


def test_ip_and_port():
    c = codes('http://115.49.27.218:43869/bin.sh')
    assert {'ip_host', 'odd_port'} <= c


def test_shortener_reason():
    assert 'shortener' in codes('han.gl/abc')
    assert 'redirect' in codes('example.top/x', hops=2)


# --- 판정 흐름 ---
def test_grade_bounds():
    assert (grade(39), grade(40), grade(69), grade(70)) == ('safe', 'caution', 'caution', 'danger')


def test_whitelist_is_safe():
    c = C(make_lists(white={'cjlogistics.com'}), FakeScorer(0.99))
    r = run(c, 'https://www.cjlogistics.com/ko/tool/parcel/tracking')
    assert (r['verdict'], r['source']) == ('safe', 'whitelist')


def test_go_kr_suffix_whitelist():
    c = C(make_lists(white={'.go.kr'}), FakeScorer(0.99))
    assert run(c, 'https://www.epost.go.kr/main.retrieveMainPage.comm')['verdict'] == 'safe'


def test_blacklisted_short_url_is_danger_without_trace():
    called = []

    async def t(url, **kw):
        called.append(url)
        return TraceResult(final_url=url)
    c = C(make_lists(black_url={'buly.kr/AbC'}), FakeScorer(0.1), trace_fn=t)
    r = run(c, 'https://buly.kr/AbC')
    assert r['verdict'] == 'danger' and r['source'] == 'blacklist' and not called


def test_short_url_resolved_then_model():
    tr = TraceResult(final_url='http://cj-1ogistics.top/kr',
                     chain=['http://bit.ly/x', 'http://short-rd.xyz/r', 'http://cj-1ogistics.top/kr'])
    c = C(make_lists(), FakeScorer(0.87), trace_fn=fake_trace(tr))
    r = run(c, 'bit.ly/x')
    assert r['verdict'] == 'danger' and r['score'] == calibrate(0.87) and r['source'] == 'canine'
    assert r['final_url'] == 'http://cj-1ogistics.top/kr'
    assert any(x['code'] == 'redirect' for x in r['reasons'])


def test_short_url_timeout_is_unknown():
    tr = TraceResult(final_url='http://bit.ly/x', chain=['http://bit.ly/x'], status='timeout')
    c = C(make_lists(), FakeScorer(0.01), trace_fn=fake_trace(tr))
    r = run(c, 'bit.ly/x')
    assert r['verdict'] == 'unknown' and r['score'] is None


def test_short_url_to_official_is_safe():
    tr = TraceResult(final_url='https://www.coupang.com/vp/products/1',
                     chain=['https://naver.me/abc', 'https://www.coupang.com/vp/products/1'])
    c = C(make_lists(white={'coupang.com'}), FakeScorer(0.9), trace_fn=fake_trace(tr))
    assert run(c, 'https://naver.me/abc')['verdict'] == 'safe'


def test_fallback_without_model():
    c = C(make_lists(), FakeScorer(None))
    r = run(c, 'http://cj-1ogistics.top/login')
    assert r['source'] == 'rules_fallback' and r['verdict'] in ('caution', 'danger')


def test_cache_returns_same_result():
    c = C(make_lists(), FakeScorer(0.2))
    a = run(c, 'example.org/a')
    c.scorer.p = 0.9
    assert run(c, 'example.org/a') == a


# --- 학습 후 보정(11.05) ---
def test_calibrate_boundaries():
    assert calibrate(0.0) == 0 and calibrate(0.049) <= 39
    assert calibrate(0.05) == 40 and calibrate(0.49) <= 69
    assert calibrate(0.5) == 70 and calibrate(1.0) == 100


def test_official_wins_over_blacklist():
    # KISA 원본에 공식 주소가 섞여 들어가도 공식 목록이 우선
    c = C(make_lists(white={'nhis.or.kr'}, black_url={'nhis.or.kr'}), FakeScorer(0.9))
    assert run(c, 'https://www.nhis.or.kr')['verdict'] == 'safe'


def test_rule_floor_lifts_brand_impersonation():
    # AI가 낮게 봐도 브랜드 사칭 + 위험 TLD면 '위험'
    c = C(make_lists(), FakeScorer(0.01))
    r = run(c, 'http://naver-security-alert.top/auth')
    assert r['verdict'] == 'danger' and r['source'] == 'canine+rules'
    # 브랜드 사칭만 있으면 '주의'
    r2 = run(c, 'http://naver-event.com/a')
    assert r2['verdict'] == 'caution'


def test_popular_domain_capped_to_caution():
    c = C(make_lists(popular={'yes24.com'}), FakeScorer(0.9))
    r = run(c, 'https://www.yes24.com/Product/Goods/12345')
    assert r['verdict'] == 'caution' and any(x['code'] == 'popular' for x in r['reasons'])


def test_popular_does_not_override_blacklist():
    c = C(make_lists(popular={'example.com'}, black_url={'example.com/phish'}), FakeScorer(0.0))
    assert run(c, 'https://example.com/phish')['verdict'] == 'danger'

# --- 주소 정보(11.06): 없는 주소, 새로 만든 주소 ---
def test_nonexistent_domain_is_caution():
    c = C(make_lists(), FakeScorer(0.01), info=DomainInfo(exists=False))
    r = run(c, 'https://haru-deliv.kr/t/88231')
    assert r['verdict'] == 'caution' and any(x['code'] == 'no_dns' for x in r['reasons'])


def test_new_domain_is_caution_and_with_risky_signal_danger():
    c = C(make_lists(), FakeScorer(0.01), info=DomainInfo(exists=True, age_days=3))
    r = run(c, 'https://some-shop.com/item')
    assert r['verdict'] == 'caution' and any(x['code'] == 'new_domain' for x in r['reasons'])
    r2 = run(c, 'http://some-parcel.top/delivery')
    assert r2['verdict'] == 'danger'


def test_old_domain_unchanged():
    c = C(make_lists(), FakeScorer(0.01), info=DomainInfo(exists=True, age_days=4000))
    assert run(c, 'https://www.musinsa.com/products/1')['verdict'] == 'safe'


def test_unknown_domain_info_does_not_raise_score():
    c = C(make_lists(), FakeScorer(0.01))
    assert run(c, 'https://example.org/a')['verdict'] == 'safe'


def test_popular_domain_skips_lookup():
    called = []

    async def d(host, **kw):
        called.append(host)
        return DomainInfo(exists=False)
    c = Checker(make_lists(popular={'yes24.com'}), FakeScorer(0.01), domain_fn=d)
    assert run(c, 'https://www.yes24.com/a')['verdict'] == 'safe' and not called


def test_short_url_partial_trace_uses_known_destination():
    # 목적지(youtube)까지 찾은 뒤 그 사이트의 추가 이동에서 시간이 넘은 경우 → 알아낸 목적지로 판정
    tr = TraceResult(final_url='https://m.youtube.com/watch?v=x',
                     chain=['https://bit.ly/youtube', 'http://www.youtube.com/watch?v=x', 'https://m.youtube.com/watch?v=x'],
                     status='timeout')
    c = C(make_lists(), FakeScorer(0.01), trace_fn=fake_trace(tr))
    r = run(c, 'https://bit.ly/youtube')
    assert r['verdict'] == 'safe' and r['final_url'].startswith('https://m.youtube.com')
    assert any(x['code'] == 'trace_partial' for x in r['reasons'])
