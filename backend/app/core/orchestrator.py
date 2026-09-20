import time
import logging
from typing import Dict, Any
from app.agents.diet_planner_agent import DietPlannerAgent
from app.agents.food_vision_agent import FoodVisionAgent
from app.agents.profile_health_agent import ProfileHealthAgent
from app.agents.progress_feedback_agent import ProgressFeedbackAgent
from app.agents.recommendation_agent import RecommendationAgent
from app.core.groq_client import AgentGenerationError

logger = logging.getLogger(__name__)

class Orchestrator:
    def __init__(self):
        # Register implemented agents
        self.registry = {
            "diet_planner": DietPlannerAgent(),
            "recommendation": RecommendationAgent(),
            "food_vision": FoodVisionAgent(),
            "profile_health": ProfileHealthAgent(),
            "progress_feedback": ProgressFeedbackAgent(),
            # nutrition_analysis is deliberately not an LLM agent -- it is a
            # deterministic lookup against IFCT 2017 / USDA in NutritionService.
        }

    async def route(self, agent_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Routes a request to the appropriate agent and logs execution details.
        """
        if agent_name not in self.registry:
            raise ValueError(f"Agent '{agent_name}' not found in registry.")

        agent = self.registry[agent_name]
        start_time = time.time()
        
        logger.info(f"Routing request to {agent_name} agent...")
        
        try:
            result = await agent.run(payload)
            latency = time.time() - start_time
            logger.info(f"Agent {agent_name} execution successful. Latency: {latency:.2f}s")
            # In the future, Progress & Feedback agent could consume this log/event stream
            return result
            
        except AgentGenerationError as e:
            latency = time.time() - start_time
            logger.error(f"Agent {agent_name} execution failed after {latency:.2f}s: {e}")
            raise e

orchestrator = Orchestrator()
