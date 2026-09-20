from typing import Dict, Any
from app.agents.base_agent import BaseAgent
from app.core.groq_client import groq_client
from app.config import settings
from app.agents.prompts.diet_planner_prompt import DIET_PLANNER_SYSTEM_PROMPT

class DietPlannerAgent(BaseAgent):
    def __init__(self):
        self.name = "diet_planner"
        self.model_id = settings.DIET_PLANNER_MODEL
        self.system_prompt = DIET_PLANNER_SYSTEM_PROMPT

    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        response_schema = {
            "type": "object",
            "properties": {
                "daily_calorie_target": {"type": "integer"},
                "macro_targets": {
                    "type": "object",
                    "properties": {
                        "protein_g": {"type": "integer"},
                        "carbs_g": {"type": "integer"},
                        "fat_g": {"type": "integer"}
                    },
                    "required": ["protein_g", "carbs_g", "fat_g"]
                },
                "days": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "day": {"type": "integer"},
                            "meals": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "slot": {"type": "string"},
                                        "items": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "name": {"type": "string"},
                                                    "portion_g": {"type": "integer"},
                                                    "calories": {"type": "integer"}
                                                },
                                                "required": ["name", "portion_g", "calories"]
                                            }
                                        },
                                        "total_calories": {"type": "integer"},
                                        "swap_alternative": {
                                            "type": "object",
                                            "properties": {
                                                "items": {
                                                    "type": "array",
                                                    "items": {
                                                        "type": "object",
                                                        "properties": {
                                                            "name": {"type": "string"},
                                                            "portion_g": {"type": "integer"}
                                                        },
                                                        "required": ["name", "portion_g"]
                                                    }
                                                },
                                                "note": {"type": "string"}
                                            },
                                            "required": ["items", "note"]
                                        }
                                    },
                                    "required": ["slot", "items", "total_calories", "swap_alternative"]
                                }
                            }
                        },
                        "required": ["day", "meals"]
                    }
                },
                "notes": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            },
            "required": ["daily_calorie_target", "macro_targets", "days", "notes"]
        }

        result = await groq_client.chat_json(
            system_prompt=self.system_prompt,
            user_payload=input_data,
            response_schema=response_schema,
            model=self.model_id
        )

        # Normalize schema if model uses alternative naming
        if "days" not in result and "plan" in result:
            result["days"] = result.pop("plan")
        if "notes" not in result:
            result["notes"] = []
        if "macro_targets" not in result:
            result["macro_targets"] = {"protein_g": 0, "carbs_g": 0, "fat_g": 0}

        return result
