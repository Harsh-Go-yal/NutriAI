from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.schemas.schemas import GenerateRecommendationsRequest
from app.database import get_db
from app.core.orchestrator import orchestrator
from app.models.models import MealPlan, Recommendation
from app.core.groq_client import AgentGenerationError

router = APIRouter()

@router.post("/generate")
async def generate_recommendations(request: GenerateRecommendationsRequest, db: Session = Depends(get_db)):
    # Retrieve the user's active plan
    meal_plan = db.query(MealPlan).filter(MealPlan.user_id == request.user_id).order_by(MealPlan.created_at.desc()).first()
    
    if not meal_plan:
        raise HTTPException(status_code=404, detail="No active diet plan found for this user.")
        
    # Prepare payload for recommendation agent
    payload = {
        "active_plan_summary": meal_plan.plan_data.get("days", [])[0] if meal_plan.plan_data.get("days") else {}, # Simplifying for demo to day 1
        "logged_today": request.logged_today,
        "recent_activity": request.recent_activity,
        "adherence_history": request.adherence_history
    }
    
    try:
        result = await orchestrator.route("recommendation", payload)
        
        # Save to DB
        recommendation_entry = Recommendation(
            user_id=request.user_id,
            recommendation_data=result
        )
        db.add(recommendation_entry)
        db.commit()
        db.refresh(recommendation_entry)
        
        return result
    except AgentGenerationError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
