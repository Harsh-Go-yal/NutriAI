"""
Sarvam Voice Agents: outbound calls, and the config to paste into the console.

Two different auth headers are in play and mixing them up is the usual first
failure:
  - core model APIs (STT/TTS/translate/LID) -> `api-subscription-key`
  - Voice Agents / outbound app APIs         -> `X-API-Key`

The agent itself is built in Sarvam's console, not here. What this file owns
is (a) triggering a call and (b) generating the exact system prompt and tool
schemas to paste in, so the console config and this backend cannot drift.
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

SARVAM_CORE_API = "https://api.sarvam.ai"
SARVAM_OUTBOUND_API = "https://apps.sarvam.ai/api/outbounds"

DEFAULT_LANGUAGE = "en-IN"

# Sarvam's outbound API wants a language *name*, not a BCP-47 code -- passing
# "hi-IN" returns 422 Invalid Parameter.
LANGUAGE_NAMES = {
    "en-IN": "English", "hi-IN": "Hindi", "mr-IN": "Marathi",
    "ta-IN": "Tamil", "te-IN": "Telugu", "bn-IN": "Bengali",
    "gu-IN": "Gujarati", "kn-IN": "Kannada", "ml-IN": "Malayalam",
    "pa-IN": "Punjabi", "od-IN": "Odia",
}


def language_name(code: str) -> str:
    """Accept either a code or an already-correct name."""
    if not code:
        return "English"
    if code in LANGUAGE_NAMES.values():
        return code
    return LANGUAGE_NAMES.get(code, "English")


SUPPORTED_LANGUAGES = [
    "en-IN", "hi-IN", "mr-IN", "ta-IN", "te-IN", "bn-IN",
    "gu-IN", "kn-IN", "ml-IN", "pa-IN", "od-IN",
]


AGENT_SYSTEM_PROMPT = """\
You are the NutriAI diet assistant, calling in India. Keep it short: this is a
phone call, not a report.

WHO YOU ARE TALKING TO
The user set up this call themselves and chose the time. They may answer in
Hindi, Marathi, Tamil, or English, or mix them. Reply in whatever language
they use.

IF THEY ASK WHAT TO EAT
"What should I have for lunch?", "aaj dinner mein kya khau?" -- call
`get_plan_for_slot` and read back its `spoken_reply`. That is their own saved
plan. Never invent a meal: if they have no plan, the tool says so, and you
offer to log whatever they are actually eating instead.

WHAT TO DO ON EVERY CALL
1. Call `get_call_context` first. It tells you the meal slot, what is already
   logged, and the one number that matters right now. Do not guess any of it.
2. Ask what they ate and roughly how much. Accept everyday quantities -- "two
   roti", "ek katori dal", "half plate rice". Convert to grams yourself:
   the food tables list DRY weights for grains and pulses, so convert cooked
   portions back: 1 roti = 40 g, 1 katori cooked dal = 30 g dry dal,
   1 katori cooked rice = 50 g raw rice, 1 katori sabzi = 100 g,
   1 cup milk = 200 g, 1 katori curd = 150 g.
3. Call `log_meal` with each item and its portion in grams.
4. Tell them the single number that came back in `spoken_reply`. One number,
   one instruction. Do not read out the whole plan.
5. Ask if they want anything changed, then end the call.

IF THEY ASK HOW THEY ARE DOING
Questions like "kitna bacha hai?", "how many calories left?", "am I on track?"
must be answered with `get_day_state`, not from memory, because the numbers in
`get_call_context` were read before anything was logged this call. It returns
`spoken_reply` -- read that out.

Do NOT call `get_day_state` routinely after `log_meal`. `log_meal` already
returns its own up-to-date `spoken_reply`, and an extra round-trip is dead air
on a phone call. Call it only when they actually ask.

HARD RULES
- Never invent calorie, protein or nutrient numbers. Every number you say must
  have come from a tool response in this call. If a tool fails, say you will
  send it as a message instead.
- If the user mentions a medical condition, medication, pregnancy, or asks
  anything clinical, call `safety_check` before responding. If it returns a
  blocking result, read that action out and offer a dietitian. Do not advise.
- Never tell anyone to change a medication or a dose.
- If they ask to stop being called, confirm it and tell them it is off. Do not
  argue or try to talk them out of it.
