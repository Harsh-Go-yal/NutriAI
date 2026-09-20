"""
Intent routing for the general assistant.

The assistant is the front door: a user should never need to know which agent
or page owns a feature. This module decides what a message is really asking
for and answers it from the deterministic services where one applies.

Routing is keyword-based rather than a model call. It has to be predictable
and free -- a misroute is more irritating than a slightly generic answer, and
paying for a classification round-trip on every turn is not worth it.
"""
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

RUPEE = "₹"

# Deterministic services the assistant answers from directly.
CAPABILITY_ROUTES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("micronutrients", (
        "micronutrient", "iron", "absorption", "absorb", "anaemia", "anemia",
        "calcium", "zinc", "folate", "vitamin a", "vitamin c", "hidden hunger",
        "chai", "tea with", "coffee with", "deficien",
    )),
    ("cost", (
        "budget", "rupee", "cheapest", "cheap", "afford", "cost", "money",
        "grocery list", "shopping list", "per rupee", "sasta", RUPEE,
    )),
    ("safety", (
        "medicine", "medication", "drug", "tablet", "warfarin", "metformin",
        "thyroid", "pregnan", "kidney", "ckd", "gout", "interaction",
        "safe for me", "is it safe",
    )),
    ("streak", (
        "streak", "xp", "level", "points", "badge", "achievement", "squad",
        "gamif", "check in", "check-in",
    )),
    ("calls", (
        "call me", "phone", "remind me", "schedule a call", "voice call",
        "call schedule", "stop calling",
    )),
    ("plan_delete", (
        "delete my plan", "remove my plan", "clear my plan", "cancel my plan",
        "delete the plan", "start over plan", "scrap my plan",
    )),
    ("plan_read", (
        "my meal plan", "my mean plan", "my diet plan", "my plan",
        "what is my plan", "whats my plan", "show my plan", "show me my plan",
        "todays plan", "today's plan", "plan for today", "fetch my plan",
        "current plan", "saved plan", "plan for dinner", "plan for lunch",
        "plan for breakfast", "plan for snack",
    )),
    ("household", (
        "family", "household", "my mother", "my father", "for four", "one pot",
        "everyone at home",
    )),
)

# Asks a specific LLM agent answers better than the general assistant.
AGENT_ROUTES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    # Broad on purpose: reads ("what is my meal plan") are matched by the
    # plan_read capability, which is checked before this list, so a bare
    # "meal plan" here can safely mean "make one".
    ("diet_planner", (
        "meal plan", "diet plan", "make a plan", "make me a plan",
        "create a plan", "generate a plan", "new plan", "plan for me",
        "weekly plan", "diet chart", "meal chart", "plan banao",
        "build me a plan", "plan bana",
    )),
    ("progress_feedback", (
        "how am i doing", "my progress", "this week", "last week", "my trend",
        "am i on track", "weekly summary", "how was my week",
    )),
    ("profile_health", (
        "my bmi", "my bmr", "my targets", "how many calories should i",
        "how much protein should i", "assess me", "my profile", "my tdee",
    )),
    ("recommendation", (
        "what should i eat", "what to eat", "suggest a meal", "suggest something",
        "healthier swap", "what can i eat", "kya khau", "kya khaun",
    )),
)


def route_capability(text: str) -> Optional[str]:
    lowered = (text or "").lower()
    for name, phrases in CAPABILITY_ROUTES:
        if any(p in lowered for p in phrases):
            return name
    return None


def route_agent(text: str) -> Optional[str]:
    lowered = (text or "").lower()
    for name, phrases in AGENT_ROUTES:
        if any(p in lowered for p in phrases):
            return name
    return None


