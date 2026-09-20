"""
Chat sessions -- a conversational front door to every agent.

Sessions and messages are persisted, so a refresh does not lose the thread.
Each message either targets a named agent (chosen in the sidebar) or goes to
the general assistant, which answers from the same measured data the rest of
the app uses rather than from the model's own recall.
"""
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.core.groq_client import AgentGenerationError, groq_client
from app.core.orchestrator import orchestrator
from app.database import get_db
from app.models.models import ChatSession
from app.services.clinical_safety_service import clinical_safety_service
from app.services import chat_router_service as router_svc
from app.services.nutrition_service import nutrition_service

logger = logging.getLogger(__name__)

# Household measures -> table weights. Shared with the voice agent prompt.
CONVERSIONS = """Portions must be in GRAMS of the food AS IT APPEARS IN A COMPOSITION TABLE, which lists dry/raw weights for grains and pulses. Cooked food absorbs water, so convert back to dry weight:
  1 roti/chapati = 40 g (as atta: 35 g)
  1 katori cooked dal = 30 g dry dal
  1 katori cooked rice = 50 g raw rice
  1 katori cooked sabzi = 100 g vegetable
  1 cup milk = 200 g, 1 egg = 50 g, 1 slice bread = 30 g
  1 katori curd = 150 g, 1 bowl poha/upma = 60 g dry
Using cooked weight against a dry-weight table overstates calories about threefold, so this conversion matters."""

router = APIRouter()

# Agents offered in the sidebar. `kind` tells the UI whether picking it needs
# a form (structured input) or just a message.
AGENTS = [
    {"key": "general", "name": "Assistant", "icon": "💬", "kind": "chat",
     "description": "Ask anything about your food, plan or numbers."},
    {"key": "nutrition_lookup", "name": "Nutrition Lookup", "icon": "🔍", "kind": "chat",
     "description": "Look up any food against IFCT 2017, USDA, then an estimate."},
    {"key": "food_log", "name": "Log a Meal", "icon": "🍽️", "kind": "chat",
     "description": "Tell me what you ate; it is resolved and saved to today's log."},
    {"key": "diet_planner", "name": "Diet Planner", "icon": "📋", "kind": "structured",
     "description": "Generate a macro-balanced day-by-day plan."},
    {"key": "food_vision", "name": "Food Vision", "icon": "📷", "kind": "upload",
     "description": "Photograph a meal; get measured nutrients back."},
    {"key": "profile_health", "name": "Profile & Health", "icon": "🩺", "kind": "structured",
     "description": "BMI, BMR, targets and risk factors."},
    {"key": "recommendation", "name": "Recommendations", "icon": "💡", "kind": "structured",
     "description": "Swaps and adjustments from what you have logged."},
    {"key": "progress_feedback", "name": "Progress", "icon": "📈", "kind": "structured",
     "description": "Weekly trend, adherence and what to change."},
]

GENERAL_SYSTEM_PROMPT = """
You are NutriAI's assistant, for Indian nutrition.

Grounding rules, in order:
- Any nutrient number you state must come from the `facts` block supplied in
  this turn. If a food is not in `facts`, say you do not have measured data
  for it rather than estimating from memory.
- `facts` entries carry a `source`. If the source says "estimate", say so out
  loud when you use that number.
- Never give medical advice, never name a drug or dose, never diagnose. If a
  question is clinical, say it needs a doctor or registered dietitian.

You are given the user's stored profile and today's log in `context`. Use
them. Do not tell the user you lack information that is already in `context`,
and do not refer them to a dietitian for ordinary nutrition questions -- that
referral is reserved for genuinely clinical ones.

Style: brief and concrete. Indian foods and household measures (katori, roti)
where they help. No hype, no emoji.
"""


class SessionCreate(BaseModel):
    title: Optional[str] = None
    agent: str = "general"
    user_id: int = 1


class MessageIn(BaseModel):
    content: str
    agent: Optional[str] = None
    user_id: int = 1


def _session(db: Session, session_id: str) -> ChatSession:
    row = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Session not found.")
    return row


def _title_from(text: str) -> str:
    text = " ".join((text or "").split())
    return (text[:44] + "...") if len(text) > 44 else (text or "New chat")


