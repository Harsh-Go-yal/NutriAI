import json
import logging
from openai import AsyncOpenAI
import openai
from app.config import settings

logger = logging.getLogger(__name__)


def _unwrap_schema_echo(data):
    """
    Undo the model echoing the schema instead of an instance.

    Because the schema is appended to the system prompt, models occasionally
    reply with the schema shape itself -- {"type": "object", "properties":
    {...}} -- with the real values sitting inside `properties`. That parses as
    valid JSON, so nothing errors; the caller just sees no data. Detect that
    specific shape and return the inner object.
    """
    if not isinstance(data, dict):
        return data
    looks_like_schema = (
        data.get("type") == "object"
        and isinstance(data.get("properties"), dict)
    )
    if not looks_like_schema:
        return data

    inner = data["properties"]
    # A genuine payload's values are data; an un-substituted schema's values
    # are still type descriptors. Only unwrap when at least one value has
    # actually been filled in.
    substituted = any(
        not (isinstance(v, dict) and "type" in v and len(v) <= 3)
        for v in inner.values()
    )
    return inner if substituted else data


class AgentGenerationError(Exception):
    """Exception raised when an agent fails to generate a valid response."""
    pass

class LLMClient:
    def __init__(self):
        if not settings.OPENAI_API_KEY:
            logger.warning("OPENAI_API_KEY is not set. LLM client will fail on calls.")
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, max_retries=2)

    async def chat_json(
        self, system_prompt: str, user_payload: dict, response_schema: dict, model: str
    ) -> dict:
        """
        Calls the OpenAI API enforcing a JSON return format.
        """
        # Append schema description to system prompt for guaranteed adherence
        enhanced_system_prompt = (
            f"{system_prompt}\n\n"
            f"You MUST respond ONLY with a JSON object matching this schema:\n"
            f"{json.dumps(response_schema, indent=2)}"
        )

        messages = [
            {"role": "system", "content": enhanced_system_prompt},
            {"role": "user", "content": json.dumps(user_payload)},
        ]

        try:
            chat_completion = await self.client.chat.completions.create(
                messages=messages,
                model=model,
                temperature=0.2,
                response_format={"type": "json_object"},
                timeout=120.0
            )
            response_content = chat_completion.choices[0].message.content
            return _unwrap_schema_echo(json.loads(response_content))

        except openai.APIConnectionError as e:
            logger.error(f"OpenAI API connection error: {e}")
            raise AgentGenerationError("Failed to connect to the LLM service.") from e
        except openai.RateLimitError as e:
            logger.error(f"OpenAI API rate limit error: {e}")
            raise AgentGenerationError("Rate limit exceeded. Please try again later.") from e
        except openai.APIStatusError as e:
            logger.error(f"OpenAI API status error: {e.status_code} - {e.response}")
            raise AgentGenerationError(f"LLM service returned an error: {e.status_code}") from e
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            raise AgentGenerationError("Agent returned invalid JSON.") from e
        except Exception as e:
            logger.error(f"Unexpected error in LLM client: {e}")
            raise AgentGenerationError(f"Generation error: {str(e)}") from e

    async def chat_json_vision(
        self, system_prompt: str, image_data_url: str, response_schema: dict,
        model: str, user_text: str = ""
    ) -> dict:
        """
        Same contract as chat_json, but the user turn carries an image.

        `image_data_url` must be a data URL ("data:image/jpeg;base64,...").
        """
        enhanced_system_prompt = (
            f"{system_prompt}\n\n"
            f"You MUST respond ONLY with a JSON object matching this schema:\n"
            f"{json.dumps(response_schema, indent=2)}"
        )

        content = [{"type": "image_url", "image_url": {"url": image_data_url}}]
        if user_text:
            content.insert(0, {"type": "text", "text": user_text})

        messages = [
            {"role": "system", "content": enhanced_system_prompt},
            {"role": "user", "content": content},
        ]

        try:
            chat_completion = await self.client.chat.completions.create(
                messages=messages,
                model=model,
                temperature=0.1,
                response_format={"type": "json_object"},
                timeout=120.0,
            )
            return _unwrap_schema_echo(
                json.loads(chat_completion.choices[0].message.content))

        except openai.APIConnectionError as e:
            logger.error(f"OpenAI API connection error: {e}")
            raise AgentGenerationError("Failed to connect to the LLM service.") from e
        except openai.RateLimitError as e:
            logger.error(f"OpenAI API rate limit error: {e}")
            raise AgentGenerationError("Rate limit exceeded. Please try again later.") from e
        except openai.APIStatusError as e:
            logger.error(f"OpenAI API status error: {e.status_code} - {e.response}")
            raise AgentGenerationError(f"LLM service returned an error: {e.status_code}") from e
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse vision response as JSON: {e}")
            raise AgentGenerationError("Agent returned invalid JSON.") from e
        except Exception as e:
            logger.error(f"Unexpected error in vision call: {e}")
            raise AgentGenerationError(f"Generation error: {str(e)}") from e


# Kept as GroqClient alias so existing imports/tests keep working
GroqClient = LLMClient
groq_client = LLMClient()
