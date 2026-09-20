"""
Habit streaks, XP, levels, shields and squads.

The scoring rules live in gamification_service; this module owns persistence,
so a restart never costs anyone their streak.
"""
import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import GameState, Squad
from app.services.gamification_service import (
    HABIT_LABELS, HABIT_XP, LEVELS, empty_state, gamification_service,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class CheckInRequest(BaseModel):
    user_id: str = "default"
    habit_key: str            # hydration | fuel | recovery


class ShieldRequest(BaseModel):
    user_id: str = "default"
    habit_key: str


class SquadCreateRequest(BaseModel):
    member_ids: List[str]
    name: Optional[str] = None


def _load(db: Session, user_key: str) -> GameState:
    row = db.query(GameState).filter(GameState.user_key == user_key).first()
    if not row:
        row = GameState(user_key=user_key, state=empty_state(user_key))
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _save(db: Session, row: GameState, state: Dict[str, Any]) -> None:
    # Reassign rather than mutate: SQLAlchemy does not track in-place changes
    # to a JSON column, so mutating it would silently never persist.
    row.state = dict(state)
    db.commit()


@router.post("/check-in")
async def check_in(req: CheckInRequest, db: Session = Depends(get_db)):
    """Complete today's habit, earn XP, advance the streak."""
    row = _load(db, req.user_id)
    state = dict(row.state or empty_state(req.user_id))

    try:
        result = gamification_service.check_in(state, req.habit_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    _save(db, row, state)
    return {**result, **gamification_service.status(state)}


@router.get("/status/{user_id}")
async def get_status(user_id: str, db: Session = Depends(get_db)):
    """Full game state: streaks, shields, XP, level, week grid, achievements."""
    row = _load(db, user_id)
    return gamification_service.status(dict(row.state or empty_state(user_id)))


@router.post("/use-shield")
async def use_shield(req: ShieldRequest, db: Session = Depends(get_db)):
    """Spend a shield to protect a streak through a missed day."""
    row = _load(db, req.user_id)
    state = dict(row.state or empty_state(req.user_id))

    try:
        result = gamification_service.use_shield(state, req.habit_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if result.get("used"):
        _save(db, row, state)
    return {**result, **gamification_service.status(state)}


@router.post("/squad/create")
async def create_squad(req: SquadCreateRequest, db: Session = Depends(get_db)):
    """Create a small accountability group (2-4 people)."""
    if not 2 <= len(req.member_ids) <= 4:
        raise HTTPException(status_code=400,
                            detail="A squad needs between 2 and 4 members.")

    squad_id = uuid.uuid4().hex[:8]
    db.add(Squad(squad_id=squad_id, name=req.name or "Squad",
                 member_ids=req.member_ids))

    for member in req.member_ids:
        row = _load(db, member)
        state = dict(row.state or empty_state(member))
        state["squad_id"] = squad_id
        row.state = state

    db.commit()
    return {"squad_id": squad_id, "members": req.member_ids,
            "name": req.name or "Squad"}


@router.get("/squad/{squad_id}")
async def get_squad(squad_id: str, db: Session = Depends(get_db)):
    """Squad standing: each member's streaks plus the combined total."""
    squad = db.query(Squad).filter(Squad.squad_id == squad_id).first()
    if not squad:
        raise HTTPException(status_code=404, detail="Squad not found.")

    members, combined = [], 0
    for member in squad.member_ids or []:
        row = _load(db, member)
        status = gamification_service.status(dict(row.state or empty_state(member)))
        combined += status["best_streak"]
        members.append({
            "user_id": member,
            "xp_total": status["xp_total"],
            "level": status["level"],
            "best_streak": status["best_streak"],
            "shields_available": status["shields_available"],
        })

    members.sort(key=lambda m: -m["xp_total"])
    return {
        "squad_id": squad_id,
        "name": squad.name,
        "members": members,
        "combined_streak": combined,
        "leader": members[0]["user_id"] if members else None,
    }


@router.get("/config")
async def config():
    """Level table and habit definitions, so the UI need not hardcode them."""
    return {
        "levels": LEVELS,
        "habits": [{"key": k, "label": HABIT_LABELS[k], "base_xp": v}
                   for k, v in HABIT_XP.items()],
        "multipliers": {"7_days": 1.5, "14_days": 2.0, "30_days": 3.0},
        "shields": "One free shield to start, plus one every 7-day streak "
                   "milestone. A shield covers a missed day so the streak survives.",
    }
