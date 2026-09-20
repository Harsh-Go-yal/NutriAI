"""
Progress & Feedback Agent -- weekly trends and coaching.

Ported from the parallel build (Qwen/Ollama) onto OpenAI. As with the profile
agent, the arithmetic is done in code: averages, adherence percentages and
trend direction come from the logged data, and the model writes the reading of
them. A coaching app that miscounts someone's week loses trust permanently.
"""
import logging
import statistics
from typing import Any, Dict, List

from app.agents.base_agent import BaseAgent
from app.config import settings
from app.core.groq_client import groq_client

logger = logging.getLogger(__name__)

PROGRESS_SYSTEM_PROMPT = """
You are a nutrition coach reviewing someone's week.

The statistics are already computed and supplied to you. Do not recalculate
them and do not invent any number that is not in the input.

Return:
- headline: one sentence on how the week actually went.
- insights: 2-4 items, each {type: "success"|"warning"|"tip", message, action}.
  `message` states what the data shows; `action` is one concrete thing to do
  next week, specific to Indian home cooking.
- focus_next_week: the single most valuable change, in one sentence.

Tone: matter-of-fact and encouraging. Never shame a bad week. If adherence was
poor, say so plainly and give the smallest possible next step. If the data is
too thin to judge (fewer than 3 logged days), say that instead of guessing.
"""


class ProgressFeedbackAgent(BaseAgent):
    def __init__(self):
        self.name = "progress_feedback"
        self.model_id = settings.PROGRESS_MODEL
        self.system_prompt = PROGRESS_SYSTEM_PROMPT

    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        days: List[Dict[str, Any]] = input_data.get("days") or []
        targets = input_data.get("targets") or {}

        stats = self._compute(days, targets)

        response_schema = {
            "type": "object",
            "properties": {
                "headline": {"type": "string"},
                "insights": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "message": {"type": "string"},
                            "action": {"type": "string"},
                        },
                        "required": ["type", "message", "action"],
                    },
                },
                "focus_next_week": {"type": "string"},
            },
            "required": ["headline", "insights", "focus_next_week"],
        }

        try:
            narrative = await groq_client.chat_json(
                system_prompt=self.system_prompt,
                user_payload={"stats": stats, "targets": targets},
                response_schema=response_schema,
                model=self.model_id,
            )
        except Exception as e:
            logger.warning(f"Progress agent narrative step failed: {e}")
            narrative = {
                "headline": stats["auto_headline"],
                "insights": [],
                "focus_next_week": "Keep logging -- a full week of data makes "
                                   "this much more useful.",
            }

        return {**stats, **narrative,
                "computation_method": "Averages, adherence and trend computed "
                                      "from logged data; only the commentary "
                                      "is model-generated."}

    @staticmethod
    def _compute(days: List[Dict[str, Any]], targets: Dict[str, Any]) -> Dict[str, Any]:
        logged = [d for d in days if (d.get("calories") or 0) > 0]
        cal_target = targets.get("daily_calorie_target") or 0
        protein_target = (targets.get("macro_targets") or {}).get("protein_g") or 0

        if not logged:
            return {
                "days_logged": 0, "avg_calories": 0, "avg_protein_g": 0,
                "adherence_pct": 0, "trend": "insufficient_data",
                "best_day": None, "worst_day": None, "streak_days": 0,
                "enough_data": False,
                "auto_headline": "Not enough logged days to assess the week yet.",
            }

        cals = [d.get("calories") or 0 for d in logged]
        prots = [d.get("protein_g") or 0 for d in logged]
        avg_cal = round(statistics.mean(cals), 1)
        avg_prot = round(statistics.mean(prots), 1)

        # Adherence = how close to target, capped so overeating never scores
        # above a day that hit the target exactly.
        if cal_target:
            scores = [max(0.0, 1 - abs(c - cal_target) / cal_target) for c in cals]
            adherence = round(statistics.mean(scores) * 100, 1)
        else:
            adherence = 0.0

        # Trend: compare the second half of the period against the first.
        trend = "stable"
        if len(cals) >= 4 and cal_target:
            half = len(cals) // 2
            early = statistics.mean(abs(c - cal_target) for c in cals[:half])
            late = statistics.mean(abs(c - cal_target) for c in cals[half:])
            if late < early * 0.85:
                trend = "improving"
            elif late > early * 1.15:
                trend = "declining"

        best = min(logged, key=lambda d: abs((d.get("calories") or 0) - cal_target)) if cal_target else logged[0]
        worst = max(logged, key=lambda d: abs((d.get("calories") or 0) - cal_target)) if cal_target else logged[-1]

        return {
            "days_logged": len(logged),
            "avg_calories": avg_cal,
            "avg_protein_g": avg_prot,
            "protein_target_g": protein_target,
            "protein_gap_g": round(protein_target - avg_prot, 1) if protein_target else None,
            "adherence_pct": adherence,
            "trend": trend,
            "best_day": best.get("date"),
            "worst_day": worst.get("date"),
            "streak_days": len(logged),
            "enough_data": len(logged) >= 3,
            "auto_headline": (
                f"{len(logged)} days logged, averaging {avg_cal:.0f} kcal and "
                f"{avg_prot:.0f} g protein ({adherence:.0f}% adherence)."
            ),
        }
