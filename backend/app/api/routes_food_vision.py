import base64
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.groq_client import AgentGenerationError
from app.core.orchestrator import orchestrator
from app.database import get_db
from app.models.models import MealPhotoLog
from app.services.nutrition_service import nutrition_service

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}
MAX_BYTES = 8 * 1024 * 1024  # 8 MB -- comfortably above a phone photo


@router.post("/analyze")
async def analyze_meal_photo(
    file: UploadFile = File(...),
    user_id: int = Form(1),
    hint: str = Form(""),
    db: Session = Depends(get_db),
):
    """
    Photo -> ingredients -> measured nutrients.

    The response is deliberately not auto-logged: portion estimates from a
    single photo carry the bulk of the error, so the client shows the result
    for confirmation and calls /confirm to persist it.
    """
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported image type '{file.content_type}'. "
                   f"Use one of: {', '.join(sorted(ALLOWED_TYPES))}.",
        )

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(raw) > MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Image is {len(raw) // 1024 // 1024} MB; the limit is "
                   f"{MAX_BYTES // 1024 // 1024} MB.",
        )

    data_url = f"data:{file.content_type};base64,{base64.b64encode(raw).decode()}"

    try:
        result = await orchestrator.route(
            "food_vision",
            {"image_data_url": data_url, "user_hint": hint},
        )
    except AgentGenerationError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception:
        logger.exception("Food vision analysis failed.")
        raise HTTPException(status_code=500, detail="Internal server error")

    if not result.get("items") and not result.get("unresolved"):
        raise HTTPException(
            status_code=422,
            detail="No food could be identified in this image.",
        )

    try:
        entry = MealPhotoLog(user_id=user_id, analysis=result, confirmed=0)
        db.add(entry)
        db.commit()
        db.refresh(entry)
        result["log_id"] = entry.id
    except Exception:
        db.rollback()
        logger.exception("Could not persist photo analysis; returning it anyway.")

    return result


@router.post("/confirm")
async def confirm_meal_photo(payload: dict, db: Session = Depends(get_db)):
    """
    Persist a user-corrected analysis.

    `items` is [{name, portion_g}] as the user adjusted them; nutrients are
    recomputed from the database rather than trusted from the client.
    """
    log_id = payload.get("log_id")
    items = payload.get("items") or []

    entry = db.query(MealPhotoLog).filter(MealPhotoLog.id == log_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Photo log not found.")

    resolved = []
    for item in items:
        food = await nutrition_service.resolve(item.get("name", ""))
        if food:
            resolved.append(nutrition_service.scale(food, item.get("portion_g") or 0))

    totals = {}
    for field in ("calories", "protein_g", "carbs_g", "fat_g", "fiber_g"):
        values = [r[field] for r in resolved if r.get(field) is not None]
        totals[field] = round(sum(values), 2) if values else 0.0

    analysis = dict(entry.analysis or {})
    analysis["items"] = resolved
    analysis["totals"] = totals
    analysis["user_confirmed"] = True

    entry.analysis = analysis
    entry.confirmed = 1
    db.commit()
    db.refresh(entry)

    return {"log_id": entry.id, "items": resolved, "totals": totals}


@router.get("/sources")
async def data_sources():
    """Provenance for the nutrient numbers, for display in the UI."""
    return {
        "primary": nutrition_service.source_meta,
        "fallback": {
            "source": "USDA FoodData Central",
            "url": "https://fdc.nal.usda.gov/",
            "note": "Used only for foods absent from IFCT (prepared dishes, "
                    "non-Indian foods).",
        },
        "foods_loaded": len(nutrition_service.foods),
    }
