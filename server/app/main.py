"""검사 서버 (FastAPI)."""
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .checker import Checker
from .normalize import extract_urls

app = FastAPI(title='스미싱 URL 탐색기 API', version='0.1.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in os.getenv('CORS_ORIGINS', '*').split(',') if o],
    allow_methods=['GET', 'POST'],
    allow_headers=['*'],
)
checker = Checker()


class CheckIn(BaseModel):
    url: str = Field(..., max_length=2048, description='검사할 링크')


class TextIn(BaseModel):
    text: str = Field(..., max_length=5000, description='문자 전체(보조 웹용)')


@app.get('/health')
def health():
    s = checker.scorer
    return {'ok': True, 'model': s.model_id if s.ready else None, 'model_error': s.error or None,
            'lists': checker.lists.stats()}


@app.post('/api/check')
async def check(body: CheckIn):
    try:
        return await checker.check(body.url)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post('/api/check-text')
async def check_text(body: TextIn):
    """문자 전체를 받아 링크마다 검사(원문은 저장하지 않음)."""
    urls = extract_urls(body.text)[:5]
    if not urls:
        raise HTTPException(400, '링크를 찾지 못했습니다')
    results = []
    for u in urls:
        try:
            results.append(await checker.check(u))
        except ValueError:
            continue
    return {'results': results}
