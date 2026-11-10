"""시연용: 노트북의 검사 서버를 Cloudflare 무료 터널로 인터넷에 연결한다.
무료 터널은 켤 때마다 주소가 바뀌므로, 새 주소를 Hugging Face 모델 저장소의 endpoint.txt에 적는다.
앱은 시작할 때 그 파일을 읽어 서버 주소를 정한다(APK를 다시 만들 필요 없음).

실행: .venv\\Scripts\\python run_public.py      (끄기: Ctrl+C)
먼저 `hf auth login`(Write 토큰)으로 로그인해 둘 것.
"""
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from huggingface_hub import HfApi

HERE = Path(__file__).resolve().parent
PORT = 8000
LOCAL_MODEL = HERE.parent / 'training' / 'out' / 'model_v2'
MODEL_REPO = os.getenv('KOK_MODEL_REPO', '6hzl/kok-canine')
CLOUDFLARED = next((p for p in (r'C:\Program Files (x86)\cloudflared\cloudflared.exe',
                                r'C:\Program Files\cloudflared\cloudflared.exe') if Path(p).exists()), 'cloudflared')


def healthy() -> bool:
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/health', timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def main():
    procs = []
    if healthy():
        print('검사 서버가 이미 켜져 있어 그대로 씁니다.')
    else:
        env = dict(os.environ, MODEL_ID=str(LOCAL_MODEL) if LOCAL_MODEL.exists() else MODEL_REPO)
        print('검사 서버를 켜는 중... (모델을 불러오는 데 30초쯤 걸립니다)')
        procs.append(subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1',
                                       '--port', str(PORT), '--no-access-log'], cwd=HERE, env=env))
        for _ in range(120):
            if healthy():
                break
            time.sleep(1)
        else:
            sys.exit('검사 서버가 켜지지 않았습니다.')

    try:
        while True:  # 무료 터널은 가끔 끊긴다 → 1분마다 확인해서 끊기면 새로 열고 주소를 다시 기록
            tunnel, url = open_tunnel()
            fails = 0
            while tunnel.poll() is None and fails < 3:
                time.sleep(60)
                fails = 0 if alive(url) else fails + 1
            print('터널이 끊겨 다시 엽니다...')
            tunnel.terminate()
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            p.terminate()
        if tunnel_box:
            tunnel_box[0].terminate()


tunnel_box = []


def alive(url: str) -> bool:
    try:
        with urllib.request.urlopen(url + '/health', timeout=10) as r:
            return r.status == 200
    except Exception:
        return False


def open_tunnel():
    print('터널을 여는 중...')
    tunnel = subprocess.Popen([CLOUDFLARED, 'tunnel', '--no-autoupdate', '--url', f'http://127.0.0.1:{PORT}'],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                              errors='replace')
    tunnel_box[:] = [tunnel]
    url = None
    for line in tunnel.stdout:
        m = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', line)
        if m:
            url = m.group(0)
            break
    if not url:
        sys.exit('터널 주소를 받지 못했습니다.')
    # 터널 로그는 계속 읽어서 버린다(안 읽으면 터널이 멈춤)
    import threading
    threading.Thread(target=lambda: [None for _ in tunnel.stdout], daemon=True).start()
    for _ in range(30):  # 실제로 연결될 때까지 기다린 뒤 주소를 공개
        if alive(url):
            break
        time.sleep(2)
    HfApi().upload_file(path_or_fileobj=url.encode(), path_in_repo='endpoint.txt', repo_id=MODEL_REPO,
                        commit_message='시연 서버 주소 갱신')
    print('\n' + '=' * 60)
    print(' 인터넷 주소:', url, '  (' + time.strftime('%H:%M') + ')')
    print(' 앱이 읽는 곳: https://huggingface.co/' + MODEL_REPO + '/resolve/main/endpoint.txt')
    print(' 웹 데모: https://6hzl-kok-demo.static.hf.space')
    print(' 터널이 끊기면 자동으로 다시 엽니다. 끄려면 Ctrl+C')
    print('=' * 60 + '\n')
    return tunnel, url


if __name__ == '__main__':
    main()