@router.get("/agents")
async def list_agents():
    """The sidebar's agent list."""
    return {"agents": AGENTS,
            "sources": {
                "primary": nutrition_service.source_meta.get("source"),
                "fallback": "USDA FoodData Central",
                "last_resort": "OpenAI estimate (flagged, not measured)",
            }}


@router.get("/sessions")
async def list_sessions(user_id: int = 1, db: Session = Depends(get_db)):
    rows = (db.query(ChatSession)
            .filter(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc())
            .limit(100).all())
    return {"sessions": [{
        "session_id": r.session_id,
        "title": r.title,
        "agent": r.agent,
        "message_count": len(r.messages or []),
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    } for r in rows]}


@router.post("/sessions")
async def create_session(req: SessionCreate, db: Session = Depends(get_db)):
    row = ChatSession(
        session_id=uuid.uuid4().hex[:12],
        user_id=req.user_id,
        title=req.title or "New chat",
        agent=req.agent,
        messages=[],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"session_id": row.session_id, "title": row.title, "agent": row.agent,
            "messages": []}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, db: Session = Depends(get_db)):
    row = _session(db, session_id)
    return {"session_id": row.session_id, "title": row.title, "agent": row.agent,
            "messages": row.messages or []}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, db: Session = Depends(get_db)):
    row = _session(db, session_id)
    db.delete(row)
    db.commit()
    return {"deleted": session_id}


@router.post("/sessions/{session_id}/message")
async def send_message(session_id: str, req: MessageIn,
                       db: Session = Depends(get_db)):
    """Send a message and get the assistant's reply."""
    row = _session(db, session_id)
    messages: List[Dict[str, Any]] = list(row.messages or [])
    agent = (req.agent or row.agent or "general").lower()

    messages.append({"role": "user", "content": req.content,
                     "at": datetime.utcnow().isoformat()})

    try:
        reply = await _respond(agent, req.content, messages, req.user_id, db)
    except AgentGenerationError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception:
        logger.exception("Chat turn failed.")
        raise HTTPException(status_code=500, detail="Internal server error")

    messages.append({"role": "assistant", **reply,
                     "at": datetime.utcnow().isoformat()})

    row.messages = messages
    row.agent = agent
    if row.title in (None, "", "New chat"):
        row.title = _title_from(req.content)
    row.updated_at = datetime.utcnow()
    db.commit()

    return {"session_id": session_id, "title": row.title, "reply": reply,
            "messages": messages}


# ---------------------------------------------------------------------------
# Response strategies
# ---------------------------------------------------------------------------

async def _respond(agent: str, content: str, history: List[Dict[str, Any]],
                   user_id: int, db: Optional[Session] = None) -> Dict[str, Any]:
    if agent == "food_log":
        return await _log_from_text(content, user_id, db)
    if agent == "nutrition_lookup":
        return await _nutrition_lookup(content)
    if agent in orchestrator.registry and agent != "food_vision":
        return await _run_agent(agent, content, user_id, db)
    if agent == "food_vision":
        return {
            "content": "Attach a meal photo with the image button and press "
                       "send — I will identify the ingredients and look up "
                       "measured nutrients for each.",
            "agent": agent,
        }
    if db is not None:
        # Reporting a meal wins over every other route: "I had dal for lunch"
        # is a log instruction, not a question about dal.
        if _looks_like_eating(content):
            logged = await _log_from_text(content, user_id, db)
            if logged.get("logged_count"):
                return logged

        capability = router_svc.route_capability(content)
        if capability:
            return await _run_capability(capability, content, user_id, db)

        routed = router_svc.route_agent(content)
        if routed:
            return await _run_agent(routed, content, user_id, db)
    return await _general(content, history)


# Phrases that mean "this is something I ate", in English and common
# transliterated Hindi/Marathi. Kept explicit rather than asking a model,
# because a false positive writes to the user's food log.
EATING_MARKERS = (
    "i ate", "i had", "i've had", "ive had", "just ate", "just had",
    "for breakfast", "for lunch", "for dinner", "as a snack",
    "khaya", "khaaya", "khaya hai", "khalla", "khalle", "kha liya",
    "log this", "log it", "add to my log", "note that i",
)


def _looks_like_eating(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in EATING_MARKERS)


