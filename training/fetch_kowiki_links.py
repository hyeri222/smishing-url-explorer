"""한국어 위키백과 '외부 링크' 목록에서 국내 정상 URL을 모은다(CC BY-SA, 페이지는 열지 않음).

Common Crawl 표본에는 국내(.kr) 주소가 적어서, 위키백과 문서가 출처로 단 국내 사이트 링크로 보충한다.
실행: python fetch_kowiki_links.py   → data/raw/normal_urls_ko.txt (prepare_data.py가 함께 읽음)
"""
import gzip
import io
import random
import re
import sys
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'server'))
from app.normalize import registered_domain  # noqa: E402

RAW = ROOT / 'data' / 'raw'
DUMP = 'https://dumps.wikimedia.org/kowiki/latest/kowiki-latest-externallinks.sql.gz'
UA = 'smishing-url-explorer student project'
# INSERT 문 안의 한 행: (el_id, el_from, 'el_to_domain_index', 'el_to_path')
ROW = re.compile(r"\(\d+,\d+,'((?:[^'\\]|\\.)*)','((?:[^'\\]|\\.)*)'\)")
SKIP_EXT = ('.jpg', '.jpeg', '.png', '.gif', '.pdf', '.css', '.js')


def domain_from_index(idx: str) -> str | None:
    """'https://kr.co.chosun.www.' → 'www.chosun.co.kr'"""
    if '://' not in idx:
        return None
    rev = idx.split('://', 1)[1].rstrip('.')
    rev = rev.split(':')[0]
    parts = [p for p in rev.split('.') if p]
    return '.'.join(reversed(parts)) if parts else None


def main(per_domain=30, top=300_000):
    dst = RAW / 'kowiki-externallinks.sql.gz'
    if not dst.exists():
        print('내려받는 중(약 190MB):', DUMP, flush=True)
        with urllib.request.urlopen(urllib.request.Request(DUMP, headers={'User-Agent': UA}), timeout=120) as r, \
                open(dst, 'wb') as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)

    with zipfile.ZipFile(RAW / 'tranco.zip') as z, z.open(z.namelist()[0]) as f:
        tranco = {line.strip().split(',', 1)[1] for i, line in enumerate(io.TextIOWrapper(f, encoding='utf-8'))
                  if i < top}

    by_dom = defaultdict(set)
    with gzip.open(dst, 'rt', encoding='utf-8', errors='replace') as f:
        for line in f:  # 행이 한 줄에 하나씩, 또는 한 줄에 여러 개
            if not line.startswith(('(', 'INSERT INTO')):
                continue
            for m in ROW.finditer(line):
                host = domain_from_index(m.group(1).replace("\\'", "'"))
                path = m.group(2).replace("\\'", "'")
                if not host or len(path) < 2 or path.lower().split('?')[0].endswith(SKIP_EXT):
                    continue
                reg = registered_domain(host)
                # 국내 주소이면서 Tranco 상위 도메인(=널리 쓰이는 정상 사이트)만
                if (host.endswith('.kr') or reg in tranco) and reg in tranco:
                    if len(by_dom[reg]) < per_domain * 5:
                        by_dom[reg].add(host + path)

    rnd = random.Random(0)
    out = []
    for reg, urls in by_dom.items():
        urls = sorted(urls)
        rnd.shuffle(urls)
        out += urls[:per_domain]
    kr_urls = [u for u in out if u.split('/', 1)[0].endswith('.kr')]
    other = [u for u in out if not u.split('/', 1)[0].endswith('.kr')]
    out = kr_urls + other[:len(kr_urls) // 2]  # 국내 위주, 해외는 국내의 절반만
    rnd.shuffle(out)
    (RAW / 'normal_urls_ko.txt').write_text('\n'.join(out), encoding='utf-8')
    kr = sum(u.split('/', 1)[0].endswith('.kr') for u in out)
    print(f'국내 보충 정상 URL {len(out)}개 (.kr {kr}개, 도메인 {len(by_dom)}개)')


if __name__ == '__main__':
    main()
