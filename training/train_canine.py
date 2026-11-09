"""CANINE 미세조정 (Google Colab T4 GPU 기준).

준비: prepare_data.py로 만든 train.csv / val.csv / test.csv 를 --data 폴더에 둔다.
실행: python train_canine.py --data /content/drive/MyDrive/smishing/data --out /content/drive/MyDrive/smishing/out
      (--push 팀이름/smishing-canine 을 주면 학습 후 Hugging Face Hub에 올림. HF_TOKEN 필요)

- 매 epoch마다 --out에 저장하므로 Colab이 끊겨도 같은 명령으로 다시 실행하면 이어서 학습한다.
- 끝나면 out/metrics.json 에 검증·테스트 성능과 '오탐률 5% 이하에서 재현율이 가장 높은 기준점'을 남긴다.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset
from sklearn.metrics import (confusion_matrix, f1_score, precision_score, recall_score,
                             roc_auc_score, precision_recall_curve)
from transformers import (CanineForSequenceClassification, CanineTokenizer, Trainer,
                          TrainingArguments, EarlyStoppingCallback)
from transformers.trainer_utils import get_last_checkpoint

BASE = 'google/canine-s'
MAX_CHARS = 256


class UrlSet(Dataset):
    def __init__(self, df, tok):
        self.urls = df['url'].astype(str).tolist()
        self.labels = df['label'].astype(int).tolist()
        self.tok = tok

    def __len__(self):
        return len(self.urls)

    def __getitem__(self, i):
        enc = self.tok(self.urls[i][:MAX_CHARS], truncation=True, max_length=MAX_CHARS + 2,
                       padding='max_length')
        enc['labels'] = self.labels[i]
        return {k: torch.tensor(v) for k, v in enc.items()}


def probs_of(trainer, ds):
    out = trainer.predict(ds)
    p = torch.softmax(torch.tensor(out.predictions), -1)[:, 1].numpy()
    return p, np.array(ds.labels)


def report(p, y, thr):
    pred = (p >= thr).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {'threshold': float(thr), 'recall': recall_score(y, pred), 'precision': precision_score(y, pred, zero_division=0),
            'f1': f1_score(y, pred), 'fpr': fp / max(1, fp + tn), 'auc': roc_auc_score(y, p),
            'confusion': {'tn': int(tn), 'fp': int(fp), 'fn': int(fn), 'tp': int(tp)}}


def pick_threshold(p, y, max_fpr=0.05):
    """검증셋에서 오탐률 max_fpr 이하를 지키면서 재현율이 가장 높은 기준점."""
    best = 0.5
    best_rec = -1
    for t in np.linspace(0.05, 0.95, 91):
        pred = p >= t
        fpr = ((pred == 1) & (y == 0)).sum() / max(1, (y == 0).sum())
        rec = ((pred == 1) & (y == 1)).sum() / max(1, (y == 1).sum())
        if fpr <= max_fpr and rec > best_rec:
            best, best_rec = t, rec
    return float(best)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--epochs', type=float, default=3)
    ap.add_argument('--lr', type=float, default=2e-5)
    ap.add_argument('--batch', type=int, default=32)
    ap.add_argument('--limit', type=int, default=0, help='빠른 시험용: 학습 데이터 개수 제한')
    ap.add_argument('--push', default='')
    a = ap.parse_args()

    data, out = Path(a.data), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tok = CanineTokenizer.from_pretrained(BASE)
    tr, va, te = (pd.read_csv(data / f'{k}.csv') for k in ('train', 'val', 'test'))
    if a.limit:
        tr = tr.sample(n=min(a.limit, len(tr)), random_state=0)
        va = va.sample(n=min(a.limit // 5, len(va)), random_state=0)
    ds_tr, ds_va, ds_te = UrlSet(tr, tok), UrlSet(va, tok), UrlSet(te, tok)
    print(f'train={len(ds_tr)} val={len(ds_va)} test={len(ds_te)} gpu={torch.cuda.is_available()}')

    model = CanineForSequenceClassification.from_pretrained(
        BASE, num_labels=2, id2label={0: 'normal', 1: 'phishing'}, label2id={'normal': 0, 'phishing': 1})

    def metrics(ev):
        p = torch.softmax(torch.tensor(ev.predictions), -1)[:, 1].numpy()
        y = ev.label_ids
        pred = (p >= 0.5).astype(int)
        return {'f1': f1_score(y, pred), 'recall': recall_score(y, pred), 'auc': roc_auc_score(y, p)}

    args = TrainingArguments(
        output_dir=str(out / 'ckpt'), num_train_epochs=a.epochs, learning_rate=a.lr,
        per_device_train_batch_size=a.batch, per_device_eval_batch_size=a.batch * 2,
        eval_strategy='epoch', save_strategy='epoch', save_total_limit=2,
        load_best_model_at_end=True, metric_for_best_model='f1', greater_is_better=True,
        fp16=torch.cuda.is_available(), warmup_ratio=0.06, weight_decay=0.01,
        logging_steps=100, report_to='none', dataloader_num_workers=2, seed=42,
    )
    trainer = Trainer(model=model, args=args, train_dataset=ds_tr, eval_dataset=ds_va,
                      compute_metrics=metrics, callbacks=[EarlyStoppingCallback(early_stopping_patience=1)])
    last = get_last_checkpoint(str(out / 'ckpt')) if (out / 'ckpt').exists() else None
    if last:
        print(f'이어서 학습: {last}')
    trainer.train(resume_from_checkpoint=last)

    pv, yv = probs_of(trainer, ds_va)
    thr = pick_threshold(pv, yv)
    pt, yt = probs_of(trainer, ds_te)
    res = {'val@0.5': report(pv, yv, 0.5), 'val@thr': report(pv, yv, thr),
           'test@0.5': report(pt, yt, 0.5), 'test@thr': report(pt, yt, thr)}
    extra = data / 'test_phishtank_recent.csv'
    if extra.exists():
        ds_x = UrlSet(pd.read_csv(extra), tok)
        px, yx = probs_of(trainer, ds_x)
        res['phishtank_recent@thr'] = report(px, yx, thr)
    real = data / 'real_eval.csv'  # 실제 문자 속 링크(학습 미사용)
    if real.exists():
        ds_r = UrlSet(pd.read_csv(real), tok)
        pr, yr = probs_of(trainer, ds_r)
        res['real@thr'] = report(pr, yr, thr) if len(set(yr)) > 1 else {'n': len(yr), 'mean_p': float(pr.mean())}
    print(json.dumps(res, indent=2, ensure_ascii=False))
    (out / 'metrics.json').write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding='utf-8')

    final = out / 'model'
    trainer.save_model(str(final))
    tok.save_pretrained(str(final))
    (final / 'threshold.json').write_text(json.dumps({'threshold': thr}), encoding='utf-8')
    if a.push:
        trainer.model.push_to_hub(a.push, private=True, token=os.getenv('HF_TOKEN'))
        tok.push_to_hub(a.push, private=True, token=os.getenv('HF_TOKEN'))
        print(f'올림: https://huggingface.co/{a.push}')


if __name__ == '__main__':
    main()