async def _log_from_text(content: str, user_id: int,
                         db: Optional[Session]) -> Dict[str, Any]:
    """
    Turn "2 roti aur dal khaya" into logged entries.

    The model only extracts names and grams -- exactly the split used for the
    voice agent and the photo path. Nutrients come from the lookup chain, and
    the write goes through the same DailyLog rows the phone calls use, so
    every channel lands in one place.
    """
    from datetime import date as _date
    from app.models.models import DailyLog
    from app.services.adaptation_service import adaptation_service
    from app.services.scheduler_service import slot_for_time

    schema = {
        "type": "object",
        "properties": {
            "slot": {"type": "string",
                     "enum": ["breakfast", "lunch", "snack", "dinner"]},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"name": {"type": "string"},
                                   "portion_g": {"type": "number"}},
                    "required": ["name", "portion_g"],
                },
            },
        },
        "required": ["items"],
    }

    extracted = await groq_client.chat_json(
        system_prompt=(
            "Extract the foods a person says they ate. " + CONVERSIONS +
            " Use plain food names in English or the common Indian name. If no "
            "food is mentioned, return an empty items list. Infer `slot` only "
            "if they say it."
        ),
        user_payload={"message": content},
        response_schema=schema,
        model=settings.RECOMMENDATION_MODEL,
    )

    items = extracted.get("items") or []
    if not items:
        return {"content": "I could not pick out any food to log from that. "
                           "Try something like: 2 roti and a katori of dal.",
                "agent": "food_log", "logged_count": 0}

    slot = (extracted.get("slot") or slot_for_time()).lower()
    today = _date.today().isoformat()

    row = (db.query(DailyLog)
           .filter(DailyLog.user_id == user_id, DailyLog.log_date == today)
           .first())
    if not row:
        row = DailyLog(user_id=user_id, log_date=today, entries=[])
        db.add(row)
        db.commit()
        db.refresh(row)

    entries = list(row.entries or [])
    added, unresolved = [], []
    for item in items:
        name = (item.get("name") or "").strip()
        grams = item.get("portion_g") or 0
        if not name or grams <= 0:
            continue
        food = await nutrition_service.resolve(name)
        if not food:
            unresolved.append(name)
            continue
        entries.append({"name": name, "portion_g": grams, "slot": slot,
                        "source": "chat"})
        scaled = nutrition_service.scale(food, grams)
        added.append({"name": food.get("name"), "requested": name,
                      "portion_g": grams, "calories": scaled.get("calories"),
                      "protein_g": scaled.get("protein_g"),
                      "source": food.get("source"),
                      "estimated": bool(food.get("estimated"))})

    profile = _profile_for(db, user_id)
    state = await adaptation_service.day_state(profile, entries)

    # Reassign, do not mutate: SQLAlchemy will not notice an in-place edit
    # of a JSON column and the write would be lost.
    row.entries = entries
    row.summary = {"consumed": state["consumed"], "remaining": state["remaining"],
                   "percent_of_calories": state["percent_of_calories"]}
    db.commit()

    lines = [f"Logged to {slot}:"]
    lines += [f"  {a['name']} — {a['portion_g']:.0f} g · {a['calories']} kcal · "
              f"{a['protein_g']} g protein" for a in added]
    if unresolved:
        lines.append(f"  (no data for: {', '.join(unresolved)})")
    lines.append("")
    lines.append(f"Today: {state['consumed']['calories']:.0f} kcal, "
                 f"{state['consumed']['protein_g']:.0f} g protein.")
    lines.append(state["next_meal_guidance"]["message"])

    return {"content": chr(10).join(lines), "agent": "food_log",
            "logged_count": len(added),
            "facts": [{"name": a["name"], "source": a["source"],
                       "estimated": a["estimated"]} for a in added],
            "totals": state["consumed"]}


