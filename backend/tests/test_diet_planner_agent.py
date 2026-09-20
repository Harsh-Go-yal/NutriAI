import pytest
from unittest.mock import patch, AsyncMock
from app.agents.diet_planner_agent import DietPlannerAgent

@pytest.mark.asyncio
async def test_diet_planner_agent():
    agent = DietPlannerAgent()
    
    mock_response = {
        "daily_calorie_target": 2000,
        "macro_targets": {"protein_g": 150, "carbs_g": 200, "fat_g": 66},
        "days": [
            {
                "day": 1,
                "meals": [
                    {
                        "slot": "breakfast",
                        "items": [{"name": "Oats", "portion_g": 100, "calories": 389}],
                        "total_calories": 389,
                        "swap_alternative": {"items": [{"name": "Poha", "portion_g": 100}], "note": "Equivalent carbs"}
                    }
                ]
            }
        ],
        "notes": ["Sample notes"]
    }
    
    with patch('app.core.groq_client.GroqClient.chat_json', new_callable=AsyncMock) as mock_chat_json:
        mock_chat_json.return_value = mock_response
        
        input_data = {
            "profile": {},
            "goals": {},
            "preferences": {},
            "plan_length_days": 1,
            "available_foods": []
        }
        
        result = await agent.run(input_data)
        
        assert result["daily_calorie_target"] == 2000
        assert len(result["days"]) == 1
        assert result["days"][0]["meals"][0]["slot"] == "breakfast"
