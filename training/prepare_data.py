"""학습 데이터 만들기.

입력(training/data/raw/):
  kisa2023.csv, kisa2024.csv   공공데이터포털 '한국인터넷진흥원 피싱사이트 URL'(날짜, 홈페이지주소)
  phishtank.csv.bz2            PhishTank online-valid (보조)
  tranco.zip                   Tranco 상위 100만 도메인
  normal_urls.txt  (선택)      Common Crawl 등에서 모은 경로 있는 정상 URL (fetch_normal_urls.py)
  real_normal.txt  (선택)      팀원·지인 알림 문자 속 정상 링크(개인정보 지운 것) → 평가 전용

출력(training/data/):
  train.csv, val.csv, test.csv           url,label,date,source  (label 1=피싱)
  test_phishtank_recent.csv              PhishTank 2025년 이후(추가 평가)
  blacklist_domains.txt, blacklist_urls.txt   서버의 피싱 목록용
  stats.json

실행: python prepare_data.py          (v1: KISA 2023~2024 기준으로 나눔)
      python prepare_data.py --v2     (v2: 2025~2026년 PhishTank까지 학습에 넣음 → data/v2/)
  v2 나누기: 학습 ~2025-12 / 검증 2026-01~04 / 테스트 2026-05~ (KISA는 2024-12까지만 공개돼 전부 학습에 들어감)
"""
import bz2
import csv
import hashlib
import io
import json
import random
import sys
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'server'))
from app.normalize import normalize, host_of, registered_domain  # noqa: E402
from app.rules import is_shortener  # noqa: E402

RAW, OUT = ROOT / 'data' / 'raw', ROOT / 'data'
VAL_FROM, TEST_FROM, TEST_TO = '2024-07-01', '2024-10-01', '2024-12-31'
V2_VAL_FROM, V2_TEST_FROM = '2026-01-01', '2026-05-01'
SEED = 42

# 여러 사람이 같이 쓰는 호스팅: 도메인 전체를 막으면 안 되므로 주소 단위로만 목록에 넣는다
SHARED_HOSTING = {
    'github.io', 'web.app', 'firebaseapp.com', 'pages.dev', 'workers.dev', 'vercel.app', 'netlify.app',
    'blogspot.com', 'wixsite.com', 'weebly.com', 'glitch.me', 'herokuapp.com', 'ngrok-free.app', 'r2.dev',
    'azurewebsites.net', 'amazonaws.com', 'cloudfront.net', 'googleapis.com', 'google.com', 'appspot.com',
    'onrender.com', 'replit.app', 'repl.co', 'framer.app', 'webflow.io', 'square.site', 'godaddysites.com',
    'notion.site', 'jimdosite.com', 'mystrikingly.com', 'ipfs.io', 'dweb.link', 'cloudflare-ipfs.com',
}


def model_text(url: str) -> str:
    """모델 입력: 스킴(http/https)과 앞의 'www.'를 뗀다.
    원본 데이터마다 표기 방식이 달라(Common Crawl은 www를 지움) '정답 힌트'가 되기 때문."""
    s = url.split('://', 1)[-1]
    return s[4:] if s.startswith('www.') else s


def read_kisa(path: Path):
    raw = path.read_bytes()
    text = None
    for enc in ('utf-8-sig', 'cp949'):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            pass
    rows = csv.reader(io.StringIO(text))
    next(rows, None)  # 헤더
    for r in rows:
        if len(r) >= 2 and r[0].strip():
            yield r[0].strip()[:10], r[1].strip(), 'kisa'


def read_phishtank(path: Path):
    with bz2.open(path, 'rt', encoding='utf-8', errors='replace') as f:
        for r in csv.DictReader(f):
            yield r['submission_time'][:10], r['url'], 'phishtank'


def read_tranco(path: Path, limit: int):
    with zipfile.ZipFile(path) as z:
        name = z.namelist()[0]
        with z.open(name) as f:
            for i, line in enumerate(io.TextIOWrapper(f, encoding='utf-8')):
                if i >= limit:
                    break
                yield line.strip().split(',', 1)[1]


