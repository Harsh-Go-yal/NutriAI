"""
Profile & Health Agent -- the onboarding assessment.

Ported from the parallel build (which ran Qwen via Ollama) onto OpenAI, with
one deliberate change: BMI, BMR, TDEE and macro targets are computed here in
Python, not asked of the model. Those are closed-form equations, and a model
that "calculates" Mifflin-St Jeor produces a number that looks right and
sometimes isn't. The model is used only for the qualitative half -- risk
flags, strengths, and framing -- which is what it is actually good at.
"""
import logging
from typing import Any, Dict

from app.agents.base_agent import BaseAgent
from app.config import settings
from app.core.groq_client import groq_client
from app.services.fitness_service import fitness_service
from app.services.micronutrient_service import micronutrient_service

logger = logging.getLogger(__name__)

PROFILE_SYSTEM_PROMPT = """
You are a nutrition assessor for an Indian dietary app.

The numbers have already been computed for you and are supplied in the input:
BMI, BMR, TDEE, calorie target and macro targets. Do NOT recalculate them and
do NOT contradict them. Your job is the judgement around them.

Return:
- health_risks: risk factors visible from this profile (weight, activity,
  stated conditions). Phrase as risk factors to discuss with a doctor, never
  as a diagnosis.
- health_strengths: what this person already has going for them. Be specific,
  not flattering.
- dietary_focus: 3-5 concrete, Indian-food-specific priorities
  ("swap white rice for brown rice or millets at lunch"), not generic advice.
- supplement_notes: only where genuinely indicated, and always framed as
  "discuss with a clinician". Vegetarian Indian diets commonly warrant a B12
  conversation.
- motivation_message: one warm, plain sentence. No hype, no exclamation marks.

Never give a diagnosis, never name a drug or dose, and never promise a
weight-loss rate. If the profile suggests something clinical, say it needs a
doctor rather than working around it.
"""


class ProfileHealthAgent(BaseAgent):
    def __init__(self):
        self.name = "profile_health"
        self.model_id = settings.PROFILE_HEALTH_MODEL
        self.system_prompt = PROFILE_SYSTEM_PROMPT

    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        profile = input_data.get("profile") or input_data

        weight = float(profile.get("weight_kg") or 60)
        height = float(profile.get("height_cm") or 165)
        age = int(profile.get("age") or 30)
        gender = profile.get("gender") or "female"

        # --- deterministic half -------------------------------------------
        targets = fitness_service.targets(
            weight_kg=weight, height_cm=height, age=age, gender=gender,
            activity_level=profile.get("activity_level") or "moderate",
            goal_type=profile.get("goal_type") or "maintenance",
            target_calories=profile.get("target_calories"),
        )

        bmi = round(weight / ((height / 100) ** 2), 1)
        rda = micronutrient_service.rda_for(
            age=age, gender=gender, life_stage=profile.get("life_stage"))

        computed = {
            "bmi": bmi,
            "bmi_category": self._bmi_category(bmi),
            "bmr_calories": targets["bmr_kcal"],
            "tdee_calories": targets["tdee_kcal"],
            "recommended_calories": targets["daily_calorie_target"],
            "macro_targets": targets["macro_targets"],
            "hydration_ml": targets["hydration_ml"],
            "protein_per_kg": targets["protein_per_kg"],
            "rda_profile": rda["profile"],
            "micronutrient_targets": rda["rda"],
        }

        # --- model half ----------------------------------------------------
        response_schema = {
            "type": "object",
            "properties": {
                "health_risks": {"type": "array", "items": {"type": "string"}},
                "health_strengths": {"type": "array", "items": {"type": "string"}},
                "dietary_focus": {"type": "array", "items": {"type": "string"}},
                "supplement_notes": {"type": "array", "items": {"type": "string"}},
                "motivation_message": {"type": "string"},
            },
            "required": ["health_risks", "health_strengths", "dietary_focus",
                         "supplement_notes", "motivation_message"],
        }

        try:
            qualitative = await groq_client.chat_json(
                system_prompt=self.system_prompt,
                user_payload={"profile": profile, "computed": computed},
                response_schema=response_schema,
                model=self.model_id,
            )
        except Exception as e:
            # The computed half is the part that matters; degrade rather than fail.
            logger.warning(f"Profile agent qualitative step failed: {e}")
            qualitative = {
                "health_risks": [], "health_strengths": [], "dietary_focus": [],
                "supplement_notes": [],
                "motivation_message": "Your targets are ready below.",
            }

        return {
            **computed,
            **qualitative,
            "computation_method": (
                "BMI, BMR (Mifflin-St Jeor), TDEE and macros computed in code; "
                "ICMR-NIN RDA 2020 for micronutrients. Only the qualitative "
                "commentary is model-generated."
            ),
            "disclaimer": "Nutrition information, not medical advice. Confirm "
                          "anything clinical with a doctor or registered dietitian.",
        }

    @staticmethod
    def _bmi_category(bmi: float) -> str:
        """WHO Asian-Indian cut-offs -- lower than the international ones,
        which is the point: standard thresholds under-flag risk in Indians."""
        if bmi < 18.5:
            return "Underweight"
        if bmi < 23:
            return "Normal"
        if bmi < 25:
            return "At risk"
        if bmi < 30:
            return "Obese I"
        return "Obese II"
