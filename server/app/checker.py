"""판정 흐름: 정규화 → 공식 목록 → 피싱 목록 → (단축 URL이면) 풀기 → CANINE 점수 + 주소 정보 + 규칙 보정 → 이유."""
import asyncio
import ipaddress
import time
from collections import OrderedDict

from . import rules
from .lists import Lists
from .domaininfo import NEW_DAYS, DomainInfo, lookup
from .model import CanineScorer
from .normalize import host_of, normalize
from .unshorten import trace

SAFE_MAX, CAUTION_MAX = 39, 69  # 0~39 안전, 40~69 주의, 70~100 위험


def grade(score: int) -> str:
    return 'safe' if score <= SAFE_MAX else 'caution' if score <= CAUTION_MAX else 'danger'


def calibrate(p: float, caution_p: float = 0.05, danger_p: float = 0.5) -> int:
    """모델 확률 → 0~100점. 학습 결과로 정한 두 기준점이 화면의 구간 경계에 오도록 환산한다.
    p < caution_p → 0~39(안전), caution_p ≤ p < danger_p → 40~69(주의), p ≥ danger_p → 70~100(위험)
    (caution_p는 검증셋에서 오탐률 5% 이하로 재현율이 가장 높은 값. 학습 결과 threshold.json)"""
    if p >= danger_p:
        s = 70 + (p - danger_p) / (1 - danger_p) * 30
    elif p >= caution_p:
        s = 40 + (p - caution_p) / (danger_p - caution_p) * 29
    else:
        s = p / caution_p * 39
    return max(0, min(100, round(s)))


def rule_floor(reasons: list[rules.Reason]) -> int:
    """규칙이 찾은 확실한 위험 신호가 있으면 점수의 바닥을 올린다.
    학습 데이터(KISA 2023~2024)에는 브랜드 사칭 주소가 드물어 AI가 약한 부분을 보완한다."""
    codes = {r.code for r in reasons}
    strong = codes & {'brand_similar', 'brand_in_domain', 'ip_host'}
    extra = codes & {'risky_tld', 'punycode', 'odd_port', 'redirect', 'suspicious_word'}
    if strong:
        # 다른 신호(새 주소·없는 주소 포함)가 겹치면 '위험', 아니면 '주의'
        return 75 if extra or codes & {'new_domain', 'no_dns'} else 45
    if 'new_domain' in codes:
        return 75 if extra else 45  # 만든 지 얼마 안 된 주소 + 위험 신호 → '위험'
    if 'no_dns' in codes:
        return 45  # 없는 주소: 열려도 당장 피해는 없지만 정상 문자에 올 주소는 아님 → '주의'
    return 0


def domain_reasons(info: DomainInfo) -> list[rules.Reason]:
    if info.exists is False:
        return [rules.Reason('no_dns', '인터넷에 등록되지 않은 주소 — 이미 막혔거나 가짜 주소일 수 있음', 'warn')]
    if info.age_days is not None and info.age_days < NEW_DAYS:
        when = '오늘' if info.age_days == 0 else f'{info.age_days}일 전'
        return [rules.Reason('new_domain', f'{when} 새로 만든 주소 (스미싱 주소는 대부분 만든 지 얼마 안 됨)', 'warn')]
    return []


def _fallback_score(reasons: list[rules.Reason]) -> int:
    """모델이 없을 때(개발용)만 쓰는 임시 점수."""
    w = {'danger': 40, 'warn': 15, 'info': 5}
    return min(100, sum(w[r.level] for r in reasons))


