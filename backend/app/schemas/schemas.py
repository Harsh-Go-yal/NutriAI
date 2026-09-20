from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class ProfileSchema(BaseModel):
    age: int
    gender: str
    height_cm: float
    weight_kg: float
    activity_level: str
    medical_conditions: List[str] = []

class GoalsSchema(BaseModel):
    goal_type: str
    target_calories: Optional[int] = None

class PreferencesSchema(BaseModel):
    diet_type: str
    cuisine_preference: str
    allergies: List[str] = []
    dislikes: List[str] = []

class GenerateDietPlanRequest(BaseModel):
    profile: ProfileSchema
    goals: GoalsSchema
    preferences: PreferencesSchema
    plan_length_days: int = 7

class GenerateRecommendationsRequest(BaseModel):
    user_id: int
    logged_today: List[Dict[str, Any]]
    recent_activity: Dict[str, Any]
    adherence_history: Dict[str, Any]