async def _run_agent(agent: str, content: str, user_id: int,
                     db: Optional[Session]) -> Dict[str, Any]:
    """
    Run a structured agent from a chat turn.

    The inputs each agent needs are assembled from the user's stored profile
    and food log rather than demanded from the person mid-conversation -- the
    data is already there, and asking for it again is what makes chat-driven
    tools tedious.
    """
    from app.services.adaptation_service import adaptation_service
    from app.services.fitness_service import fitness_service

    profile = _profile_for(db, user_id)
    payload: Dict[str, Any] = {}

    if agent == "profile_health":
        payload = {"profile": profile, "note": content}

    elif agent == "diet_planner":
        payload = {
            "profile": {k: profile[k] for k in
                        ("age", "gender", "height_cm", "weight_kg",
                         "activity_level", "medical_conditions")},
            "goals": {"goal_type": profile.get("goal_type") or "maintenance",
                      "target_calories": profile.get("target_calories")},
            "preferences": {"diet_type": profile.get("diet_type") or "veg",
                            "cuisine_preference": "indian",
                            "allergies": [], "dislikes": []},
            "plan_length_days": 3,
            "user_request": content,
            "available_foods": nutrition_service.get_all_foods(
                diet_type=profile.get("diet_type") or "veg"),
        }

    elif agent == "recommendation":
        entries = _entries_for(db, user_id)
        state = await adaptation_service.day_state(profile, entries)
        payload = {
            "active_plan_summary": state.get("next_meal_guidance") or {},
            "logged_today": entries,
            "recent_activity": {},
            "adherence_history": {"consumed": state.get("consumed"),
                                  "remaining": state.get("remaining")},
            "user_request": content,
        }

    elif agent == "progress_feedback":
        payload = {
            "days": _recent_days(db, user_id),
            "targets": fitness_service.targets(
                profile.get("weight_kg") or 60, profile.get("height_cm") or 165,
                profile.get("age") or 30, profile.get("gender") or "female",
                profile.get("activity_level") or "moderate",
                profile.get("goal_type") or "maintenance"),
            "user_request": content,
        }

    result = await orchestrator.route(agent, payload)

    if db is not None:
        _record_run(db, user_id, agent, payload, result)
        if agent == "diet_planner":
            _persist_plan(db, user_id, result)

    return {"content": _summarise(agent, result), "agent": agent,
            "data": result}


def _persist_plan(db, user_id: int, plan: dict) -> None:
    """
    Store the generated plan against the user.

    A plan that exists only in a chat bubble is lost on refresh, and the
    My Plan page had no way to find it. One active plan per user: a new one
    replaces the old rather than accumulating.
    """
    from app.models.models import MealPlan, User

    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            user = User(id=user_id, name="Demo User")
            db.add(user)
            db.commit()
            db.refresh(user)

        row = (db.query(MealPlan)
               .filter(MealPlan.user_id == user.id)
               .order_by(MealPlan.created_at.desc())
               .first())
        if row:
            row.plan_data = plan
        else:
            db.add(MealPlan(user_id=user.id, plan_data=plan))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not persist the generated plan.")


def _summarise(agent: str, result: Dict[str, Any]) -> str:
    """Turn an agent's structured output into something readable in a chat."""
    if agent == "profile_health":
        m = result.get("macro_targets") or {}
        lines = [
            f"BMI {result.get('bmi')} ({result.get('bmi_category')})",
            f"BMR {result.get('bmr_calories')} kcal · TDEE {result.get('tdee_calories')} kcal",
            f"Target {result.get('recommended_calories')} kcal — "
            f"{m.get('protein_g')} g protein, {m.get('carbs_g')} g carbs, {m.get('fat_g')} g fat",
        ]
        if result.get("health_risks"):
            lines += ["", "Risk factors to discuss with a doctor:"] + \
                     [f"· {r}" for r in result["health_risks"][:4]]
        if result.get("dietary_focus"):
            lines += ["", "Focus on:"] + [f"· {r}" for r in result["dietary_focus"][:4]]
        if result.get("motivation_message"):
            lines += ["", result["motivation_message"]]
        return "\n".join(lines)

    if agent == "diet_planner":
        m = result.get("macro_targets") or {}
        lines = [f"{result.get('daily_calorie_target')} kcal/day — "
                 f"{m.get('protein_g')} g protein, {m.get('carbs_g')} g carbs, "
                 f"{m.get('fat_g')} g fat", ""]
        for day in (result.get("days") or [])[:3]:
            lines.append(f"Day {day.get('day')}")
            for meal in day.get("meals") or []:
                items = ", ".join(i.get("name", "") for i in meal.get("items") or [])
                lines.append(f"  {meal.get('slot')}: {items} ({meal.get('total_calories')} kcal)")
            lines.append("")
        for n in (result.get("notes") or [])[:3]:
            lines.append(f"· {n}")
        return "\n".join(lines).strip()

    if agent == "recommendation":
        lines = [result.get("summary", "")]
        for r in (result.get("recommendations") or [])[:5]:
            lines.append(f"\n[{r.get('priority')}] {r.get('message')}\n   {r.get('reason')}")
        return "\n".join(lines).strip()

    if agent == "progress_feedback":
        lines = [result.get("headline") or result.get("auto_headline", "")]
        lines.append(f"\n{result.get('days_logged')} days logged · "
                     f"{result.get('adherence_pct')}% adherence · trend: {result.get('trend')}")
        for i in (result.get("insights") or [])[:4]:
            lines.append(f"\n[{i.get('type')}] {i.get('message')}\n   → {i.get('action')}")
        if result.get("focus_next_week"):
            lines.append(f"\nNext week: {result['focus_next_week']}")
        return "\n".join(lines).strip()

    return json.dumps(result, indent=2)[:2000]


