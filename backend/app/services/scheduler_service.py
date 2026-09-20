"""
Call scheduling. The user decides whether the phone rings, and when.

Every slot is independently switchable and every schedule carries a
`consent` flag. An app that dials someone's phone without an explicit opt-in
per slot is a nuisance at best, so the default for a new user is all slots
OFF until they turn one on.
"""
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional

DEFAULT_TIMES = {
    "breakfast": "08:30",
    "lunch": "13:30",
    "snack": "17:30",
    "dinner": "21:00",
}

VALID_SLOTS = set(DEFAULT_TIMES)
VALID_CHANNELS = {"voice", "text", "both"}

# Nobody gets called outside these hours, whatever they configured.
QUIET_START = time(21, 30)
QUIET_END = time(7, 0)


def parse_hhmm(value: str) -> time:
    hours, _, minutes = (value or "").partition(":")
    return time(int(hours), int(minutes))


def in_quiet_hours(when: time) -> bool:
    """Quiet window wraps midnight, so it is an OR not an AND."""
    return when >= QUIET_START or when < QUIET_END


# Slot boundaries by clock time, so a call placed at 13:40 knows it is about
# lunch without the campaign having to pass it in.
SLOT_WINDOWS = [
    ("breakfast", time(4, 0), time(11, 0)),
    ("lunch", time(11, 0), time(16, 0)),
    ("snack", time(16, 0), time(19, 0)),
    ("dinner", time(19, 0), time(4, 0)),      # wraps midnight
]


def slot_for_time(when: Optional[time] = None) -> str:
    """Which meal a call at this time is about."""
    when = when or datetime.now().time()
    for slot, start, end in SLOT_WINDOWS:
        if start < end:
            if start <= when < end:
                return slot
        elif when >= start or when < end:    # the wrapping window
            return slot
    return "snack"


class SchedulerService:
    def default_schedule(self) -> List[Dict[str, Any]]:
        """New users start with everything off."""
        return [
            {
                "slot": slot,
                "time": default,
                "enabled": False,
                "channel": "voice",
                "language": "en-IN",
            }
            for slot, default in DEFAULT_TIMES.items()
        ]

    def validate(self, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Validate a user-submitted schedule, returning errors not exceptions."""
        cleaned, errors = [], []

        for entry in entries or []:
            slot = (entry.get("slot") or "").lower()
            if slot not in VALID_SLOTS:
                errors.append(f"Unknown slot '{entry.get('slot')}'.")
                continue

            raw_time = entry.get("time") or DEFAULT_TIMES[slot]
            try:
                when = parse_hhmm(raw_time)
            except (ValueError, TypeError):
                errors.append(f"{slot}: '{raw_time}' is not HH:MM.")
                continue

            channel = (entry.get("channel") or "voice").lower()
            if channel not in VALID_CHANNELS:
                errors.append(f"{slot}: channel must be one of {sorted(VALID_CHANNELS)}.")
                continue

            enabled = bool(entry.get("enabled"))
            quiet = in_quiet_hours(when)
            if enabled and quiet and channel in {"voice", "both"}:
                errors.append(
                    f"{slot} at {raw_time} falls in quiet hours "
                    f"({QUIET_START:%H:%M}-{QUIET_END:%H:%M}); voice calls are "
                    f"not scheduled then. Use channel 'text' or move the time."
                )
                continue

            cleaned.append({
                "slot": slot,
                "time": f"{when:%H:%M}",
                "enabled": enabled,
                "channel": channel,
                "language": entry.get("language") or "en-IN",
            })

        return {"schedule": cleaned, "errors": errors, "valid": not errors}

    def due_now(self, schedule: List[Dict[str, Any]], now: Optional[datetime] = None,
                window_minutes: int = 10,
                already_done: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Which slots are due within the window.

        `already_done` prevents re-dialling a slot the user has already logged
        -- being called about lunch you already reported is the fastest way to
        get an app uninstalled.
        """
        now = now or datetime.now()
        done = set(already_done or [])
        due = []

        for entry in schedule or []:
            if not entry.get("enabled") or entry["slot"] in done:
                continue
            scheduled = datetime.combine(now.date(), parse_hhmm(entry["time"]))
            delta = (now - scheduled).total_seconds() / 60.0
            if 0 <= delta <= window_minutes:
                due.append({**entry, "scheduled_for": scheduled.isoformat(),
                            "minutes_late": round(delta, 1)})
        return due

    def next_up(self, schedule: List[Dict[str, Any]],
                now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
        """The next enabled contact, today or tomorrow."""
        now = now or datetime.now()
        upcoming = []

        for entry in schedule or []:
            if not entry.get("enabled"):
                continue
            when = datetime.combine(now.date(), parse_hhmm(entry["time"]))
            if when < now:
                when += timedelta(days=1)
            upcoming.append((when, entry))

        if not upcoming:
            return None

        when, entry = min(upcoming, key=lambda pair: pair[0])
        return {**entry, "next_at": when.isoformat(),
                "in_minutes": round((when - now).total_seconds() / 60)}

    def summary(self, schedule: List[Dict[str, Any]]) -> str:
        on = [e for e in schedule or [] if e.get("enabled")]
        if not on:
            return "No calls or messages scheduled. You are in full control."
        parts = [f"{e['slot']} at {e['time']} ({e['channel']})" for e in on]
        return "Scheduled: " + ", ".join(parts) + "."


scheduler_service = SchedulerService()