def budget_from(text: str) -> Optional[float]:
    """Pull a rupee figure out of free text, if the user named one."""
    for token in (text or "").replace(RUPEE, " ").replace(",", "").split():
        digits = "".join(c for c in token if c.isdigit())
        if digits and len(digits) >= 2:
            try:
                return float(digits)
            except ValueError:
                continue
    return None


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def _resolved_items(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from app.services.nutrition_service import nutrition_service
    out = []
    for entry in entries or []:
        food = await nutrition_service.resolve(entry.get("name", ""))
        if food:
            scaled = nutrition_service.scale(food, entry.get("portion_g") or 0)
            scaled["slot"] = entry.get("slot")
            out.append(scaled)
    return out


async def handle_micronutrients(content, profile, entries) -> Dict[str, Any]:
    from app.services.micronutrient_service import micronutrient_service

    items = await _resolved_items(entries)
    if not items:
        return {"content": "Nothing is logged today yet, so there is no "
                           "micronutrient picture to assess. Tell me what you "
                           "ate and I will work it out.",
                "agent": "micronutrients"}

    lowered = content.lower()
    timing = None
    if any(w in lowered for w in ("chai", "tea", "coffee")):
        timing = "separated" if any(w in lowered for w in
                                    ("after", "later", "gap", "90")) else "with_meal"

    a = micronutrient_service.assess(
        items, age=profile.get("age"), gender=profile.get("gender"),
        life_stage=profile.get("life_stage"),
        context={"tea_coffee_timing": timing})
    ab = a["absorption"]

    lines = [a["headline"], "",
             f"Iron: {ab['iron_intake_mg']} mg on the plate, but only "
             f"{ab['iron_absorbed_mg']} mg absorbed "
             f"({ab['absorption_rate'] * 100:.0f}%)."]
    for note in ab["explanations"][:3]:
        lines.append("  - " + note)
    if a["gaps"]:
        lines += ["", "Biggest gaps against your ICMR RDA:"]
        lines += [f"  - {g['nutrient']}: {g['intake']} / {g['rda']} {g['unit']}"
                  f"  ({g['percent_rda']:.0f}%)" for g in a["gaps"][:4]]
    lines += ["", f"Assessed against {a['rda_source']}."]
    return {"content": "\n".join(lines), "agent": "micronutrients", "data": a}


async def handle_cost(content, profile, entries) -> Dict[str, Any]:
    from app.services.cost_optimizer_service import cost_optimizer_service
    from app.services.micronutrient_service import micronutrient_service

    items = await _resolved_items(entries)
    gaps: Dict[str, float] = {}
    if items:
        a = micronutrient_service.assess(items, age=profile.get("age"),
                                         gender=profile.get("gender"))
        for g in a["gaps"]:
            deficit = max(g["rda"] - g["intake"], 0)
            if deficit > 0 and g["key"] in {"iron_mg", "calcium_mg", "zinc_mg",
                                            "folate_ug", "vitamin_a_ug",
                                            "vitamin_c_mg"}:
                gaps[g["key"]] = round(deficit, 2)
    gaps.setdefault("protein_g", 40)

    result = cost_optimizer_service.optimize(
        gaps=gaps, budget=budget_from(content),
        diet_type=profile.get("diet_type") or "veg")

    if not result.get("basket"):
        return {"content": result.get("message", "No basket could be built for "
                                                 "those targets."),
                "agent": "cost", "data": result}

    lines = [result["message"], ""]
    lines += [f"  {b['food']} - {b['grams']} g  ({RUPEE}{b['cost']:.2f})"
              for b in result["basket"]]
    lines += ["", f"Total: {RUPEE}{result['total_cost']:.2f}",
              f"Solved with {result['solver']}, not a language model.",
              "", result["prices"]["warning"]]
    return {"content": "\n".join(lines), "agent": "cost", "data": result}


async def handle_safety(content, profile, entries) -> Dict[str, Any]:
    from app.services.clinical_safety_service import clinical_safety_service

    items = await _resolved_items(entries)
    screen = clinical_safety_service.screen(
        items=items,
        conditions=profile.get("medical_conditions"),
        medications=profile.get("medications") or [],
        free_text=content)

    if not screen["findings"]:
        return {"content": "Nothing flagged for what you have logged and the "
                           "conditions on your profile. Tell me which "
                           "medicines you take and I will re-check for "
                           "drug-nutrient interactions.\n\n"
                           + screen["disclaimer"],
                "agent": "safety", "data": screen}

    lines: List[str] = []
    for f in screen["findings"]:
        lines.append(f"[{f['severity'].upper()}] {f['message']}")
        lines.append("  Do this: " + f["action"])
        lines.append("  Basis: " + f["citation"])
        lines.append("")
    lines.append(screen["disclaimer"])
    return {"content": "\n".join(lines), "agent": "safety", "data": screen}


async def handle_streak(content, state) -> Dict[str, Any]:
    from app.services.gamification_service import gamification_service

    st = gamification_service.status(state)
    lines = [f"Level {st['level']['level']} - {st['level']['title']} "
             f"({st['xp_total']} XP)",
             f"Shields available: {st['shields_available']}", ""]
    for habit in st["habits"].values():
        when = "done today" if habit["checked_in_today"] else "not yet today"
        lines.append(f"  {habit['label']}: {habit['current_streak']}-day "
                     f"streak, {when}")
    if st["achievements"]:
        lines += ["", "Unlocked: " + ", ".join(
            f"{a['icon']} {a['title']}" for a in st["achievements"])]
    else:
        lines += ["", "No achievements yet - the first check-in unlocks one."]
    return {"content": "\n".join(lines), "agent": "streak", "data": st}


async def handle_calls(content, schedule_row) -> Dict[str, Any]:
    from app.services.scheduler_service import scheduler_service

    if not schedule_row or not (schedule_row.schedule or []):
        return {"content": "No call schedule set up yet.\n\nI can ring you at "
                           "any meal time you pick, in Hindi, Marathi, Tamil "
                           "or English. Every slot starts switched off, voice "
                           "calls need your explicit consent and a number, and "
                           "nothing is scheduled between 21:30 and 07:00.",
                "agent": "calls"}

    lines = [scheduler_service.summary(schedule_row.schedule)]
    nxt = scheduler_service.next_up(schedule_row.schedule)
    if nxt:
        lines.append(f"Next: {nxt['slot']} at {nxt['time']} "
                     f"(in {nxt['in_minutes']} minutes).")
    if not schedule_row.consent_to_call:
        lines.append("Voice calling is currently off - it needs your consent.")
    lines.append("Quiet hours 21:30-07:00; no voice calls are placed then.")
    return {"content": "\n".join(lines), "agent": "calls"}


async def handle_household(content) -> Dict[str, Any]:
    return {"content": "Household mode splits one dish across everyone at home "
                       "and judges each person's share against their own ICMR "
                       "requirement - so a diabetic father and an anaemic "
                       "teenager get different verdicts on the same pot, and "
                       "you get one cooking plan that serves all of them.\n\n"
                       "It needs each member's age, gender and weight, so open "
                       "Household from the Tools list in the sidebar to set "
                       "them up.",
            "agent": "household"}


SLOT_WORDS = ("breakfast", "lunch", "dinner", "snack")


async def handle_plan_read(content: str, plan: Optional[dict]) -> Dict[str, Any]:
    """Read back the saved plan, or one meal of it if a slot was named."""
    if not plan:
        return {"content": "You do not have a saved meal plan yet. Say "
                           "\"make me a meal plan\" and I will build one and "
                           "save it to My Plan.",
                "agent": "plan_read"}

    lowered = (content or "").lower()
    wanted = next((w for w in SLOT_WORDS if w in lowered), None)

    days = plan.get("days") or []
    if not days:
        return {"content": "Your saved plan has no days in it. Ask me to make "
                           "a new one.", "agent": "plan_read"}

    day = days[0]
    macros = plan.get("macro_targets") or {}
    header = (f"{plan.get('daily_calorie_target')} kcal/day - "
              f"{macros.get('protein_g')} g protein, "
              f"{macros.get('carbs_g')} g carbs, {macros.get('fat_g')} g fat")

    if wanted:
        meal = next((m for m in (day.get("meals") or [])
                     if (m.get("slot") or "").lower() == wanted), None)
        if not meal:
            have = ", ".join(m.get("slot", "") for m in (day.get("meals") or []))
            return {"content": f"Your plan has no {wanted} entry. It covers: {have}.",
                    "agent": "plan_read"}
        lines = [f"{wanted.capitalize()} - {meal.get('total_calories')} kcal", ""]
        lines += [f"  {i.get('name')} - {i.get('portion_g')} g"
                  for i in (meal.get("items") or [])]
        swap = meal.get("swap_alternative") or {}
        if swap.get("items"):
            lines += ["", "Swap: " + ", ".join(i.get("name", "")
                                               for i in swap["items"])]
            if swap.get("note"):
                lines.append(f"  ({swap['note']})")
        return {"content": "\n".join(lines), "agent": "plan_read", "data": plan}

    lines = [header, ""]
    for meal in day.get("meals") or []:
        items = ", ".join(i.get("name", "") for i in (meal.get("items") or []))
        lines.append(f"{(meal.get('slot') or '').capitalize()}: {items} "
                     f"({meal.get('total_calories')} kcal)")
    if len(days) > 1:
        lines += ["", f"This is day 1 of {len(days)}. Open My Plan for the rest."]
    lines += ["", "Say \"change dinner to paneer and roti\" to edit it, or "
                  "\"delete my plan\" to start again."]
    return {"content": "\n".join(lines), "agent": "plan_read", "data": plan}