def _profile_for(db: Optional[Session], user_id: int) -> Dict[str, Any]:
    from app.models.models import User
    default = {"age": 30, "gender": "female", "weight_kg": 60, "height_cm": 165,
               "activity_level": "moderate", "goal_type": "maintenance",
               "diet_type": "veg", "medical_conditions": [], "target_calories": None}
    if not db:
        return default
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return default
    return {
        "age": user.age or 30, "gender": user.gender or "female",
        "weight_kg": user.weight_kg or 60, "height_cm": user.height_cm or 165,
        "activity_level": user.activity_level or "moderate",
        "goal_type": user.goal_type or "maintenance",
        "diet_type": user.diet_type or "veg",
        "medical_conditions": user.medical_conditions or [],
        "target_calories": user.target_calories,
    }


def _entries_for(db: Optional[Session], user_id: int) -> List[Dict[str, Any]]:
    from datetime import date as _date
    from app.models.models import DailyLog
    if not db:
        return []
    row = (db.query(DailyLog)
           .filter(DailyLog.user_id == user_id,
                   DailyLog.log_date == _date.today().isoformat())
           .first())
    return list(row.entries or []) if row else []


def _recent_days(db: Optional[Session], user_id: int, limit: int = 7) -> List[Dict[str, Any]]:
    from app.models.models import DailyLog
    if not db:
        return []
    rows = (db.query(DailyLog)
            .filter(DailyLog.user_id == user_id)
            .order_by(DailyLog.log_date.desc()).limit(limit).all())
    days = []
    for r in rows:
        summary = r.summary or {}
        consumed = summary.get("consumed") or {}
        days.append({"date": r.log_date,
                     "calories": consumed.get("calories") or 0,
                     "protein_g": consumed.get("protein_g") or 0,
                     "entries": len(r.entries or [])})
    return list(reversed(days))


async def _nutrition_lookup(content: str) -> Dict[str, Any]:
    """
    Resolve the foods named in the message through the full source chain.

    The chain is the product here, so the reply names which source answered
    for each food rather than presenting one undifferentiated number.
    """
    names = [n.strip() for n in content.replace(" and ", ",").split(",") if n.strip()]
    names = names[:6] or [content.strip()]

    found = []
    for name in names:
        food = await nutrition_service.resolve(name)
        if not food:
            found.append({"query": name, "found": False})
            continue
        found.append({
            "query": name,
            "found": True,
            "name": food.get("name"),
            "source": food.get("source"),
            "estimated": bool(food.get("estimated")),
            "per_100g": {k: food.get(k) for k in
                         ("calories", "protein_g", "carbs_g", "fat_g", "fiber_g")},
            "micronutrients": food.get("micronutrients"),
            "confidence": food.get("confidence") or food.get("match_confidence"),
        })

    lines = []
    for f in found:
        if not f["found"]:
            lines.append(f"{f['query']}: no data in IFCT, USDA or estimate.")
            continue
        p = f["per_100g"]
        flag = "  [estimated, not measured]" if f["estimated"] else ""
        lines.append(
            f"{f['name']} (per 100 g) - {p.get('calories')} kcal, "
            f"{p.get('protein_g')} g protein, {p.get('carbs_g')} g carbs, "
            f"{p.get('fat_g')} g fat. Source: {f['source']}{flag}"
        )

    return {"content": "\n".join(lines), "agent": "nutrition_lookup",
            "facts": found}


