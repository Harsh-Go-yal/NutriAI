from typing import Dict, Any
from app.agents.base_agent import BaseAgent
from app.core.groq_client import groq_client
from app.config import settings
from app.agents.prompts.recommendation_prompt import RECOMMENDATION_SYSTEM_PROMPT

class RecommendationAgent(BaseAgent):
    def __init__(self):
        self.name = "recommendation"
        self.model_id = settings.RECOMMENDATION_MODEL
        self.system_prompt = RECOMMENDATION_SYSTEM_PROMPT

    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        response_schema = {
            "type": "object",
            "properties": {
                "recommendations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "priority": {"type": "string"},
                            "message": {"type": "string"},
                            "reason": {"type": "string"}
                        },
                        "required": ["type", "priority", "message", "reason"]
                    }
                },
                "summary": {"type": "string"}
            },
            "required": ["recommendations", "summary"]
        }

        result = await groq_client.chat_json(
            system_prompt=self.system_prompt,
            user_payload=input_data,
            response_schema=response_schema,
            model=self.model_id
        )

        if "recommendations" not in result:
            result["recommendations"] = []
        if "summary" not in result or not result["summary"]:
            result["summary"] = "Here are your nutrition insights based on your recent activity and meal logs."

        return result
