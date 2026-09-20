import copy

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from app.schemas.schemas import GenerateDietPlanRequest
from app.database import get_db
from app.core.orchestrator import orchestrator
from app.services.nutrition_service import nutrition_service
from app.models.models import User, MealPlan
from app.core.groq_client import AgentGenerationError

router = APIRouter()

@router.post("/generate")
async def generate_diet_plan(request: GenerateDietPlanRequest, db: Session = Depends(get_db)):
    # Prepare payload for agent
    payload = {
        "profile": request.profile.model_dump(),
        "goals": request.goals.model_dump(),
        "preferences": request.preferences.model_dump(),
        "plan_length_days": request.plan_length_days,
        "available_foods": nutrition_service.get_all_foods(
            diet_type=request.preferences.diet_type
        )
    }
    
    try:
        result = await orchestrator.route("diet_planner", payload)
        
        # Save to DB - mock a user id for now since auth is not required for demo
        user = db.query(User).first()
        if not user:
            user = User(
                name="Demo User",
                age=request.profile.age,
                gender=request.profile.gender,
                height_cm=request.profile.height_cm,
                weight_kg=request.profile.weight_kg,
                activity_level=request.profile.activity_level,
                medical_conditions=request.profile.medical_conditions,
                goal_type=request.goals.goal_type,
                target_calories=request.goals.target_calories,
                diet_type=request.preferences.diet_type,
                cuisine_preference=request.preferences.cuisine_preference,
                allergies=request.preferences.allergies,
                dislikes=request.preferences.dislikes
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        # Upsert Meal Plan for demo user
        meal_plan = db.query(MealPlan).filter(MealPlan.user_id == user.id).first()
        if not meal_plan:
            meal_plan = MealPlan(user_id=user.id, plan_data=result)
            db.add(meal_plan)
        else:
            meal_plan.plan_data = result
        db.commit()
        db.refresh(meal_plan)
        
        return result
    except AgentGenerationError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/current")
async def current_plan(user_id: int = 1, db: Session = Depends(get_db)):
    """
    The user's active plan.

    My Plan previously relied on router state passed at navigation time, so a
    refresh lost the plan entirely. This lets the page load it on its own.
    """
    row = (db.query(MealPlan)
           .filter(MealPlan.user_id == user_id)
           .order_by(MealPlan.created_at.desc())
           .first())
    if not row or not row.plan_data:
        return {"has_plan": False, "plan": None,
                "message": "No plan saved yet. Ask the assistant for a meal plan."}
    return {"has_plan": True, "plan": row.plan_data,
            "created_at": row.created_at.isoformat() if row.created_at else None}


@router.delete("/current")
async def delete_plan(user_id: int = 1, db: Session = Depends(get_db)):
    """Discard the saved plan."""
    rows = db.query(MealPlan).filter(MealPlan.user_id == user_id).all()
    for row in rows:
        db.delete(row)
    db.commit()
    return {"deleted": len(rows)}


@router.patch("/current")
async def update_plan(payload: dict, user_id: int = 1,
                      db: Session = Depends(get_db)):
    """
    Edit one meal of the saved plan.

    Body: {"day": 1, "slot": "dinner", "items": [{"name": ..., "portion_g": ...}]}

    Calories are recomputed from the food tables rather than taken from the
    caller, so an edited meal carries the same provenance as a generated one.
    """
    row = (db.query(MealPlan)
           .filter(MealPlan.user_id == user_id)
           .order_by(MealPlan.created_at.desc())
           .first())
    if not row or not row.plan_data:
        raise HTTPException(status_code=404, detail="No saved plan to update.")

    day_no = int(payload.get("day") or 1)
    slot = (payload.get("slot") or "").lower()
    items = payload.get("items") or []
    if not slot or not items:
        raise HTTPException(status_code=400,
                            detail="Provide 'slot' and a non-empty 'items' list.")

    resolved, unresolved, total = [], [], 0.0
    for item in items:
        food = await nutrition_service.resolve(item.get("name", ""))
        grams = item.get("portion_g") or 0
        if not food or grams <= 0:
            unresolved.append(item.get("name"))
            continue
        scaled = nutrition_service.scale(food, grams)
        total += scaled.get("calories") or 0
        resolved.append({"name": scaled["name"], "portion_g": grams,
                         "calories": scaled.get("calories"),
                         "source": scaled.get("source")})

    if not resolved:
        raise HTTPException(
            status_code=422,
            detail=f"None of those foods could be resolved: {unresolved}")

    # Deep copy, not dict(): a shallow copy shares the nested day/meal
    # objects with SQLAlchemy's change-detection snapshot, so mutating them
    # mutates the snapshot too, the column compares equal, and no UPDATE is
    # emitted. The write silently does nothing.
    plan = copy.deepcopy(row.plan_data)
    days = plan.get("days") or []
    day = next((d for d in days if d.get("day") == day_no), None)
    if not day:
        raise HTTPException(status_code=404, detail=f"Day {day_no} not in plan.")

    meals = day.get("meals") or []
    meal = next((m for m in meals if (m.get("slot") or "").lower() == slot), None)
    if meal:
        meal["items"] = resolved
        meal["total_calories"] = round(total)
        meal["edited_by_user"] = True
    else:
        meals.append({"slot": slot, "items": resolved,
                      "total_calories": round(total),
                      "swap_alternative": {"items": [], "note": ""},
                      "edited_by_user": True})
        day["meals"] = meals

    row.plan_data = plan
    flag_modified(row, "plan_data")   # belt and braces for the JSON column
    db.commit()
    db.refresh(row)

    return {"updated": True, "day": day_no, "slot": slot,
            "items": resolved, "total_calories": round(total),
            "unresolved": unresolved, "plan": plan}
