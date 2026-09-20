import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Nutrition AI Assistant"
    API_V1_STR: str = "/api/v1"
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/nutrition_ai")
    
    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # OpenAI API
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    DIET_PLANNER_MODEL: str = os.getenv("DIET_PLANNER_MODEL", "gpt-4o-mini")
    RECOMMENDATION_MODEL: str = os.getenv("RECOMMENDATION_MODEL", "gpt-4o-mini")
    FOOD_VISION_MODEL: str = os.getenv("FOOD_VISION_MODEL", "gpt-4o")
    PROFILE_HEALTH_MODEL: str = os.getenv("PROFILE_HEALTH_MODEL", "gpt-4o-mini")
    PROGRESS_MODEL: str = os.getenv("PROGRESS_MODEL", "gpt-4o-mini")

    # USDA FoodData Central (fallback nutrient source).
    # DEMO_KEY works without signup but is capped at 30 req/hour.
    USDA_API_KEY: str = os.getenv("USDA_API_KEY", "DEMO_KEY")

    # Sarvam Voice Agents (outbound calls, Indian languages)
    SARVAM_API_KEY: str = os.getenv("SARVAM_API_KEY", "")
    SARVAM_AGENT_ID: str = os.getenv("SARVAM_AGENT_ID", "")
    SARVAM_ORG_ID: str = os.getenv("SARVAM_ORG_ID", "")
    SARVAM_WORKSPACE_ID: str = os.getenv("SARVAM_WORKSPACE_ID", "")
    SARVAM_FROM_NUMBER: str = os.getenv("SARVAM_FROM_NUMBER", "")
    # Voice Agents keys are a separate credential from the core Sarvam API key
    # and are not interchangeable.
    SARVAM_VOICE_API_KEY: str = os.getenv("SARVAM_VOICE_API_KEY", "")
    SARVAM_CONNECTION_ID: str = os.getenv("SARVAM_CONNECTION_ID", "")
    SARVAM_APP_VERSION: int = int(os.getenv("SARVAM_APP_VERSION", "1"))

    # Shared secret the voice agent presents when calling our tool endpoints.
    # Empty means the tool endpoints stay disabled (fail closed).
    AGENT_TOOL_KEY: str = os.getenv("AGENT_TOOL_KEY", "")

    # Messaging
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_WHATSAPP_FROM: str = os.getenv("TWILIO_WHATSAPP_FROM", "")
    TWILIO_SMS_FROM: str = os.getenv("TWILIO_SMS_FROM", "")
    
    class Config:
        case_sensitive = True
        env_file = ".env"
        extra = "ignore"

settings = Settings()
