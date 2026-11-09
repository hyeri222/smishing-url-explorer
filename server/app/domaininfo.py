"""주소가 실제로 있는지(DNS)와 만든 지 며칠 됐는지(RDAP 등록일)를 알아본다.
스미싱 주소는 며칠 전에 만들었다가 금방 사라지는 경우가 많아서, AI가 놓친 것을 보완한다.
페이지는 열지 않는다: DNS 조회와 등록 기관(RDAP)의 공개 정보만 본다.
시간 안에 답이 없으면 '모름'으로 두고 판정에 반영하지 않는다(그것 때문에 위험으로 몰지 않음)."""
import asyncio
import json
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .normalize import registered_domain

# IANA 목록(https://data.iana.org/rdap/dns.json)을 저장해 둔 것: 주소 끝(TLD) → 등록 기관 RDAP 서버
_SERVERS: dict[str, str] = json.loads((Path(__file__).parent.parent / 'data' / 'rdap_servers.json').read_text())
NEW_DAYS = 30          # 이보다 최근에 만든 주소는 '새 주소'
CACHE_TTL = 6 * 3600


@dataclass
class DomainInfo:
    exists: bool | None = None    # None = 확인 못 함
    age_days: int | None = None   # None = 확인 못 함


_cache: dict[str, tuple[float, DomainInfo]] = {}


async def _dns_exists(host: str) -> bool | None:
    try:
        await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        return True
    except socket.gaierror as e:
        # '그런 이름 없음'만 없다고 본다. 일시적 오류(EAI_AGAIN 등)는 모름
        no_name = {getattr(socket, n) for n in ('EAI_NONAME', 'EAI_NODATA') if hasattr(socket, n)} | {11001}
        return False if e.errno in no_name else None
    except Exception:
        return None


def _registered(j: dict) -> datetime | None:
    for e in j.get('events', []):
        if e.get('eventAction') == 'registration':
            try:
                return datetime.fromisoformat(e['eventDate'].replace('Z', '+00:00'))
            except (KeyError, ValueError):
                return None
    return None


async def _age_days(domain: str, client: httpx.AsyncClient) -> int | None:
    base = _SERVERS.get(domain.rsplit('.', 1)[-1])
    if not base:
        return None
    try:
        r = await client.get(base.rstrip('/') + '/domain/' + domain)
        if r.status_code != 200:
            return None
        d = _registered(r.json())
        if d is None:
            return None
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - d).days)
    except Exception:
        return None


_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    # 접속 도구를 만드는 데 0.5초쯤 걸리므로 한 번 만들어 계속 쓴다
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=2.0, follow_redirects=True,
                                    headers={'Accept': 'application/rdap+json'})
    return _client


async def lookup(host: str, budget: float = 0.9) -> DomainInfo:
    """DNS와 등록일을 동시에 조회. budget초 안에 끝나지 않은 것은 '모름'.
    DNS에서 '없는 주소'로 나오면 등록일은 기다리지 않는다."""
    domain = registered_domain(host)
    hit = _cache.get(host)
    if hit and time.monotonic() - hit[0] < CACHE_TTL:
        return hit[1]
    deadline = time.monotonic() + budget
    dns_t = asyncio.create_task(_dns_exists(host))
    age_t = asyncio.create_task(_age_days(domain, _get_client()))
    pending = {dns_t, age_t}
    while pending:
        left = deadline - time.monotonic()
        if left <= 0:
            break
        _, pending = await asyncio.wait(pending, timeout=left, return_when=asyncio.FIRST_COMPLETED)
        if dns_t.done() and dns_t.result() is False:
            break
    for t in pending:
        t.cancel()
    info = DomainInfo(exists=dns_t.result() if dns_t.done() else None,
                      age_days=age_t.result() if age_t.done() and not age_t.cancelled() else None)
    if info.exists is not None or info.age_days is not None:
        _cache[host] = (time.monotonic(), info)
    return info