class Checker:
    def __init__(self, lists: Lists | None = None, scorer: CanineScorer | None = None,
                 trace_fn=trace, domain_fn=lookup, cache_size: int = 2000, cache_ttl: float = 3600):
        self.lists = lists or Lists()
        self.scorer = scorer or CanineScorer()
        self.trace = trace_fn
        self.domain = domain_fn
        self._cache: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self._cache_size, self._ttl = cache_size, cache_ttl

    async def check(self, raw: str) -> dict:
        url = normalize(raw)  # ValueError는 호출한 쪽에서 400 처리
        hit = self._cache.get(url)
        if hit and time.monotonic() - hit[0] < self._ttl:
            self._cache.move_to_end(url)
            return hit[1]
        result = await self._check(url)
        if result['verdict'] != 'unknown':  # 판단 불가는 다음에 다시 시도
            self._cache[url] = (time.monotonic(), result)
            if len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        return result

    def _official(self, base):
        return self._out(base, 'safe', 0, 'whitelist', [], extra=rules.Reason('official', '공식 기관·기업 주소', 'info'))

    def _phish(self, base, reasons):
        return self._out(base, 'danger', 100, 'blacklist', reasons,
                         extra=rules.Reason('blacklist', '이미 신고된 피싱 주소 (KISA·PhishTank)', 'danger'))

    async def _check(self, url: str) -> dict:
        base = {'input': url, 'final_url': url, 'chain': [url]}
        short = rules.is_shortener(host_of(url))

        # 1) 공식 도메인(단축 URL 서비스는 제외 — 풀어서 최종 주소로 판단)
        if not short and self.lists.is_official(url):
            return self._official(base)

        # 2) 원래 주소가 이미 알려진 피싱(단축 URL 자체가 목록에 있는 경우 포함)
        if self.lists.is_known_phish(url):
            return self._phish(base, rules.find_reasons(url))

        # 3) 단축 URL이면 최종 주소까지 따라감
        hops = 0
        if short:
            t = await self.trace(url)
            base.update(final_url=t.final_url, chain=t.chain)
            hops = t.hops
            if t.status != 'ok' or rules.is_shortener(host_of(t.final_url)):
                why = t.status if t.status != 'ok' else 'unresolved'
                return self._out(base, 'unknown', None, f'trace_{why}', rules.find_reasons(url),
                                 extra=rules.Reason('unresolved', '실제 목적지를 확인하지 못함 — 누르지 마세요', 'danger'))
            final = base['final_url']
            if self.lists.is_official(final):
                return self._official(base)
            if self.lists.is_known_phish(final):
                return self._phish(base, rules.find_reasons(final, hops))

        final = base['final_url']
        reasons = rules.find_reasons(final, hops)

        # 4) CANINE 점수 + 주소 정보(있는지·며칠 됐는지) + 규칙 보정. 모델 계산과 주소 조회를 동시에 한다
        host = host_of(final)
        popular = self.lists.is_popular(final)
        p, info = await asyncio.gather(asyncio.to_thread(self.scorer.predict, final),
                                       self._domain_info(host, popular, budget=0.6 if hops else 0.9))
        reasons += domain_reasons(info)
        if p is None:
            return self._out(base, grade(_fallback_score(reasons)), _fallback_score(reasons), 'rules_fallback', reasons)

        score = calibrate(p, self.scorer.caution_p)
        source = 'canine'
        floor = rule_floor(reasons)
        if floor > score:
            score, source = floor, 'canine+rules'
        if popular and score > CAUTION_MAX:
            # 널리 쓰이는 사이트(Tranco 상위 10만)는 AI 점수가 높아도 '주의'까지만(오탐 방지). 피싱 목록에 있으면 위에서 이미 '위험'
            score = CAUTION_MAX
            reasons.append(rules.Reason('popular', '널리 쓰이는 사이트 주소라 경고 대신 주의로 낮춤', 'info'))
        return self._out(base, grade(score), score, source, reasons)

    async def _domain_info(self, host: str, popular: bool, budget: float) -> DomainInfo:
        # 널리 쓰이는 사이트는 오래된 주소라 조회하지 않음. IP 주소는 등록일이 없음
        if popular or not self.domain:
            return DomainInfo()
        try:
            ipaddress.ip_address(host)
            return DomainInfo()
        except ValueError:
            pass
        try:
            return await self.domain(host, budget=budget)  # 단축 URL을 푸느라 시간을 쓴 경우 더 짧게
        except Exception:
            return DomainInfo()

    @staticmethod
    def _out(base, verdict, score, source, reasons, extra=None) -> dict:
        rs = ([extra] if extra else []) + reasons
        return {**base, 'verdict': verdict, 'score': score, 'source': source, 'reasons': rules.as_dicts(rs)}
