"""URL 추출·정규화."""
import re
from urllib.parse import urlsplit, urlunsplit, unquote

# 문자 속에서 링크를 찾는 패턴: 스킴이 있거나, '도메인.tld/...' 형태
_URL_RE = re.compile(
    r"""(?ix)
    (?:https?://[^\s<>"']+)
    |
    (?:\b(?:[a-z0-9가-힣-]+\.)+[a-z가-힣]{2,}(?:/[^\s<>"']*)?)
    """
)
_TRAILING = '.,;:!?)]}>\'"’”'


def extract_urls(text: str) -> list[str]:
    """문자 전체에서 URL 후보만 골라낸다(중복 제거, 순서 유지)."""
    seen, out = set(), []
    for m in _URL_RE.finditer(text or ''):
        u = m.group(0).rstrip(_TRAILING)
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def normalize(raw: str) -> str:
    """스킴 보충, 호스트 소문자·IDNA 변환, 퍼센트 인코딩 복원, 끝 '/' 제거."""
    s = (raw or '').strip()
    if not s:
        raise ValueError('빈 URL')
    if not re.match(r'^[a-z][a-z0-9+.-]*://', s, re.I):
        s = 'http://' + s
    p = urlsplit(s)
    if p.scheme.lower() not in ('http', 'https'):
        raise ValueError('http/https 주소만 검사할 수 있습니다')
    host = (p.hostname or '').rstrip('.')
    if not host:
        raise ValueError('주소에 호스트가 없습니다')
    try:
        host = host.encode('idna').decode('ascii').lower()
    except UnicodeError:
        host = host.lower()
    netloc = host + (f':{p.port}' if p.port else '')
    path = unquote(p.path)
    if path.endswith('/'):
        path = path.rstrip('/')
    return urlunsplit((p.scheme.lower(), netloc, path, unquote(p.query), ''))


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or '').lower()


def registered_domain(host: str) -> str:
    """eTLD+1(예: www.cjlogistics.com → cjlogistics.com, a.b.co.kr → b.co.kr)."""
    try:
        import tldextract
        ext = _EXTRACT(host)
        if ext.domain and ext.suffix:
            return f'{ext.domain}.{ext.suffix}'
        return host
    except ImportError:  # 간이 처리
        parts = host.split('.')
        if len(parts) >= 3 and parts[-2] in ('co', 'or', 'go', 'ac', 'ne', 're', 'pe', 'com', 'net', 'org'):
            return '.'.join(parts[-3:])
        return '.'.join(parts[-2:])


try:
    import tldextract as _t
    # 네트워크로 공개 접미사 목록을 받지 않도록 내장 스냅샷만 사용
    _EXTRACT = _t.TLDExtract(suffix_list_urls=())
except ImportError:
    _EXTRACT = None
