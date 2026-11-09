"""공식 도메인(화이트리스트)과 알려진 피싱(블랙리스트) 목록."""
from pathlib import Path

from .normalize import host_of, normalize, registered_domain

DATA_DIR = Path(__file__).resolve().parent.parent / 'data'


def _read(name: str) -> set[str]:
    p = DATA_DIR / name
    if not p.exists():
        return set()
    out = set()
    for line in p.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            out.add(line.lower())
    return out


class Lists:
    def __init__(self):
        self.whitelist = _read('whitelist.txt')            # 등록 도메인 단위(eTLD+1)
        # 피싱 전용 도메인 (+ 시연용 가짜 주소: demo_blacklist.txt)
        self.black_domains = _read('blacklist_domains.txt') | _read('demo_blacklist.txt')
        self.black_urls = {self._key(u) for u in _read('blacklist_urls.txt')}  # 단축 URL 등 전체 주소
        self.popular = _read('popular_domains.txt')  # Tranco 상위 도메인(오탐 줄이기용)

    @staticmethod
    def _key(url: str) -> str:
        try:
            u = normalize(url)
        except ValueError:
            return url
        s = u.split('://', 1)[-1]  # http/https 차이 무시
        return s[4:] if s.startswith('www.') else s  # www 유무 무시(학습 데이터와 같은 형식)

    def is_official(self, url: str) -> bool:
        host = host_of(url)
        if host in self.whitelist or registered_domain(host) in self.whitelist:
            return True
        # '.go.kr'처럼 점으로 시작하는 항목은 그 아래 전부(누구나 등록할 수 없는 공공 도메인)
        return any(w.startswith('.') and host.endswith(w) for w in self.whitelist)

    def is_known_phish(self, url: str) -> bool:
        if self._key(url) in self.black_urls:
            return True
        host = host_of(url)
        return host in self.black_domains or registered_domain(host) in self.black_domains

    def is_popular(self, url: str) -> bool:
        return registered_domain(host_of(url)) in self.popular

    def stats(self) -> dict:
        return {'whitelist': len(self.whitelist), 'black_domains': len(self.black_domains),
                'black_urls': len(self.black_urls), 'popular': len(self.popular)}
