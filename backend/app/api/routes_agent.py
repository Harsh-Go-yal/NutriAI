"""
Endpoints the voice agent and the messaging bot call.

These are the "tools" you register in the Sarvam console. They are deliberately
small and single-purpose, because a voice agent picks tools mid-conversation
and a fat ambiguous tool gets called at the wrong moment.

Auth: a shared secret in X-Agent-Key, checked against settings.AGENT_TOOL_KEY.
These endpoints mutate a user's food log, so they are not left open. If the
key is unset the endpoints refuse rather than defaulting to open.
"""
import json
import logging
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.models import CallSchedule, DailyLog, User
from app.services.adaptation_service import adaptation_service
from app.services.clinical_safety_service import clinical_safety_service
from app.services.messaging_service import messaging_service
from app.services.sarvam_service import sarvam_service
from app.services.scheduler_service import scheduler_service, slot_for_time

logger = logging.getLogger(__name__)

router = APIRouter()


def require_agent_key(x_agent_key: str = Header(default="")):
    """
    Shared-secret gate.

    Fails closed: an unset key blocks every request rather than allowing all
    of them, so a missing .env value cannot silently expose the food log.
    """
    expected = settings.AGENT_TOOL_KEY
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="AGENT_TOOL_KEY is not configured on the server; agent "
                   "tools are disabled.",
        )
    if x_agent_key != expected:
        raise HTTPException(status_code=401, detail="Invalid X-Agent-Key.")
    return True


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class LoggedItem(BaseModel):
    name: str
    portion_g: float


class LogMealRequest(BaseModel):
    """
    Sarvam serialises an agent-generated array as a JSON *string*, so `items`
    arrives as '[{"name": "Roti", ...}]' rather than a real list. Accept both
    rather than requiring every console field to be retyped -- the agent's
    content was correct; only the encoding differed.
    """
    # user_id/slot are optional: phone identifies the user and the slot falls
    # back to the time of day, so a campaign need only pass the number.
    user_id: Optional[str] = None
    phone: Optional[str] = None
    slot: Optional[str] = None     # breakfast | lunch | snack | dinner
    items: List[LoggedItem]
    note: Optional[str] = None

    @field_validator("items", mode="before")
    @classmethod
    def _parse_items(cls, value):
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value        # let normal validation report it
        return value


class ScheduleEntry(BaseModel):
    slot: str
    time: str = "08:30"
    enabled: bool = False
    channel: str = "voice"
    language: str = "en-IN"


class ScheduleRequest(BaseModel):
    user_id: int = 1
    phone: Optional[str] = None
    consent_to_call: bool = False
    schedule: List[ScheduleEntry]


class NotifyRequest(BaseModel):
    user_id: int = 1
    text: str
    channel: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _profile(db: Session, user_id: int) -> Dict[str, Any]:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        # Demo-friendly default rather than a hard failure mid-call.
        return {"age": 30, "gender": "female", "weight_kg": 60,
                "height_cm": 165, "activity_level": "moderate",
                "goal_type": "maintenance"}
    return {
        "age": user.age, "gender": user.gender, "weight_kg": user.weight_kg,
        "height_cm": user.height_cm, "activity_level": user.activity_level,
        "goal_type": user.goal_type, "target_calories": user.target_calories,
        "medical_conditions": user.medical_conditions or [],
    }


def _clean(value: Optional[str]) -> Optional[str]:
    """Treat empty/placeholder strings from the agent as absent."""
    if value is None:
        return None
    value = str(value).strip()
    if not value or value.lower() in {"none", "null", "undefined", "<user_id>",
                                      "<meal_slot>", "<user_name>"}:
        return None
    return value


def _as_int(value) -> Optional[int]:
    value = _clean(value)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _resolve_user(db: Session, user_id: Optional[int],
                  phone: Optional[str]) -> int:
    """
    Work out who this call is about.

    Outbound campaigns reliably carry the phone number they dialled but often
    cannot carry a user_id, so the number is accepted as an identifier. An
    explicit user_id still wins when supplied.
    """
    if user_id:
        return user_id
    if phone:
        digits = "".join(ch for ch in phone if ch.isdigit())[-10:]
        for row in db.query(CallSchedule).all():
            if row.phone and "".join(ch for ch in row.phone if ch.isdigit())[-10:] == digits:
                return row.user_id
    return 1        # demo fallback