def read_lines(path: Path):
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                yield line


def domain_bucket(url: str) -> str:
    """정상 URL은 날짜가 없으니 도메인 해시로 나눈다(같은 도메인이 양쪽에 들어가지 않게)."""
    h = int(hashlib.md5(registered_domain(host_of(url)).encode()).hexdigest(), 16) % 100
    return 'train' if h < 70 else 'val' if h < 85 else 'test'


def main(tranco_limit=200_000, v2=False):
    rnd = random.Random(SEED)
    phish, black_domains, black_urls, skipped = {}, set(), set(), Counter()
    # 널리 쓰이는 도메인(Tranco 상위 10만)은 그 위에 피싱 페이지가 있어도 도메인 전체를 막지 않는다
    popular = set(read_tranco(RAW / 'tranco.zip', 100_000))

    # ---- 피싱 ----
    sources = []
    for p in sorted(RAW.glob('kisa*.csv')):
        sources.append(read_kisa(p))
    if (RAW / 'phishtank.csv.bz2').exists():
        sources.append(read_phishtank(RAW / 'phishtank.csv.bz2'))
    for src in sources:
        for date, raw, source in src:
            try:
                u = normalize(raw)
            except ValueError:
                skipped['bad_url'] += 1
                continue
            host = host_of(u)
            reg = registered_domain(host)
            if is_shortener(host):
                black_urls.add(model_text(u))  # 단축 URL: 목록에만, 학습 제외
                skipped['shortener'] += 1
                continue
            if reg in SHARED_HOSTING or host in SHARED_HOSTING or reg in popular or host in popular:
                black_urls.add(model_text(u))  # 주소 하나만 막음
            else:
                black_domains.add(host)
            key = model_text(u)
            if key not in phish or date < phish[key][0]:
                phish[key] = (date, source)

    # ---- 정상 ----
    whitelist = set(read_lines(ROOT.parent / 'server' / 'data' / 'whitelist.txt'))
    normal = {}
    for d in read_tranco(RAW / 'tranco.zip', tranco_limit):
        normal.setdefault(model_text('http://' + d), 'tranco')
    n_cc = 0
    for fname, source in (('normal_urls.txt', 'commoncrawl'), ('normal_urls_ko.txt', 'kowiki')):
        for raw in read_lines(RAW / fname):
            try:
                normal.setdefault(model_text(normalize(raw)), source)
                n_cc += 1
            except ValueError:
                pass
    for raw in list(normal):  # 단축 URL·피싱과 겹치는 것 제거
        h = raw.split('/', 1)[0]
        if is_shortener(h) or raw in phish or h in black_domains:
            del normal[raw]
    # 공식 도메인이 피싱 목록에 섞여 들어갔다면 목록에서 뺀다(오탐 방지)
    def official(h):
        return h in whitelist or registered_domain(h) in whitelist or \
            any(w.startswith('.') and h.endswith(w) for w in whitelist)
    black_domains = {h for h in black_domains if not official(h)}
    # KISA 원본에 공식 주소 자체가 섞여 있는 경우가 있음(예: nhis.or.kr) → 주소 목록에서도 뺀다
    black_urls = {u for u in black_urls if not official(u.split('/', 1)[0])}

    # ---- 나누기 ----
    out_dir = OUT / 'v2' if v2 else OUT
    out_dir.mkdir(exist_ok=True)
    splits = {k: [] for k in (('train', 'val', 'test') if v2 else ('train', 'val', 'test', 'test_phishtank_recent'))}
    for url, (date, source) in phish.items():
        if v2:
            k = 'test' if date >= V2_TEST_FROM else 'val' if date >= V2_VAL_FROM else 'train'
            splits[k].append((url, 1, date, source))
        elif source == 'phishtank' and date > TEST_TO:
            splits['test_phishtank_recent'].append((url, 1, date, source))
        elif date >= TEST_FROM and date <= TEST_TO:
            splits['test'].append((url, 1, date, source))
        elif date >= VAL_FROM and date <= TEST_TO:
            splits['val'].append((url, 1, date, source))
        elif date < VAL_FROM:
            splits['train'].append((url, 1, date, source))
    norm_by = {'train': [], 'val': [], 'test': []}
    for url, source in normal.items():
        norm_by[domain_bucket('http://' + url)].append((url, 0, '', source))

    # 정상은 피싱 수와 1:1. '경로 있는 주소' 비율도 피싱 쪽과 같게 맞춰 길이·형태로 맞히지 못하게 한다
    for k in ('train', 'val', 'test'):
        need = len(splits[k])
        ratio = sum('/' in r[0] for r in splits[k]) / max(1, need)
        pool = norm_by[k]
        with_path = [r for r in pool if '/' in r[0]]
        bare = [r for r in pool if '/' not in r[0]]
        rnd.shuffle(with_path)
        rnd.shuffle(bare)
        n_path = min(len(with_path), round(need * ratio))
        n_bare = min(len(bare), need - n_path)
        n_path = min(len(with_path), need - n_bare)  # 한쪽이 모자라면 다른 쪽으로 채움
        take = with_path[:n_path] + bare[:n_bare]
        splits[k] += take
        rnd.shuffle(splits[k])
    # 추가 평가셋에도 같은 수의 정상(테스트 도메인)
    if not v2:
        extra = [r for r in norm_by['test'] if r not in splits['test']]
        rnd.shuffle(extra)
        splits['test_phishtank_recent'] += extra[:len(splits['test_phishtank_recent'])]

    # ---- 저장 ----
    for k, rows in splits.items():
        with open(out_dir / f'{k}.csv', 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['url', 'label', 'date', 'source'])
            w.writerows(rows)
    # 피싱 목록: 학습 폴더와 서버 폴더(server/data) 양쪽에 저장
    for d in (OUT, ROOT.parent / 'server' / 'data'):
        (d / 'blacklist_domains.txt').write_text('\n'.join(sorted(black_domains)), encoding='utf-8')
        (d / 'blacklist_urls.txt').write_text('\n'.join(sorted(black_urls)), encoding='utf-8')
    # 널리 쓰이는 도메인(Tranco 상위 10만, 국내 대형 사이트도 1~9만 위): 서버에서 AI 점수가 높아도 '주의'까지만 올리는 데 쓴다
    top10k = [d for d in read_tranco(RAW / 'tranco.zip', 100_000)
              if d not in SHARED_HOSTING and not is_shortener(d)]
    (ROOT.parent / 'server' / 'data' / 'popular_domains.txt').write_text(
        '# Tranco 상위 10만 도메인(공유 호스팅·단축 URL 제외). 피싱 목록이 우선한다.\n' + '\n'.join(top10k), encoding='utf-8')

    def share_path(rows, label):
        xs = [r for r in rows if r[1] == label]
        return round(sum('/' in r[0] for r in xs) / max(1, len(xs)), 3)

    stats = {
        'skipped': dict(skipped), 'phish_unique': len(phish), 'normal_pool': len(normal),
        'normal_from_commoncrawl': n_cc, 'black_domains': len(black_domains), 'black_urls': len(black_urls),
        'splits': {k: dict(Counter(r[1] for r in v)) for k, v in splits.items()},
        'path_ratio': {k: {'phish': share_path(v, 1), 'normal': share_path(v, 0)} for k, v in splits.items()},
        'avg_len': {k: {'phish': round(sum(len(r[0]) for r in v if r[1] == 1) / max(1, sum(r[1] == 1 for r in v)), 1),
                        'normal': round(sum(len(r[0]) for r in v if r[1] == 0) / max(1, sum(r[1] == 0 for r in v)), 1)}
                    for k, v in splits.items()},
    }
    (out_dir / 'stats.json').write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main(v2='--v2' in sys.argv)
