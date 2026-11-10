"""Hugging Face에 모델과 검사 서버(Space)를 올린다. 먼저 `hf auth login`으로 로그인해 둘 것.
실행: python deploy_hf.py [모델폴더]   (기본: ../training/out/model_v2)
  1) 모델  → <아이디>/kok-canine   (모델 저장소)
  2) 서버  → <아이디>/kok-api      (Docker Space, 무료 CPU) + 변수 MODEL_ID 설정
"""
import sys
from pathlib import Path

from huggingface_hub import HfApi

HERE = Path(__file__).resolve().parent
MODEL_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / 'training' / 'out' / 'model_v2'
MODEL_FILES = ['config.json', 'model.safetensors', 'special_tokens_map.json', 'threshold.json', 'tokenizer_config.json']

api = HfApi()
user = api.whoami()['name']
model_repo, space_repo = f'{user}/kok-canine', f'{user}/kok-api'

# 1) 모델
api.create_repo(model_repo, repo_type='model', exist_ok=True)
api.upload_folder(repo_id=model_repo, folder_path=MODEL_DIR, allow_patterns=MODEL_FILES,
                  commit_message='KoK CANINE v2 (KISA 2023~2024 + PhishTank ~2025-12)')
print('모델:', f'https://huggingface.co/{model_repo}')

# 2) 서버(Space)
api.create_repo(space_repo, repo_type='space', space_sdk='docker', exist_ok=True)
api.add_space_variable(space_repo, 'MODEL_ID', model_repo)
api.upload_folder(repo_id=space_repo, repo_type='space', folder_path=HERE,
                  allow_patterns=['app/*.py', 'app/static/*', 'data/*', 'Dockerfile', 'requirements.txt', 'README.md'],
                  commit_message='KoK 검사 서버')
print('Space:', f'https://huggingface.co/spaces/{space_repo}')
print('API 주소:', f'https://{user.lower()}-kok-api.hf.space')