def _today_log(db: Session, user_id: int) -> DailyLog:
    today = date.today().isoformat()
    row = (db.query(DailyLog)
           .filter(DailyLog.user_id == user_id, DailyLog.log_date == today)
           .first())
    if not row:
        row = DailyLog(user_id=user_id, log_date=today, entries=[])
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _schedule_row(db: Session, user_id: int) -> CallSchedule:
    row = db.query(CallSchedule).filter(CallSchedule.user_id == user_id).first()
    if not row:
        row = CallSchedule(user_id=user_id,
                           schedule=scheduler_service.default_schedule(),
                           consent_to_call=0)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Tools the voice agent calls mid-conversation
# ---------------------------------------------------------------------------

@router.post("/tools/log_meal", dependencies=[Depends(require_agent_key)])
async def log_meal(req: LogMealRequest, db: Session = Depends(get_db)):
    """
    TOOL: record what the user just said they ate, and return the updated
    picture. The agent should read back only `spoken_reply`.
    """
    user_id = _resolve_user(db, _as_int(req.user_id), _clean(req.phone))
    slot = (_clean(req.slot) or slot_for_time()).lower()

    row = _today_log(db, user_id)
    entries = list(row.entries or [])

    for item in req.items:
        entries.append({"name": item.name, "portion_g": item.portion_g,
                        "slot": slot, "source": "voice_agent"})

    profile = _profile(db, user_id)
    state = await adaptation_service.day_state(profile, entries)

    # Persist only what resolved to a real food, so the log cannot fill up
    # with names the database could never price or score.
    row.entries = entries
    row.summary = {
        "consumed": state["consumed"],
        "remaining": state["remaining"],
        "percent_of_calories": state["percent_of_calories"],
    }
    db.commit()

    guidance = state["next_meal_guidance"]
    spoken = guidance["message"]
    if state["unresolved"]:
        spoken += (f" I could not find {', '.join(state['unresolved'])} in the "
                   f"food tables, so it is not counted.")

    return {
        "user_id": user_id,
        "slot": slot,
        "logged": len(req.items),
        "unresolved": state["unresolved"],
        "consumed": state["consumed"],
        "remaining": state["remaining"],
        "next_meal": guidance,
        "spoken_reply": spoken,
    }


@router.get("/tools/day_state", dependencies=[Depends(require_agent_key)])
async def day_state(user_id: Optional[str] = None, phone: Optional[str] = None,
                    db: Session = Depends(get_db)):
    """TOOL: where the user stands today. Returns a ready `spoken_reply`."""
    resolved_id = _resolve_user(db, _as_int(user_id), _clean(phone))
    row = _today_log(db, resolved_id)
    profile = _profile(db, resolved_id)
    state = await adaptation_service.day_state(profile, list(row.entries or []))
    state["user_id"] = resolved_id
    return state


@router.get("/tools/call_context", dependencies=[Depends(require_agent_key)])
async def call_context(user_id: Optional[str] = None, phone: Optional[str] = None,
                       slot: Optional[str] = None, language: str = "en",
                       db: Session = Depends(get_db)):
    """
    TOOL: the briefing handed to the agent when a call starts.

    Both `user_id` and `slot` are optional. `phone` identifies the user when a
    campaign cannot pass an id, and the slot is inferred from the clock -- so
    the cohort only has to supply the number it is already dialling.
    """
    resolved_id = _resolve_user(db, _as_int(user_id), _clean(phone))
    resolved_slot = (_clean(slot) or slot_for_time()).lower()

    row = _today_log(db, resolved_id)
    profile = _profile(db, resolved_id)
    state = await adaptation_service.day_state(profile, list(row.entries or []))

    script = adaptation_service.call_script(state, resolved_slot, language)
    script["user_id"] = resolved_id
    script["slot_source"] = "supplied" if slot else "inferred from time of day"
    return script


@router.post("/tools/safety_check", dependencies=[Depends(require_agent_key)])
async def safety_check(payload: Dict[str, Any], db: Session = Depends(get_db)):
    """
    TOOL: the agent must call this before giving any advice that touches a
    medical condition. A blocking result means the agent stops and offers a
    dietitian instead of improvising.
    """
    profile = _profile(db, payload.get("user_id", 1))
    result = clinical_safety_service.screen(
        conditions=payload.get("conditions") or profile.get("medical_conditions"),
        medications=payload.get("medications") or [],
        free_text=payload.get("question") or "",
    )
    result["spoken_reply"] = (
        result["blocking"][0]["action"] if result["blocking"]
        else "No safety concerns for that."
    )
    return result


