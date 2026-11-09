"""CANINE 위험 점수. MODEL_ID(허깅페이스 저장소 이름 또는 로컬 폴더)가 있을 때만 불러온다."""
import os
import threading

MAX_CHARS = 256


class CanineScorer:
    def __init__(self, model_id: str | None = None):
        self.model_id = model_id or os.getenv('MODEL_ID')
        self.ready = False
        self.error = ''
        self.caution_p = 0.05  # 학습 때 검증셋으로 정한 기준점(threshold.json이 있으면 그 값)
        self._lock = threading.Lock()
        if self.model_id:
            try:
                self._load()
            except Exception as e:  # 모델이 없어도 서버는 뜨게 한다
                self.error = f'{type(e).__name__}: {e}'

    def _load(self):
        import torch
        from transformers import CanineTokenizer, CanineForSequenceClassification
        torch.set_num_threads(int(os.getenv('TORCH_THREADS', '2')))
        token = os.getenv('HF_TOKEN') or None
        self.tok = CanineTokenizer.from_pretrained(self.model_id, token=token)
        self.model = CanineForSequenceClassification.from_pretrained(self.model_id, token=token).eval()
        self.torch = torch
        self.ready = True
        try:
            import json
            from pathlib import Path
            from huggingface_hub import hf_hub_download
            local = Path(self.model_id) / 'threshold.json'
            path = local if local.exists() else hf_hub_download(self.model_id, 'threshold.json', token=token)
            self.caution_p = float(json.loads(Path(path).read_text())['threshold'])
        except Exception:
            pass  # 없으면 기본값 0.05
        # 첫 판정은 준비 시간이 길어 앱이 시간 초과로 '확인 못 함'을 띄울 수 있으므로, 켜질 때 미리 한 번 돌린다
        self.predict('example.com/warmup')

    def predict(self, url: str) -> float | None:
        """피싱일 확률(0~1). 모델이 없으면 None."""
        if not self.ready:
            return None
        text = url.split('://', 1)[-1]  # 학습 때와 똑같이 스킴과 앞의 'www.'를 뗀다
        if text.startswith('www.'):
            text = text[4:]
        with self._lock, self.torch.inference_mode():
            enc = self.tok(text[:MAX_CHARS], return_tensors='pt', truncation=True, max_length=MAX_CHARS + 2)
            logits = self.model(**enc).logits
            return float(self.torch.softmax(logits, -1)[0, 1])
