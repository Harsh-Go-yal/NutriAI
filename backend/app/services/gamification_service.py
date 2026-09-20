"""
Habit streaks, XP, levels, shields and squads.

Ported from the parallel build, with one substantive change: state lives in
the database rather than a module-level dict. An in-memory store loses every
user's streak on restart, and a streak that silently resets is worse than no
streak at all -- the whole mechanic depends on the user trusting the count.

XP, level thresholds and shield rules are kept exactly as designed.
"""
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

LEVELS = [
    {"level": 1, "title": "Novice Eater", "xp_required": 0},
    {"level": 2, "title": "Habit Starter", "xp_required": 200},
    {"level": 3, "title": "Consistency Champ", "xp_required": 600},
    {"level": 4, "title": "Fuel Master", "xp_required": 1400},
    {"level": 5, "title": "Nutrition Legend", "xp_required": 3000},
]

HABIT_XP = {"hydration": 25, "fuel": 35, "recovery": 30}

HABIT_LABELS = {
    "hydration": "Water First",
    "fuel": "Protein Anchor",
    "recovery": "Sleep & Recover",
}

ACHIEVEMENTS = [
    {"key": "first_checkin", "title": "First Step", "icon": "👟",
     "test": lambda s: s["xp_total"] > 0},
    {"key": "week_streak", "title": "7-Day Streak", "icon": "🔥",
     "test": lambda s: any(h["current_streak"] >= 7 for h in s["habits"].values())},
    {"key": "fortnight", "title": "Two Weeks Strong", "icon": "💪",
     "test": lambda s: any(h["current_streak"] >= 14 for h in s["habits"].values())},
    {"key": "month_streak", "title": "30-Day Legend", "icon": "🏆",
     "test": lambda s: any(h["current_streak"] >= 30 for h in s["habits"].values())},
    {"key": "all_three", "title": "Triple Threat", "icon": "⚡",
     "test": lambda s: all(h["current_streak"] >= 3 for h in s["habits"].values())},
    {"key": "level_3", "title": "Consistency Champ", "icon": "🌟",
     "test": lambda s: s["xp_total"] >= 600},
]


def _streak_multiplier(streak: int) -> float:
    if streak >= 30:
        return 3.0
    if streak >= 14:
        return 2.0
    if streak >= 7:
        return 1.5
    return 1.0


def level_for_xp(xp: int) -> dict:
    result = LEVELS[0]
    for lvl in LEVELS:
        if xp >= lvl["xp_required"]:
            result = lvl
    return result


def xp_to_next(xp: int) -> dict:
    current = level_for_xp(xp)
    for lvl in LEVELS:
        if lvl["xp_required"] > xp:
            span = max(1, lvl["xp_required"] - current["xp_required"])
            return {
                "current_xp": xp,
                "current_level_xp": current["xp_required"],
                "next_level_xp": lvl["xp_required"],
                "progress": round((xp - current["xp_required"]) / span, 3),
            }
    return {"current_xp": xp, "current_level_xp": current["xp_required"],
            "next_level_xp": current["xp_required"], "progress": 1.0}


def empty_state(user_id: str) -> Dict[str, Any]:
    return {
        "user_id": user_id,
        "xp_total": 0,
        "shields_available": 1,      # everyone starts with one free shield
        "habits": {
            key: {"current_streak": 0, "longest_streak": 0,
                  "last_checked_in": None, "xp": 0, "history": []}
            for key in HABIT_XP
        },
        "achievements": [],
        "shield_log": [],
        "squad_id": None,
    }


