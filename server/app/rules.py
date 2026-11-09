"""판정 이유를 찾는 규칙. 점수에는 관여하지 않고 '왜 위험해 보이는지' 문장만 만든다."""
import ipaddress
import re
from dataclasses import dataclass, asdict
from urllib.parse import urlsplit

from .normalize import host_of, registered_domain

# 사칭이 잦은 브랜드: 이름 조각 → (화면에 보일 이름, 공식 도메인들)
BRANDS = {
    'cjlogistics': ('CJ대한통운', {'cjlogistics.com'}),
    'hanjin': ('한진택배', {'hanjin.com', 'hanjin.co.kr'}),
    'lotteglogis': ('롯데택배', {'lotteglogis.com'}),
    'epost': ('우체국', {'epost.go.kr', 'koreapost.go.kr'}),
    'naver': ('네이버', {'naver.com', 'naver.me'}),
    'kakao': ('카카오', {'kakao.com', 'kakaocorp.com', 'kakaobank.com', 'kakaopay.com'}),
    'coupang': ('쿠팡', {'coupang.com'}),
    'kbstar': ('KB국민은행', {'kbstar.com'}),
    'shinhan': ('신한', {'shinhan.com', 'shinhancard.com'}),
    'wooribank': ('우리은행', {'wooribank.com'}),
    'hanabank': ('하나은행', {'hanabank.com'}),
    'nonghyup': ('농협', {'nonghyup.com', 'nhbank.com'}),
    'samsungcard': ('삼성카드', {'samsungcard.com'}),
    'hyundaicard': ('현대카드', {'hyundaicard.com'}),
    'lottecard': ('롯데카드', {'lottecard.co.kr'}),
    'nhis': ('국민건강보험', {'nhis.or.kr'}),
    'police': ('경찰청', {'police.go.kr'}),
    'tossbank': ('토스뱅크', {'tossbank.com', 'toss.im'}),
    'hometax': ('국세청 홈택스', {'hometax.go.kr', 'nts.go.kr'}),
}
# 이름 자체가 짧아 편집 거리로 비교하면 오탐이 많은 브랜드는 '포함'만 본다
SHORT_BRANDS = {'cj': 'CJ대한통운', 'post': '우체국', 'nh': '농협', 'kb': 'KB국민은행', 'toss': '토스', 'nts': '국세청'}

RISKY_TLDS = {
    'top', 'xyz', 'icu', 'buzz', 'cyou', 'sbs', 'cfd', 'click', 'link', 'live', 'shop', 'store',
    'online', 'site', 'club', 'vip', 'work', 'rest', 'bond', 'yachts', 'one', 'wtf', 'hair',
    'golf', 'uno', 'monster', 'lol', 'pro', 'win', 'loan', 'cc', 'tk', 'ml', 'ga', 'cf', 'gq',
}

SHORTENERS = {
    'bit.ly', 'han.gl', 't.ly', 'buly.kr', 'go9.co', 'nal.la', 'u2.to', 'alie.kr', 'xgo.kr',
    'gourl.kr', 'me2.kr', 'tuney.kr', 'c11.kr', 'gg.gg', 'naver.me', 'swyg.link', 'zxcv.be',
    'me2.do', 'orl.kr', 'tinyurl.com', 'vo.la', 'url.kr', 't.co', 'goo.gl', 'is.gd', 'cutt.ly',
    'rebrand.ly', 'shorturl.at', 'ow.ly', 'buff.ly', 'vvd.bz', 'abit.ly', 'abr.ge', 'muz.so',
}

SUSPICIOUS_WORDS = ('login', 'signin', 'verify', 'secure', 'account', 'update', 'delivery',
                    'parcel', 'track', 'confirm', 'auth', 'wallet', 'refund', 'apk')


@dataclass
class Reason:
    code: str
    text: str
    level: str  # 'danger' | 'warn' | 'info'


def _lev(a: str, b: str, limit: int = 2) -> int:
    """편집 거리(limit 넘으면 limit+1 반환)."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        best = cur[0]
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            best = min(best, cur[j])
        if best > limit:
            return limit + 1
        prev = cur
    return prev[-1]


# 숫자·기호로 글자를 흉내 내는 경우(de1ivery, nav3r)
_LEET = str.maketrans({'0': 'o', '1': 'l', '3': 'e', '4': 'a', '5': 's', '7': 't', '@': 'a', '$': 's'})


def is_shortener(host: str) -> bool:
    return host in SHORTENERS or registered_domain(host) in SHORTENERS


def find_reasons(url: str, hops: int = 0) -> list[Reason]:
    host = host_of(url)
    reg = registered_domain(host)
    tld = host.rsplit('.', 1)[-1]
    out: list[Reason] = []

    # 1) IP 주소
    try:
        ipaddress.ip_address(host)
        out.append(Reason('ip_host', '이름 대신 숫자(IP) 주소를 사용', 'danger'))
    except ValueError:
        pass

    # 2) 브랜드 사칭
    labels = [t for t in re.split(r'[.\-_]', host) if t]
    brand_hit = None
    for brand, (name, officials) in BRANDS.items():
        if reg in officials:
            continue  # 이 브랜드의 공식 도메인
        for t in labels:
            t2 = t.translate(_LEET)
            if t == brand or t2 == brand or brand in t2:
                brand_hit = (name, t, 'contains')
            elif len(brand) >= 5 and _lev(t2, brand, 2) <= 2:
                brand_hit = (name, t, 'similar')
            if brand_hit:
                break
        if brand_hit:
            break
    if not brand_hit:
        for t in labels:
            if t in SHORT_BRANDS and len(labels) > 2:
                brand_hit = (SHORT_BRANDS[t], t, 'contains')
                break
    if brand_hit:
        name, token, kind = brand_hit
        if kind == 'similar':
            out.append(Reason('brand_similar', f'{name} 주소를 흉내 낸 가짜 주소 ({token})', 'danger'))
        else:
            out.append(Reason('brand_in_domain', f'{name} 이름을 넣었지만 공식 주소가 아님 ({token})', 'danger'))

    # 3) 위험 TLD
    if tld in RISKY_TLDS:
        out.append(Reason('risky_tld', f'스미싱에 자주 쓰이는 주소 끝 (.{tld})', 'warn'))

    # 4) 퓨니코드(한글·유사 문자 도메인)
    if 'xn--' in host:
        out.append(Reason('punycode', '다른 글자처럼 보이게 만든 주소(퓨니코드)', 'warn'))

    # 5) 단축 URL 경유
    if hops > 0:
        out.append(Reason('redirect', f'단축 URL로 진짜 주소를 숨김 ({hops}회 이동)', 'warn'))
    elif is_shortener(host):
        out.append(Reason('shortener', '단축 URL이라 실제 목적지를 알 수 없음', 'warn'))

    # 6) 의심 단어
    low = url.lower()
    words = [w for w in SUSPICIOUS_WORDS if w in low]
    if words:
        out.append(Reason('suspicious_word', f'로그인·배송 확인 등을 유도하는 단어 포함 ({words[0]})', 'info'))

    # 7) 하이픈·숫자 과다
    if host.count('-') >= 3 or sum(c.isdigit() for c in host) >= 6:
        out.append(Reason('messy_host', '하이픈이나 숫자가 많은 복잡한 주소', 'info'))

    # 8) 비표준 포트
    port = urlsplit(url).port
    if port and port not in (80, 443):
        out.append(Reason('odd_port', f'특이한 포트 번호 사용 (:{port})', 'warn'))

    return out


def as_dicts(reasons: list[Reason]) -> list[dict]:
    return [asdict(r) for r in reasons]
