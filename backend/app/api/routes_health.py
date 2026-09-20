import time
import httpx
from fastapi import APIRouter
from app.config import settings

router = APIRouter()

@router.get("")
@router.get("/")
@router.get("/health")
async def health_check():
    # Attempt a fast check with Groq to ensure key works
    llm_status = "ok"
    try:
        if settings.OPENAI_API_KEY:
            headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}
            async with httpx.AsyncClient() as client:
                res = await client.get("https://api.openai.com/v1/models", headers=headers, timeout=10.0)
                if res.status_code != 200:
                    llm_status = "invalid_key_or_error"
        else:
            llm_status = "no_key"
    except Exception:
        llm_status = "unreachable"

    return {
        "status": "ok",
        "timestamp": time.time(),
        "llm_api_status": llm_status
    }