# ---------------------------------------------------------------------------
# Scheduling -- the user's control surface
# ---------------------------------------------------------------------------

@router.get("/schedule")
async def get_schedule(user_id: int = 1, db: Session = Depends(get_db)):
    row = _schedule_row(db, user_id)
    schedule = list(row.schedule or [])
    return {
        "user_id": user_id,
        "phone": row.phone,
        "consent_to_call": bool(row.consent_to_call),
        "schedule": schedule,
        "next_up": scheduler_service.next_up(schedule),
        "summary": scheduler_service.summary(schedule),
        "quiet_hours": "21:30-07:00 (no voice calls)",
    }


@router.post("/schedule")
async def set_schedule(req: ScheduleRequest, db: Session = Depends(get_db)):
    """The user decides which slots ring. Everything defaults to off."""
    validated = scheduler_service.validate([e.model_dump() for e in req.schedule])
    if not validated["valid"]:
        raise HTTPException(status_code=400, detail=validated["errors"])

    wants_voice = any(e["enabled"] and e["channel"] in {"voice", "both"}
                      for e in validated["schedule"])
    if wants_voice and not req.consent_to_call:
        raise HTTPException(
            status_code=400,
            detail="Voice calls need consent_to_call=true and a phone number.",
        )
    if wants_voice and not (req.phone or "").strip():
        raise HTTPException(status_code=400,
                            detail="A phone number is required for voice calls.")

    row = _schedule_row(db, req.user_id)
    row.schedule = validated["schedule"]
    row.consent_to_call = 1 if req.consent_to_call else 0
    if req.phone is not None:
        row.phone = req.phone
    db.commit()
    db.refresh(row)

    return {
        "saved": True,
        "schedule": row.schedule,
        "next_up": scheduler_service.next_up(row.schedule),
        "summary": scheduler_service.summary(row.schedule),
    }


@router.get("/due")
async def due(user_id: int = 1, window_minutes: int = 10,
              db: Session = Depends(get_db)):
    """
    Which contacts are due right now. A scheduler (cron, Celery beat, or the
    Sarvam campaign scheduler) polls this and places the calls.
    """
    row = _schedule_row(db, user_id)
    log = _today_log(db, user_id)
    done = sorted({e.get("slot") for e in (log.entries or []) if e.get("slot")})

    if not row.consent_to_call:
        return {"due": [], "reason": "User has not consented to calls.",
                "slots_already_logged": done}

    return {
        "due": scheduler_service.due_now(row.schedule, window_minutes=window_minutes,
                                         already_done=done),
        "phone": row.phone,
        "slots_already_logged": done,
    }


# ---------------------------------------------------------------------------
# Messaging
# ---------------------------------------------------------------------------

@router.post("/notify")
async def notify(req: NotifyRequest, db: Session = Depends(get_db)):
    """Send the user a text update on whichever channel is configured."""
    row = _schedule_row(db, req.user_id)
    result = await messaging_service.send(
        text=req.text, phone=row.phone, channel=req.channel,
    )
    if not result.get("sent"):
        raise HTTPException(status_code=503, detail=result)
    return result


@router.post("/inbound/message")
async def inbound_message(payload: Dict[str, Any], db: Session = Depends(get_db)):
    """
    Webhook for an inbound text ("2 roti aur dal khaya").

    Parsing free text into items is the vision/NLU model's job; this endpoint
    accepts already-parsed items so the same log path serves voice, text and
    photo, and there is exactly one place that mutates the day's log.
    """
    user_id = payload.get("user_id", 1)
    items = payload.get("items") or []
    slot = (payload.get("slot") or "snack").lower()

    if not items:
        return {"ok": True, "note": "No items parsed from the message.",
                "reply": "Tell me what you ate and roughly how much."}

    row = _today_log(db, user_id)
    entries = list(row.entries or [])
    for item in items:
        entries.append({"name": item.get("name"),
                        "portion_g": item.get("portion_g") or 0,
                        "slot": slot, "source": "text"})

    profile = _profile(db, user_id)
    state = await adaptation_service.day_state(profile, entries)
    row.entries = entries
    db.commit()

    return {"ok": True, "remaining": state["remaining"],
            "reply": state["next_meal_guidance"]["message"]}


@router.get("/messaging/status")
async def messaging_status():
    """Which channels are actually configured on this server."""
    return messaging_service.status()


# ---------------------------------------------------------------------------
# Sarvam voice agent
# ---------------------------------------------------------------------------

