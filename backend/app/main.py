import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import engine, Base
import app.api.routes_diet_plan as routes_diet_plan
import app.api.routes_recommendations as routes_recommendations
import app.api.routes_health as routes_health
import app.api.routes_food_vision as routes_food_vision
import app.api.routes_insights as routes_insights
import app.api.routes_agent as routes_agent
import app.api.routes_gamification as routes_gamification
import app.api.routes_chat as routes_chat

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure tables are created on startup
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables verified/created.")
    except Exception as e:
        logger.warning(f"Could not connect to database on startup: {e}")
    yield

app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

@app.middleware("http")
async def collapse_slashes(request: Request, call_next):
    """
    Treat `//api/v1/...` as `/api/v1/...`.

    A base URL pasted with a trailing slash produces a doubled slash and a
    bare 404, which on a voice call looks like the tool simply not existing.
    Normalising here is cheaper than re-pasting four tool URLs every time the
    tunnel hands out a new hostname.
    """
    raw = request.scope.get("path", "")
    if raw.startswith("//"):
        request.scope["path"] = "/" + raw.lstrip("/")
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_health.router, prefix=settings.API_V1_STR, tags=["health"])
app.include_router(routes_diet_plan.router, prefix=f"{settings.API_V1_STR}/diet-plan", tags=["diet-plan"])
app.include_router(routes_recommendations.router, prefix=f"{settings.API_V1_STR}/recommendations", tags=["recommendations"])
app.include_router(routes_food_vision.router, prefix=f"{settings.API_V1_STR}/food-vision", tags=["food-vision"])
app.include_router(routes_insights.router, prefix=f"{settings.API_V1_STR}/insights", tags=["insights"])
app.include_router(routes_agent.router, prefix=f"{settings.API_V1_STR}/agent", tags=["agent"])
app.include_router(routes_gamification.router, prefix=f"{settings.API_V1_STR}/gamification", tags=["gamification"])
app.include_router(routes_chat.router, prefix=f"{settings.API_V1_STR}/chat", tags=["chat"])


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Log the body that failed validation.

    A voice agent's tool call fails silently from the caller's side -- the
    agent just carries on talking -- so without this the only signal is a
    bare 422 in the access log with no way to tell which field was wrong.
    """
    try:
        body = (await request.body()).decode("utf-8", "replace")[:1000]
    except Exception:
        body = "<unreadable>"
    logger.error(
        "422 on %s %s | errors=%s | body=%s",
        request.method, request.url.path, exc.errors(), body,
    )
    return JSONResponse(status_code=422,
                        content={"detail": exc.errors(), "received": body[:500]})
