"""
Endpoints for the micronutrient, household, fitness, safety and cost layers.

Everything here is deterministic: no LLM is consulted. The vision agent is the
only model call in the photo flow, and it never produces a nutrient number.
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.clinical_safety_service import clinical_safety_service
from app.services.cost_optimizer_service import cost_optimizer_service
from app.services.fitness_service import fitness_service
from app.services.household_service import household_service
from app.services.micronutrient_service import RDA, micronutrient_service
from app.services.nutrition_service import nutrition_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class FoodItem(BaseModel):
    name: str
    portion_g: float


class MemberSchema(BaseModel):
    name: str
    age: Optional[int] = None
    gender: str = "female"
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    activity_level: str = "moderate"
    life_stage: Optional[str] = None          # pregnant | lactating
    medical_conditions: List[str] = []
    medications: List[str] = []


class MicronutrientRequest(BaseModel):
    items: List[FoodItem]
    age: Optional[int] = None
    gender: str = "female"
    life_stage: Optional[str] = None
    tea_coffee_timing: Optional[str] = None   # with_meal | within_hour | separated
    days: int = 1


class HouseholdRequest(BaseModel):
    items: List[FoodItem]
    members: List[MemberSchema]
    shares: Optional[Dict[str, float]] = None
    tea_coffee_timing: Optional[str] = None


class CostRequest(BaseModel):
    gaps: Dict[str, float] = Field(
        ..., description="nutrient key -> amount still needed, e.g. "
                         "{'protein_g': 40, 'iron_mg': 8}")
    budget: Optional[float] = None
    diet_type: Optional[str] = None
    exclude: List[str] = []


class FitnessRequest(BaseModel):
    weight_kg: float
    height_cm: float
    age: int
    gender: str = "male"
    activity_level: str = "moderate"
    goal_type: str = "maintenance"
    target_calories: Optional[int] = None
    items: List[FoodItem] = []
    steps: Optional[int] = None
    workout_minutes: Optional[int] = None
    workout_intensity: Optional[str] = None


class SafetyRequest(BaseModel):
    items: List[FoodItem] = []
    conditions: List[str] = []
    medications: List[str] = []
    question: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _resolve(items: List[FoodItem]) -> Dict[str, Any]:
    """Resolve names to measured foods, reporting what could not be matched."""
    resolved, unresolved = [], []
    for item in items:
        food = await nutrition_service.resolve(item.name)
        if not food:
            unresolved.append(item.name)
            continue
        scaled = nutrition_service.scale(food, item.portion_g)
        scaled["requested_as"] = item.name
        scaled["match_confidence"] = food.get("confidence")
        resolved.append(scaled)
    return {"resolved": resolved, "unresolved": unresolved}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/micronutrients")
async def micronutrients(req: MicronutrientRequest):
    """Hidden-hunger check: intake vs ICMR RDA, plus absorption modelling."""
    found = await _resolve(req.items)
    if not found["resolved"]:
        raise HTTPException(
            status_code=422,
            detail=f"None of these foods could be resolved: {found['unresolved']}",
        )

    assessment = micronutrient_service.assess(
        found["resolved"], age=req.age, gender=req.gender,
        life_stage=req.life_stage, days=req.days,
        context={"tea_coffee_timing": req.tea_coffee_timing},
    )
    assessment["unresolved"] = found["unresolved"]
    assessment["items"] = found["resolved"]
    return assessment


@router.post("/household")
async def household(req: HouseholdRequest):
    """One pot, per-person nutrition against each member's own RDA."""
    found = await _resolve(req.items)
    if not found["resolved"]:
        raise HTTPException(status_code=422, detail="No foods could be resolved.")

    try:
        result = household_service.split(
            found["resolved"],
            [m.model_dump() for m in req.members],
            shares=req.shares,
            context={"tea_coffee_timing": req.tea_coffee_timing},
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result["unresolved"] = found["unresolved"]
    return result


@router.post("/optimize-cost")
async def optimize_cost(req: CostRequest):
    """Cheapest basket of foods that closes the given nutrient gaps."""
    return cost_optimizer_service.optimize(
        gaps=req.gaps, budget=req.budget,
        diet_type=req.diet_type, exclude=req.exclude,
    )


@router.post("/fitness")
async def fitness(req: FitnessRequest):
    """Energy/macro targets, leucine check, and activity adjustment."""
    targets = fitness_service.targets(
        req.weight_kg, req.height_cm, req.age, req.gender,
        req.activity_level, req.goal_type, req.target_calories,
    )

    out: Dict[str, Any] = {"targets": targets}

    if req.items:
        found = await _resolve(req.items)
        out["protein_quality"] = fitness_service.meal_protein_quality(
            found["resolved"])
        out["unresolved"] = found["unresolved"]

    if req.steps is not None or req.workout_minutes is not None:
        out["activity"] = fitness_service.activity_adjustment(
            targets,
            {"steps": req.steps, "workout_minutes": req.workout_minutes,
             "workout_intensity": req.workout_intensity},
        )

    return out


@router.post("/safety")
async def safety(req: SafetyRequest):
    """Clinical guardrail screen. A blocking finding must withhold advice."""
    found = await _resolve(req.items) if req.items else {"resolved": [],
                                                         "unresolved": []}
    return clinical_safety_service.screen(
        items=found["resolved"],
        conditions=req.conditions,
        medications=req.medications,
        free_text=req.question,
    )


@router.get("/rda")
async def rda_reference():
    """The RDA table the app judges everything against, for transparency."""
    return {
        "source": "ICMR-NIN, Nutrient Requirements for Indians (RDA and EAR), 2020",
        "profiles": RDA,
        "note": "Values are per day. Iron adequacy is judged on absorbed "
                "iron, not the amount on the plate.",
    }


@router.get("/sources")
async def sources():
    """Provenance for every number the app produces."""
    return {
        "food_composition": nutrition_service.source_meta,
        "fallback": "USDA FoodData Central (foods absent from IFCT)",
        "rda": "ICMR-NIN RDA 2020",
        "absorption_model": "Hurrell & Egli, Am J Clin Nutr 2010 (iron "
                            "bioavailability); ascorbate, polyphenol, calcium "
                            "and phytate factors",
        "protein_guidance": "ISSN position stands; leucine threshold ~2.5 g/meal",
        "prices": cost_optimizer_service.meta,
        "foods_loaded": len(nutrition_service.foods),
        "priced_foods": len(cost_optimizer_service.priced_foods),
        "known_gaps": nutrition_service.source_meta.get("known_gaps"),
    }