async def _general(content: str, history: List[Dict[str, Any]],
                   context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    General chat, grounded in whatever foods the message mentions.

    Foods are resolved first and handed to the model as `facts`, so the reply
    is built on measured values instead of the model's recollection.
    """
    facts = []
    for token in _candidate_foods(content):
        food = nutrition_service.lookup(token)
        if food:
            facts.append({
                "food": food["name"],
                "source": food.get("source"),
                "per_100g": {k: food.get(k) for k in
                             ("calories", "protein_g", "carbs_g", "fat_g", "fiber_g")},
            })

    recent = [{"role": m["role"], "content": m.get("content", "")}
              for m in history[-8:]]

    schema = {
        "type": "object",
        "properties": {"reply": {"type": "string"},
                       "used_sources": {"type": "array",
                                        "items": {"type": "string"}}},
        "required": ["reply"],
    }

    result = await groq_client.chat_json(
        system_prompt=GENERAL_SYSTEM_PROMPT,
        user_payload={"conversation": recent, "facts": facts,
                      "context": context or {}, "question": content},
        response_schema=schema,
        model=settings.RECOMMENDATION_MODEL,
    )

    text = result.get("reply") or "I could not put an answer together for that."

    # Clinical questions get the deterministic guardrail, not the model's judgement.
    screen = clinical_safety_service.screen(free_text=content)
    if screen["blocking"]:
        text = screen["blocking"][0]["action"]

    return {"content": text, "agent": "general", "facts": facts,
            "used_sources": result.get("used_sources") or [],
            "safety": screen["findings"]}


def _candidate_foods(text: str) -> List[str]:
    """
    Pull likely food names out of a sentence.

    Deliberately crude: it feeds a lookup that returns None for non-foods, so
    a false candidate costs nothing while a missed one costs grounding.
    """
    cleaned = "".join(c if c.isalnum() or c.isspace() else " " for c in text.lower())
    words = [w for w in cleaned.split() if len(w) > 2]
    grams = [" ".join(words[i:i + 2]) for i in range(len(words) - 1)]
    return (grams + words)[:14]


# ---------------------------------------------------------------------------
# Calendar -- per-day logging history for the sidebar
# ---------------------------------------------------------------------------

@router.get("/calendar")
async def calendar(user_id: int = 1, days: int = 35,
                   db: Session = Depends(get_db)):
    """
    Recent days with what was logged on each.

    Returns a dense range (including empty days) so the UI can draw a grid
    without filling gaps itself.
    """
    from datetime import date as _date, timedelta
    from app.models.models import DailyLog

    rows = {r.log_date: r for r in db.query(DailyLog)
            .filter(DailyLog.user_id == user_id).all()}

    today = _date.today()
    out = []
    for offset in range(days - 1, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        row = rows.get(day)
        consumed = (row.summary or {}).get("consumed") if row else None
        entries = len(row.entries or []) if row else 0
        out.append({
            "date": day,
            "logged": entries > 0,
            "entries": entries,
            "calories": round((consumed or {}).get("calories") or 0),
            "protein_g": round((consumed or {}).get("protein_g") or 0, 1),
            "is_today": day == today.isoformat(),
        })

    logged_days = [d for d in out if d["logged"]]
    return {
        "days": out,
        "logged_count": len(logged_days),
        "current_streak": _streak(out),
    }


@router.get("/calendar/{day}")
async def calendar_day(day: str, user_id: int = 1,
                       db: Session = Depends(get_db)):
    """Everything logged on one day, resolved to measured nutrients."""
    from app.models.models import DailyLog
    from app.services.micronutrient_service import micronutrient_service

    row = (db.query(DailyLog)
           .filter(DailyLog.user_id == user_id, DailyLog.log_date == day)
           .first())
    if not row or not (row.entries or []):
        return {"date": day, "logged": False, "items": [], "totals": {},
                "message": "Nothing logged on this day."}

    items = []
    for entry in row.entries or []:
        food = await nutrition_service.resolve(entry.get("name", ""))
        if not food:
            continue
        scaled = nutrition_service.scale(food, entry.get("portion_g") or 0)
        scaled["slot"] = entry.get("slot")
        items.append(scaled)

    totals = {}
    for field in ("calories", "protein_g", "carbs_g", "fat_g", "fiber_g"):
        values = [i[field] for i in items if i.get(field) is not None]
        totals[field] = round(sum(values), 1) if values else 0.0

    return {
        "date": day,
        "logged": True,
        "items": items,
        "totals": totals,
        "by_slot": _group_slots(items),
        "micronutrients": micronutrient_service.total_micros(items),
    }


def _streak(days: List[Dict[str, Any]]) -> int:
    """Consecutive logged days counting back from the most recent."""
    streak = 0
    for day in reversed(days):
        if day["logged"]:
            streak += 1
        elif not day["is_today"]:      # today not yet logged does not break it
            break
    return streak


def _group_slots(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    grouped: Dict[str, Any] = {}
    for item in items:
        slot = item.get("slot") or "other"
        bucket = grouped.setdefault(slot, {"items": [], "calories": 0.0,
                                           "protein_g": 0.0})
        bucket["items"].append(item["name"])
        bucket["calories"] += item.get("calories") or 0
        bucket["protein_g"] += item.get("protein_g") or 0
    for bucket in grouped.values():
        bucket["calories"] = round(bucket["calories"])
        bucket["protein_g"] = round(bucket["protein_g"], 1)
    return grouped


async def _run_capability(name: str, content: str, user_id: int,
                          db: Session) -> Dict[str, Any]:
    """
    Answer from a deterministic service.

    The assistant is the single front door -- a user should not have to know
    which page or agent owns a feature, so these are answered inline rather
    than being pointed elsewhere.
    """
    from app.models.models import CallSchedule, GameState
    from app.services.gamification_service import empty_state

    profile = _profile_for(db, user_id)
    entries = _entries_for(db, user_id)

    if name == "micronutrients":
        return await router_svc.handle_micronutrients(content, profile, entries)
    if name == "cost":
        return await router_svc.handle_cost(content, profile, entries)
    if name == "safety":
        return await router_svc.handle_safety(content, profile, entries)
    if name == "household":
        return await router_svc.handle_household(content)
    if name == "plan_read":
        return await router_svc.handle_plan_read(content, _load_plan(db, user_id))
    if name == "plan_delete":
        return _delete_plan(db, user_id)
    if name == "streak":
        key = str(user_id)
        row = db.query(GameState).filter(GameState.user_key == key).first()
        state = dict(row.state) if row and row.state else empty_state(key)
        return await router_svc.handle_streak(content, state)
    if name == "calls":
        row = (db.query(CallSchedule)
               .filter(CallSchedule.user_id == user_id).first())
        return await router_svc.handle_calls(content, row)

    return {"content": "I could not work out how to help with that.",
            "agent": "general"}


def _record_run(db, user_id: int, agent: str, payload: dict, result: dict) -> None:
    """
    Keep every agent output.

    Plans, assessments and progress reports used to live only in the chat
    bubble that produced them -- nothing could be revisited later or read back
    on a phone call. Failure here must never break the chat turn, so it is
    logged and swallowed.
    """
    from app.models.models import AgentRun
    try:
        db.add(AgentRun(user_id=user_id, agent=agent,
                        payload=payload, result=result))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not record the %s run.", agent)


def _load_plan(db, user_id: int) -> Optional[dict]:
    """The user's most recent saved plan, if any."""
    from app.models.models import MealPlan
    row = (db.query(MealPlan)
           .filter(MealPlan.user_id == user_id)
           .order_by(MealPlan.created_at.desc())
           .first())
    return row.plan_data if row and row.plan_data else None


def _delete_plan(db, user_id: int) -> Dict[str, Any]:
    """Remove the saved plan so a fresh one can be generated."""
    from app.models.models import MealPlan
    rows = db.query(MealPlan).filter(MealPlan.user_id == user_id).all()
    if not rows:
        return {"content": "There is no saved plan to delete.",
                "agent": "plan_delete"}
    for row in rows:
        db.delete(row)
    db.commit()
    return {"content": "Deleted your saved plan. Say \"make me a meal plan\" "
                       "whenever you want a new one.",
            "agent": "plan_delete"}
