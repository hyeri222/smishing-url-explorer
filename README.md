# 스미싱 URL 탐색기 (4조)

문자 속 링크를 누르는 순간, 열기 전에 AI(CANINE)가 먼저 검사하는 안드로이드 앱 + 검사 서버.

```
문자 속 링크 터치 → [앱] 공식 도메인이면 바로 열기
                    └ 그 외 → [서버] 단축 URL 풀기 → 피싱 목록 → CANINE 점수 → 이유
                              안전: 바로 열기 / 주의: 열면서 안내 / 위험: 경고창 / 확인 못 함: 경고창
```

| 폴더 | 내용 | 담당 |
|---|---|---|
| `server/` | 검사 서버(FastAPI). Hugging Face Spaces에 Docker로 배포 | 김서은 |
| `training/` | 데이터 정리, CANINE 학습(Colab) | 김서은 |
| `android/` | 안드로이드 앱(Kotlin, 외부 라이브러리 없음) | 이혜리 |

---

## 1. 학습 (Google Colab) — 직접 할 일

1. 구글 드라이브에 `smishing/data/` 폴더를 만든다.
2. `training/colab_upload/` 안의 파일 5개를 그 폴더에 올린다.
   (`train.csv`, `val.csv`, `test.csv`, `test_phishtank_recent.csv`, `train_canine.py`)
3. `training/colab_train.ipynb`를 Colab에서 연다(파일 → 노트북 업로드).
4. **런타임 → 런타임 유형 변경 → T4 GPU**.
5. 셀을 위에서부터 실행한다. 3번째 셀(빠른 시험)이 몇 분 안에 끝나면 4번째 셀(본 학습)을 실행한다.
   - 끊기면 2번째·4번째 셀만 다시 실행하면 이어서 학습한다.
6. 끝나면 `smishing/out/metrics.json`에 성능이, `smishing/out/model/`에 모델이 생긴다.

Hugging Face에 모델을 바로 올리려면: Hugging Face 가입 → Settings → Access Tokens에서 **Write** 토큰 발급 →
Colab 왼쪽 🔑(보안 비밀)에 `HF_TOKEN`으로 저장 → 4번째 셀의 `PUSH = '내아이디/smishing-canine'`.

## 2. 검사 서버 배포 (Hugging Face Spaces) — 직접 할 일

1. huggingface.co → New Space → SDK **Docker**, 하드웨어 **CPU basic(무료)**.
2. `server/` 폴더 안의 내용(`app/`, `data/`, `Dockerfile`, `requirements.txt`, `README.md`)을 Space에 올린다.
   - `data/blacklist_*.txt`(피싱 목록)는 GitHub에는 올리지 않지만 **Space에는 올려야 한다.**
3. Space → Settings → Variables: `MODEL_ID` = `내아이디/smishing-canine`
   (모델 저장소가 비공개면 Secrets에 `HF_TOKEN`도)
4. 빌드가 끝나면 `https://<아이디>-<스페이스>.hf.space/health` 에서 `"model"`이 채워졌는지 확인.

## 3. 앱 빌드

```
cd android
gradlew assembleDebug                                      # 개발용(PC 로컬 서버)
gradlew assembleRelease -PapiBase=https://<스페이스주소>.hf.space   # 배포용
```

Android Studio로 `android/` 폴더를 열어도 된다(Gradle 9.6, AGP 9.4, minSdk 29).

### PC에서 서버 + 에뮬레이터로 시험

```
cd server
.venv\Scripts\python -m uvicorn app.main:app --port 8000
adb reverse tcp:8000 tcp:8000
adb shell am start -a android.intent.action.VIEW -c android.intent.category.BROWSABLE -d "http://cj-1ogistics-demo.top/kr"
```

`cj-1ogistics-demo.top`은 `server/data/demo_blacklist.txt`에 넣어 둔 **시연용 가짜 주소**다(실제 피싱 아님).
**수집한 진짜 피싱 URL은 절대 브라우저로 열지 않는다.**

## 4. 데이터 다시 만들기

```
cd training
python fetch_normal_urls.py     # Common Crawl 표본(약 100MB)에서 경로 있는 정상 URL
python fetch_kowiki_links.py    # 한국어 위키백과 외부 링크(약 190MB)에서 국내 정상 URL
python prepare_data.py          # 날짜 기준 분할 + 피싱 목록(server/data에도 저장)
python check_bias.py            # 길이·경로·.kr 등 '정답 힌트'가 남았는지 확인
```

데이터 출처: KISA 피싱사이트 URL(공공데이터포털, 이용 제한 없음), PhishTank, Tranco, Common Crawl, 한국어 위키백과(CC BY-SA)

## 시험

```
cd server
.venv\Scripts\python -m pytest -q tests
```

## 글꼴
앱에 Pretendard 글꼴(SIL Open Font License 1.1)을 넣었다. 라이선스: `android/FONT_LICENSE_Pretendard.txt`