@router.get("/sarvam/config")
async def sarvam_config(base_url: str = "http://localhost:8020"):
    """
    Everything to paste into the Sarvam console: system prompt, tool schemas
    with live URLs, and whatever is still blocking you.

    Pass ?base_url=https://<your>.ngrok-free.app once ngrok is running, so the
    tool URLs are reachable from Sarvam's cloud.
    """
    return sarvam_service.console_config(base_url)


@router.post("/sarvam/call")
async def sarvam_call(payload: Dict[str, Any], db: Session = Depends(get_db)):
    """Place one outbound call. Refuses without the user's consent."""
    user_id = payload.get("user_id", 1)
    row = _schedule_row(db, user_id)

    if not row.consent_to_call:
        raise HTTPException(
            status_code=403,
            detail="This user has not consented to phone calls.",
        )

    to_number = payload.get("to_number") or row.phone
    if not to_number:
        raise HTTPException(status_code=400, detail="No phone number on file.")

    # Give the agent a grounded opening line instead of a generic greeting.
    log = _today_log(db, user_id)
    profile = _profile(db, user_id)
    state = await adaptation_service.day_state(profile, list(log.entries or []))
    slot = (payload.get("slot") or slot_for_time()).lower()
    script = adaptation_service.call_script(state, slot,
                                            payload.get("language") or "hi-IN")

    return await sarvam_service.place_call(
        to_number=to_number,
        slot=slot,
        user_id=user_id,
        language=payload.get("language") or "hi-IN",
        user_name=payload.get("user_name"),
        opening_line=payload.get("opening_line") or script.get("opening_line"),
    )


@router.post("/sarvam/detect-language")
async def sarvam_detect_language(payload: Dict[str, Any]):
    """Language ID for an inbound vernacular message."""
    return await sarvam_service.detect_language(payload.get("text") or "")


@router.get("/tools/plan_for_slot", dependencies=[Depends(require_agent_key)])
async def plan_for_slot(user_id: Optional[str] = None, phone: Optional[str] = None,
                        slot: Optional[str] = None, day: int = 1,
                        db: Session = Depends(get_db)):
    """
    TOOL: what the saved plan says to eat at a given meal.

    Lets the caller ask "what should I have for dinner?" and get their own
    plan read back, rather than the agent improvising a meal that was never
    planned. Returns `spoken_reply` for the agent to read verbatim.
    """
    from app.models.models import MealPlan

    resolved_id = _resolve_user(db, _as_int(user_id), _clean(phone))
    wanted = (_clean(slot) or slot_for_time()).lower()

    row = (db.query(MealPlan)
           .filter(MealPlan.user_id == resolved_id)
           .order_by(MealPlan.created_at.desc())
           .first())

    if not row or not row.plan_data:
        return {
            "has_plan": False,
            "slot": wanted,
            "spoken_reply": "You do not have a saved meal plan yet. I can make "
                            "one for you, or just tell me what you are eating "
                            "and I will log it.",
        }

    plan = row.plan_data
    days = plan.get("days") or []
    chosen = next((d for d in days if d.get("day") == day), days[0] if days else None)
    if not chosen:
        return {"has_plan": False, "slot": wanted,
                "spoken_reply": "Your saved plan has no days in it."}

    meal = next((m for m in (chosen.get("meals") or [])
                 if (m.get("slot") or "").lower() == wanted), None)
    if not meal:
        available = [m.get("slot") for m in (chosen.get("meals") or [])]
        return {
            "has_plan": True,
            "slot": wanted,
            "available_slots": available,
            "spoken_reply": f"Your plan does not have a {wanted} entry. It "
                            f"covers {', '.join(a for a in available if a)}.",
        }

    items = meal.get("items") or []
    spoken = ", ".join(
        f"{i.get('name')}, {i.get('portion_g')} grams" for i in items if i.get("name"))

    swap = meal.get("swap_alternative") or {}
    swap_items = ", ".join(i.get("name", "") for i in (swap.get("items") or []))

    return {
        "has_plan": True,
        "slot": wanted,
        "day": chosen.get("day"),
        "items": items,
        "total_calories": meal.get("total_calories"),
        "swap": swap,
        "daily_calorie_target": plan.get("daily_calorie_target"),
        "spoken_reply": (
            f"Your plan for {wanted} is {spoken}. That is about "
            f"{meal.get('total_calories')} calories."
            + (f" If you would rather swap, try {swap_items}." if swap_items else "")
        ),
    }
