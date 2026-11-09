"""'경로가 있는 정상 URL' 모으기 (Common Crawl 색인 표본 파일 1개만 내려받음, 페이지는 열지 않음).

정상 데이터가 'naver.com' 같은 짧은 주소뿐이면 모델이 길이만 보고 맞히게 된다.
Common Crawl의 cluster.idx(약 100MB)에는 수집된 페이지 약 3,000개마다 1개씩 실제 주소가 들어 있다.
이 중 Tranco 상위 도메인에 속한 주소만 골라 정상 URL로 쓴다.

실행: python fetch_normal_urls.py            → data/raw/normal_urls.txt
옵션: --crawl CC-MAIN-2026-43 --top 200000 --per-domain 20
"""
import argparse
import io
import random
import sys
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'server'))
from app.normalize import registered_domain  # noqa: E402

RAW = ROOT / 'data' / 'raw'
UA = 'smishing-url-explorer student project'
SKIP_EXT = ('.jpg', '.jpeg', '.png', '.gif', '.css', '.js', '.ico', '.svg', '.woff', '.woff2', '.pdf', '.xml', '.txt')


def surt_to_url(surt: str) -> str | None:
    """'kr,co,cjlogistics,www)/ko/tool?x=1' → 'www.cjlogistics.co.kr/ko/tool?x=1'"""
    if ')' not in surt:
        return None
    host, rest = surt.split(')', 1)
    host = host.split(':')[0]  # 포트 제거
    parts = host.split(',')
    if not all(parts) or parts[0].isdigit():  # IP 주소는 제외
        return None
    return '.'.join(reversed(parts)) + rest


def tranco_set(top: int) -> set[str]:
    with zipfile.ZipFile(RAW / 'tranco.zip') as z, z.open(z.namelist()[0]) as f:
        out = set()
        for i, line in enumerate(io.TextIOWrapper(f, encoding='utf-8')):
            if i >= top:
                break
            out.add(line.strip().split(',', 1)[1])
        return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--crawl', default='CC-MAIN-2026-43')
    ap.add_argument('--top', type=int, default=200_000, help='Tranco 상위 몇 개 도메인까지 정상으로 볼지')
    ap.add_argument('--per-domain', type=int, default=20, help='도메인 하나에서 최대 몇 개')
    a = ap.parse_args()

    idx = RAW / f'cluster_{a.crawl}.idx'
    if not idx.exists():
        url = f'https://data.commoncrawl.org/cc-index/collections/{a.crawl}/indexes/cluster.idx'
        print('내려받는 중:', url, flush=True)
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=120) as r, open(idx, 'wb') as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)

    top = tranco_set(a.top)
    by_dom = defaultdict(list)
    with open(idx, encoding='utf-8', errors='replace') as f:
        for line in f:
            u = surt_to_url(line.split(' ', 1)[0])
            if not u or '/' not in u:
                continue
            path = u.split('/', 1)[1].split('?')[0].lower()
            if len(path) < 2 or path.endswith(SKIP_EXT) or 'robots' in path:
                continue
            reg = registered_domain(u.split('/', 1)[0])
            if reg in top:
                by_dom[reg].append(u)

    rnd = random.Random(0)
    out = []
    for reg, urls in by_dom.items():
        rnd.shuffle(urls)
        out += urls[:a.per_domain]
    rnd.shuffle(out)
    dst = RAW / 'normal_urls.txt'
    dst.write_text('\n'.join(out), encoding='utf-8')
    kr = sum(1 for u in out if '.kr/' in u)
    print(f'정상 URL {len(out)}개 (도메인 {len(by_dom)}개, .kr {kr}개) → {dst}')


if __name__ == '__main__':
    main()
