"""데이터에 '정답 힌트'(길이, 경로 유무, 도메인 끝 등)가 남아 있는지 확인."""
import json
from pathlib import Path

import pandas as pd

D = Path(__file__).resolve().parent / 'data'
s = json.loads((D / 'stats.json').read_text(encoding='utf-8'))
print('개수', s['splits'])
print('경로 비율', s['path_ratio'])
print('평균 길이', s['avg_len'])
print('피싱 목록', s['black_domains'], s['black_urls'])
for k in ('train', 'val', 'test'):
    d = pd.read_csv(D / f'{k}.csv')
    h = d.url.str.split('/').str[0]
    line = []
    for lab, name in ((0, '정상'), (1, '피싱')):
        x = h[d.label == lab]
        line.append(f"{name}: .kr={x.str.endswith('.kr').mean():.3f} .com={x.str.endswith('.com').mean():.3f}")
    print(k, ' | '.join(line), '| 정상 출처', d[d.label == 0].source.value_counts().to_dict())
