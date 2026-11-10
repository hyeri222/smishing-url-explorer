"""단축 URL 풀기: 응답 헤더(Location)만 따라가고 페이지 본문은 받지도 실행하지도 않는다."""
import asyncio
import ipaddress
import socket
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

import httpx

from .normalize import normalize

MAX_HOPS = 5
ALLOWED_PORTS = {80, 443}
REDIRECT_CODES = {301, 302, 303, 307, 308}
UA = 'Mozilla/5.0 (Linux; Android 14) SmishingURLExplorer/0.1 (+redirect check only)'


@dataclass
class TraceResult:
    final_url: str
    chain: list[str] = field(default_factory=list)  # 지나온 주소(처음 포함, 최종 포함)
    status: str = 'ok'  # ok | timeout | blocked | error | too_many
    detail: str = ''
    http_status: int | None = None  # 마지막 주소의 응답 코드(더 이동하지 않을 때). 404·410 = 없는 주소

    @property
    def hops(self) -> int:
        return max(0, len(self.chain) - 1)


async def _is_public(host: str, port: int) -> bool:
    """호스트가 가리키는 모든 IP가 공인 주소인지 확인(내부망 공격 방지)."""
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_global
    except ValueError:
        pass
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    ips = {ipaddress.ip_address(i[4][0]) for i in infos}
    return bool(ips) and all(ip.is_global for ip in ips)


async def trace(url: str, budget: float = 1.5, client: httpx.AsyncClient | None = None,
                check_ip=_is_public) -> TraceResult:
    """url에서 시작해 리다이렉트를 최대 MAX_HOPS번 따라간다. 전체 시간은 budget초."""
    deadline = time.monotonic() + budget
    own = client is None
    client = client or httpx.AsyncClient(follow_redirects=False, headers={'User-Agent': UA})
    res = TraceResult(final_url=url, chain=[url])
    try:
        cur = url
        for _ in range(MAX_HOPS + 1):
            left = deadline - time.monotonic()
            if left <= 0:
                res.status = 'timeout'
                return res
            p = urlsplit(cur)
            port = p.port or (443 if p.scheme == 'https' else 80)
            if p.scheme not in ('http', 'https') or port not in ALLOWED_PORTS:
                res.status, res.detail = 'blocked', '허용되지 않는 스킴·포트'
                return res
            if not await asyncio.wait_for(check_ip(p.hostname, port), timeout=left):
                res.status, res.detail = 'blocked', '내부망 주소'
                return res
            loc, code = await asyncio.wait_for(_location(client, cur), timeout=max(0.05, deadline - time.monotonic()))
            if loc is None:
                res.http_status = code
                return res  # 더 이동하지 않음 → 지금 주소가 최종
            nxt = normalize(urljoin(cur, loc))
            if nxt in res.chain:
                return res  # 순환
            res.chain.append(nxt)
            res.final_url = cur = nxt
        res.status = 'too_many'
        return res
    except asyncio.TimeoutError:
        res.status = 'timeout'
        return res
    except (httpx.HTTPError, OSError, ValueError) as e:
        res.status, res.detail = 'error', type(e).__name__
        return res
    finally:
        if own:
            await client.aclose()


async def _location(client: httpx.AsyncClient, url: str) -> tuple[str | None, int]:
    """(이동할 주소, 응답 코드). HEAD로 물어보고, 서버가 HEAD를 거부하면 GET을 보내되 본문은 읽지 않고 바로 닫는다."""
    r = await client.head(url)
    if r.status_code in REDIRECT_CODES:
        return r.headers.get('location'), r.status_code
    if r.status_code in (403, 405, 400, 501):
        async with client.stream('GET', url) as s:  # 헤더만 확인, 본문 미수신
            if s.status_code in REDIRECT_CODES:
                return s.headers.get('location'), s.status_code
            return None, s.status_code
    return None, r.status_code
