"""저장된 모델 하나를 CSV 하나로 채점한다(CPU에서도 됨). train_canine.py의 report와 같은 지표.
실행: python eval_model.py out/model data/v2/test.csv out/v1_on_v2test.json"""
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score
from transformers import CanineForSequenceClassification, CanineTokenizer

MAX_CHARS = 256


def report(p, y, thr):
    pred = (p >= thr).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {'threshold': thr, 'accuracy': (tp + tn) / len(y), 'recall': recall_score(y, pred),
            'precision': precision_score(y, pred, zero_division=0), 'f1': f1_score(y, pred),
            'fpr': fp / max(1, fp + tn), 'auc': roc_auc_score(y, p),
            'confusion': {'tn': int(tn), 'fp': int(fp), 'fn': int(fn), 'tp': int(tp)}}


def main(model_dir, csv_path, out_path):
    torch.set_num_threads(4)
    tok = CanineTokenizer.from_pretrained(model_dir)
    model = CanineForSequenceClassification.from_pretrained(model_dir).eval()
    rows = list(csv.DictReader(open(csv_path, encoding='utf-8')))
    probs, loss, t0 = [], 0.0, time.time()
    for i in range(0, len(rows), 64):
        b = rows[i:i + 64]
        enc = tok([r['url'][:MAX_CHARS] for r in b], truncation=True, max_length=MAX_CHARS + 2,
                  padding=True, return_tensors='pt')
        y = torch.tensor([int(r['label']) for r in b])
        with torch.inference_mode():
            logits = model(**enc).logits
        loss += torch.nn.functional.cross_entropy(logits, y, reduction='sum').item()
        probs += torch.softmax(logits, -1)[:, 1].tolist()
        if i % 6400 == 0:
            print(len(probs), '/', len(rows), round(time.time() - t0), 's', flush=True)
    p, y = np.array(probs), np.array([int(r['label']) for r in rows])
    res = {'model': str(model_dir), 'data': str(csv_path), 'n': len(rows), 'loss': loss / len(rows),
           '@0.5': report(p, y, 0.5), '@0.05': report(p, y, 0.05)}
    Path(out_path).write_text(json.dumps(res, indent=2), encoding='utf-8')
    print(json.dumps(res, indent=2))


if __name__ == '__main__':
    main(*sys.argv[1:4])
