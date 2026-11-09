---
title: KoK Smishing Check API
emoji: 🛡️
colorFrom: blue
colorTo: red
sdk: docker
app_port: 7860
pinned: false
---

# 스미싱 URL 탐색기 · 검사 서버

`POST /api/check {"url": "..."}` → 판정(safe/caution/danger/unknown), 점수, 이유
`GET /health` → 모델·목록 상태

판정 순서: 단축 URL 풀기(헤더만) → 피싱 목록 → 공식 도메인 → CANINE 점수 → 이유(규칙)

Space 설정(Settings → Variables and secrets):
- `MODEL_ID` = 학습한 모델 저장소 이름 (예: `team4/smishing-canine`)
- `HF_TOKEN` (Secret) = 모델 저장소가 비공개일 때만