- Do not moralise about what they ate. If they went over, say what to do at
  the next meal and move on.

TONE
Warm, brief, practical. Like a dietitian who respects their time. No
guilt-tripping. Never more than two sentences before letting them speak.
"""


def tool_definitions(base_url: str, agent_key: str) -> List[Dict[str, Any]]:
    """
    Tool schemas to register in the Sarvam console.

    Generated from the live config so the URLs and the auth header are always
    the ones this server actually expects.
    """
    base = base_url.rstrip("/")
    headers = {"X-Agent-Key": agent_key or "<set AGENT_TOOL_KEY in .env>"}

    return [
        {
            "name": "get_call_context",
            "description": "Read at the start of every call: which meal slot "
                           "this is, what is already logged today, and the "
                           "targets for this meal. Call this before saying "
                           "anything about food.",
            "method": "GET",
            "url": f"{base}/api/v1/agent/tools/call_context",
            "headers": headers,
            "query_parameters": {
                "phone": {"type": "string", "required": True,
                          "description": "The number being called. Identifies "
                                         "the user; pass the campaign's number "
                                         "variable."},
                "user_id": {"type": "integer", "required": False,
                            "description": "Optional. Overrides phone lookup."},
                "slot": {"type": "string", "required": False,
                         "enum": ["breakfast", "lunch", "snack", "dinner"],
                         "description": "Optional. Inferred from time of day "
                                        "if omitted."},
                "language": {"type": "string", "required": False},
            },
        },
        {
            "name": "log_meal",
            "description": "Record what the user just said they ate. Portions "
                           "must be in grams. Returns 'spoken_reply' -- read "
                           "that out verbatim.",
            "method": "POST",
            "url": f"{base}/api/v1/agent/tools/log_meal",
            "headers": {**headers, "Content-Type": "application/json"},
            "body_schema": {
                "type": "object",
                "properties": {
                    "phone": {"type": "string",
                              "description": "Number being called; identifies "
                                             "the user."},
                    "user_id": {"type": "integer",
                                "description": "Optional; overrides phone."},
                    "slot": {"type": "string",
                             "enum": ["breakfast", "lunch", "snack", "dinner"],
                             "description": "Optional; inferred from time of "
                                            "day if omitted."},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string",
                                         "description": "Food name in English "
                                                        "or common Indian name"},
                                "portion_g": {"type": "number"},
                            },
                            "required": ["name", "portion_g"],
                        },
                    },
                },
                "required": ["items"],
            },
        },
        {
            "name": "get_plan_for_slot",
            "description": "What the user's SAVED meal plan says to eat at a "
                           "given meal. Call this whenever they ask what they "
                           "should eat for breakfast, lunch, snack or dinner. "
                           "Returns 'spoken_reply' -- read it verbatim. Never "
                           "invent a meal instead of calling this.",
            "method": "GET",
            "url": f"{base}/api/v1/agent/tools/plan_for_slot",
            "headers": headers,
            "query_parameters": {
                "user_id": {"type": "integer", "required": False},
                "phone": {"type": "string", "required": False},
                "slot": {"type": "string", "required": False,
                         "enum": ["breakfast", "lunch", "snack", "dinner"],
                         "description": "Defaults to the current time of day."},
            },
        },
        {
            "name": "get_day_state",
            "description": "How much of today's calorie and protein budget is "
                           "left. Use if the user asks how they are doing. "
                           "Returns 'spoken_reply' -- read that out verbatim.",
            "method": "GET",
            "url": f"{base}/api/v1/agent/tools/day_state",
            "headers": headers,
            "query_parameters": {
                "phone": {"type": "string", "required": True},
                "user_id": {"type": "integer", "required": False},
            },
        },
        {
            "name": "safety_check",
            "description": "MANDATORY before answering anything involving a "
                           "medical condition, medication, or pregnancy. If it "
                           "returns blocking findings, read the action out and "
                           "stop.",
            "method": "POST",
            "url": f"{base}/api/v1/agent/tools/safety_check",
            "headers": {**headers, "Content-Type": "application/json"},
            "body_schema": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer"},
                    "conditions": {"type": "array", "items": {"type": "string"}},
                    "medications": {"type": "array", "items": {"type": "string"}},
                    "question": {"type": "string"},
                },
                "required": ["user_id"],
            },
        },
    ]


def _failure_hint(status: int) -> str:
    """
    Say what is actually wrong.

    The first version of this only described 404 and 401, so a 402 sent the
    user looking for a configuration fault that did not exist. A diagnostic
    that guesses is worse than none.
    """
    if status == 402:
        return ("Sarvam has no credits left on this workspace. Top up under "
                "Pricing in the console; nothing in this app needs changing.")
    if status == 401:
        return ("The Voice Agents key was rejected. Generate a fresh one under "
                "Deploy with code -- generating a new key invalidates the old. "
                "Note Voice Agents uses X-API-Key, not api-subscription-key.")
    if status == 404:
        return ("The outbound path was not found. It is workspace-scoped, so "
                "SARVAM_ORG_ID and SARVAM_WORKSPACE_ID must match the console.")
    if status == 422:
        return ("Sarvam rejected a field. Common causes: app_version points at "
                "a version that does not exist, or initial_language_name was "
                "given a code like 'hi-IN' instead of a name like 'Hindi'.")
    if status == 403:
        return ("Forbidden -- the key may not have outbound permission on this "
                "workspace.")
    if status and status >= 500:
        return "Sarvam had a server error. Retry in a moment."
    return "See the response body above for what Sarvam reported."


class SarvamService:
    def configured(self) -> Dict[str, bool]:
        return {
            "core_api_key": bool(settings.SARVAM_API_KEY),
            "voice_api_key": bool(settings.SARVAM_VOICE_API_KEY),
            "org_and_workspace": bool(settings.SARVAM_ORG_ID
                                      and settings.SARVAM_WORKSPACE_ID),
            "connection_id": bool(settings.SARVAM_CONNECTION_ID),
            "agent_id": bool(settings.SARVAM_AGENT_ID),
            "from_number": bool(settings.SARVAM_FROM_NUMBER),
            "agent_tool_key": bool(settings.AGENT_TOOL_KEY),
        }

    def console_config(self, base_url: str) -> Dict[str, Any]:
        """Everything to paste into the Sarvam console, in one response."""
        ready = self.configured()
        public = base_url.startswith("https://")

        return {
            "step_1_create_agent": {
                "system_prompt": AGENT_SYSTEM_PROMPT,
                "greeting": "Namaste, NutriAI se bol raha hoon. Do minute hai?",
                "languages": ["hi-IN", "en-IN"],
                "switch_language_during_call": True,
                "all_supported": SUPPORTED_LANGUAGES,
            },
            "step_2_register_tools": tool_definitions(
                base_url, settings.AGENT_TOOL_KEY),
            "step_3_telephony": {
                "options": ["Rent a number from Sarvam",
                            "Bring your own: Exotel, Twilio, Smartflo, Pulse, "
                            "Intalk, Vobiz"],
                "then": "Assign the number to the agent to create a deployment.",
            },
            "readiness": ready,
            "blocking_issues": self._blockers(ready, public, base_url),
            "auth_note": (
                "Voice Agents APIs use the 'X-API-Key' header. The core "
                "STT/TTS/translate APIs use 'api-subscription-key'. They are "
                "not interchangeable."
            ),
        }

    @staticmethod
    def _blockers(ready, public, base_url) -> List[str]:
        issues = []
        if not public:
            issues.append(
                f"BLOCKING: tool URLs point at {base_url}, which Sarvam's cloud "
                f"cannot reach. Run 'ngrok http 8020' and re-generate this "
                f"config with ?base_url=https://<your>.ngrok-free.app"
            )
        if not ready["agent_tool_key"]:
            issues.append("AGENT_TOOL_KEY is unset, so tool endpoints refuse "
                          "every request. Set it in backend/.env.")
        if not ready["org_and_workspace"]:
            issues.append("SARVAM_ORG_ID / SARVAM_WORKSPACE_ID are unset. Every "
                          "Voice Agents route is scoped to them and there is no "
                          "lookup endpoint -- copy them from the console URL.")
        if not ready["connection_id"]:
            issues.append("SARVAM_CONNECTION_ID is unset -- it identifies the "
                          "telephony connection the call goes out on.")
        if not ready["agent_id"]:
            issues.append("SARVAM_AGENT_ID is unset -- create the agent in the "
                          "console and copy its id into .env.")
        if not ready["from_number"]:
            issues.append("SARVAM_FROM_NUMBER is unset -- rent or attach a "
                          "number before outbound calls will place.")
        return issues

    async def place_call(self, to_number: str, slot: str,
                         user_id: int = 1,
                         language: str = "hi-IN",
                         user_name: Optional[str] = None,
                         opening_line: Optional[str] = None) -> Dict[str, Any]:
        """
        Trigger a single outbound call.

        Sarvam's outbound path is workspace-scoped and the exact route is
        behind the console login, so the endpoint is configurable rather than
        hard-coded to a guess. A failure returns a diagnosis, not an exception,
        because this runs on a schedule.
        """
        voice_key = settings.SARVAM_VOICE_API_KEY or settings.SARVAM_API_KEY
        if not voice_key:
            return {"placed": False,
                    "reason": "SARVAM_VOICE_API_KEY is not set."}
        if not settings.SARVAM_AGENT_ID:
            return {"placed": False,
                    "reason": "SARVAM_AGENT_ID is not set; create the agent in "
                              "the Sarvam console first."}
        if not to_number:
            return {"placed": False, "reason": "No destination number."}

        if not (settings.SARVAM_ORG_ID and settings.SARVAM_WORKSPACE_ID):
            return {
                "placed": False,
                "reason": "SARVAM_ORG_ID and SARVAM_WORKSPACE_ID are required. "
                          "Every Voice Agents route is scoped to them and there "
                          "is no endpoint to look them up -- read them out of "
                          "the console URL.",
            }

        url = (f"{SARVAM_OUTBOUND_API}/v1/orgs/{settings.SARVAM_ORG_ID}"
               f"/workspaces/{settings.SARVAM_WORKSPACE_ID}/outbounds")

        payload = {
            "app_config": {
                "app_id": settings.SARVAM_AGENT_ID,
                "app_version": settings.SARVAM_APP_VERSION,
                "app_type": "agent",
                "connection_config": {
                    "connection_id": settings.SARVAM_CONNECTION_ID,
                    "agent_phone_number": settings.SARVAM_FROM_NUMBER,
                },
                # Names must match the variables declared on the agent
                # (Variables tab) or Sarvam drops them: it is `meal_slot`,
                # not `slot`. call_disposition/call_summary are outputs the
                # agent sets during the call, so they are not sent here.
                "agent_variables": {
                    "user_id": str(user_id),
                    "meal_slot": slot,
                    "user_name": user_name or "there",
                },
                "app_overrides": {
                    k: v for k, v in {
                        "initial_language_name": language_name(language),
                        "initial_bot_message": opening_line,
                    }.items() if v
                },
            },
            "user_config": {"user_phone_number": to_number},
        }

        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    url,
                    json=payload,
                    headers={"X-API-Key": voice_key,
                             "Content-Type": "application/json"},
                    timeout=30.0,
                )
        except Exception as e:
            logger.warning(f"Sarvam outbound call failed: {e}")
            return {"placed": False, "reason": str(e), "url_tried": url}

        ok = res.status_code in (200, 201, 202)
        return {
            "placed": ok,
            "status_code": res.status_code,
            "url_tried": url,
            "response": res.text[:400],
            "hint": None if ok else _failure_hint(res.status_code),
        }

    async def detect_language(self, text: str) -> Dict[str, Any]:
        """Language ID for inbound text, so replies match the user's language."""
        if not settings.SARVAM_API_KEY:
            return {"ok": False, "reason": "SARVAM_API_KEY is not set."}
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    f"{SARVAM_CORE_API}/text-lid",
                    json={"input": text},
                    headers={"api-subscription-key": settings.SARVAM_API_KEY},
                    timeout=15.0,
                )
            if res.status_code != 200:
                return {"ok": False, "status_code": res.status_code,
                        "detail": res.text[:200]}
            data = res.json()
            detected = data.get("language_code")
            # Sarvam returns null when it cannot identify the language. A null
            # would leave the voice agent with no language to reply in, so
            # fall back to Hinglish-safe defaults and say we did.
            return {
                "ok": True,
                "language_code": detected or DEFAULT_LANGUAGE,
                "script_code": data.get("script_code"),
                "detected": detected is not None,
                "note": None if detected else (
                    "Language could not be identified; defaulting to "
                    f"{DEFAULT_LANGUAGE}."
                ),
            }
        except Exception as e:
            return {"ok": False, "reason": str(e)}


sarvam_service = SarvamService()