class GamificationService:
    def check_in(self, state: Dict[str, Any], habit_key: str) -> Dict[str, Any]:
        """
        Record today's habit. Returns (mutated state, result).

        Pure function over the state dict so the route owns persistence and
        this stays testable without a database.
        """
        if habit_key not in HABIT_XP:
            raise ValueError(f"Unknown habit '{habit_key}'. Use: {list(HABIT_XP)}")

        habit = state["habits"][habit_key]
        today = date.today().isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()

        if habit["last_checked_in"] == today:
            return {"already_done": True,
                    "message": "Already checked in today.",
                    "earned_xp": 0}

        shield_used = streak_broken = False
        if habit["last_checked_in"] not in (None, yesterday, today):
            # A day was missed. Spend a shield if one is available.
            if state["shields_available"] > 0:
                state["shields_available"] -= 1
                state["shield_log"].append(today)
                shield_used = True
            else:
                streak_broken = True
                habit["current_streak"] = 0

        habit["current_streak"] += 1
        habit["last_checked_in"] = today
        if today not in habit["history"]:
            habit["history"].append(today)
        habit["history"] = habit["history"][-30:]
        habit["longest_streak"] = max(habit["longest_streak"],
                                      habit["current_streak"])

        multiplier = _streak_multiplier(habit["current_streak"])
        earned = int(HABIT_XP[habit_key] * multiplier)
        habit["xp"] += earned

        before = state["xp_total"]
        state["xp_total"] += earned

        new_shield = habit["current_streak"] % 7 == 0
        if new_shield:
            state["shields_available"] += 1

        unlocked = self._unlock(state)
        leveled_up = level_for_xp(state["xp_total"])["level"] > level_for_xp(before)["level"]

        return {
            "already_done": False,
            "message": f"+{earned} XP ({multiplier}x multiplier)",
            "earned_xp": earned,
            "multiplier": multiplier,
            "shield_used": shield_used,
            "streak_broken": streak_broken,
            "new_shield_earned": new_shield,
            "leveled_up": leveled_up,
            "new_level": level_for_xp(state["xp_total"]) if leveled_up else None,
            "new_achievements": unlocked,
        }

    def use_shield(self, state: Dict[str, Any], habit_key: str) -> Dict[str, Any]:
        if habit_key not in HABIT_XP:
            raise ValueError(f"Unknown habit '{habit_key}'.")
        if state["shields_available"] <= 0:
            return {"used": False, "reason": "No shields available."}

        state["shields_available"] -= 1
        state["shield_log"].append(date.today().isoformat())
        # Treat today as covered so tomorrow continues the streak.
        state["habits"][habit_key]["last_checked_in"] = date.today().isoformat()
        return {"used": True,
                "shields_remaining": state["shields_available"],
                "protected": habit_key}

    def _unlock(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        have = {a["key"] for a in state.get("achievements", [])}
        newly = []
        for spec in ACHIEVEMENTS:
            if spec["key"] in have:
                continue
            try:
                if spec["test"](state):
                    entry = {"key": spec["key"], "title": spec["title"],
                             "icon": spec["icon"],
                             "unlocked_at": date.today().isoformat()}
                    state.setdefault("achievements", []).append(entry)
                    newly.append(entry)
            except Exception:            # a malformed state must not break check-in
                logger.debug("achievement %s could not be evaluated", spec["key"])
        return newly

    def status(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Full game state plus the derived bits the UI needs."""
        level = level_for_xp(state["xp_total"])
        week = [(date.today() - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]

        habits = {}
        for key, habit in state["habits"].items():
            habits[key] = {
                **habit,
                "label": HABIT_LABELS[key],
                "base_xp": HABIT_XP[key],
                "multiplier": _streak_multiplier(habit["current_streak"]),
                "checked_in_today": habit["last_checked_in"] == date.today().isoformat(),
                "week_grid": [{"date": d, "done": d in habit["history"]} for d in week],
            }

        best = max((h["current_streak"] for h in state["habits"].values()), default=0)
        return {
            "user_id": state["user_id"],
            "xp_total": state["xp_total"],
            "level": level,
            "progress": xp_to_next(state["xp_total"]),
            "shields_available": state["shields_available"],
            "habits": habits,
            "best_streak": best,
            "achievements": state.get("achievements", []),
            "all_achievements": [{"key": a["key"], "title": a["title"],
                                  "icon": a["icon"]} for a in ACHIEVEMENTS],
            "squad_id": state.get("squad_id"),
        }


gamification_service = GamificationService()
