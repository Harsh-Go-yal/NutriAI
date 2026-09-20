import pytest
from unittest.mock import patch, AsyncMock
from app.agents.recommendation_agent import RecommendationAgent

@pytest.mark.asyncio
async def test_recommendation_agent():
    agent = RecommendationAgent()
    
    mock_response = {
        "recommendations": [
            {
                "type": "adjustment",
                "priority": "high",
                "message": "You missed breakfast, try to add a snack later.",
                "reason": "Calorie deficit"
            }
        ],
        "summary": "Overall on track, just one missed meal."
    }
    
    with patch('app.core.groq_client.GroqClient.chat_json', new_callable=AsyncMock) as mock_chat_json:
        mock_chat_json.return_value = mock_response
        
        input_data = {
            "active_plan_summary": {},
            "logged_today": [],
            "recent_activity": {},
            "adherence_history": {}
        }
        
        result = await agent.run(input_data)
        
        assert len(result["recommendations"]) == 1
        assert result["recommendations"][0]["priority"] == "high"
        assert result["summary"] == "Overall on track, just one missed meal."
