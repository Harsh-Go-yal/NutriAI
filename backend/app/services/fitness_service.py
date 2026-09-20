"""
Fitness/performance layer: energy targets, macro split, and protein timing.

This sits alongside the clinical layer rather than replacing it -- the same
meal is judged for training adequacy here and for safety there. The part that
is hard to copy is leucine: muscle protein synthesis is triggered per-meal
above a leucine threshold, and IFCT 2017 carries per-food leucine for Indian
foods, so this can tell a vegetarian lifter that their 30 g of dal protein
did not actually trigger MPS while 30 g of paneer would have.

References
----------
Mifflin-St Jeor equation (Am J Clin Nutr 1990) for BMR.
ISSN position stands on protein for exercising adults (1.4-2.0 g/kg) and on
per-meal distribution; leucine threshold ~2.5-3 g per meal for adults.
"""
from typing import Any, Dict, List, Optional

ACTIVITY_FACTORS = {
    "sedentary": 1.2,
    "light": 1.375,
    "lightly_active": 1.375,
    "moderate": 1.55,
    "moderately_active": 1.55,
    "active": 1.725,
    "very_active": 1.9,
    "athlete": 1.9,
}

# g protein per kg bodyweight, by goal (ISSN ranges).
PROTEIN_PER_KG = {
    "weight_loss": 1.8,      # higher, to spare lean mass in a deficit
    "muscle_gain": 1.9,
    "maintenance": 1.4,
    "weight_gain": 1.6,
    "endurance": 1.4,
}

CALORIE_ADJUSTMENT = {
    "weight_loss": -0.20,    # 20% deficit
    "muscle_gain": +0.10,    # modest surplus limits fat gain
    "weight_gain": +0.15,
    "maintenance": 0.0,
    "endurance": 0.0,
}

# Per-meal leucine needed to trigger muscle protein synthesis.
LEUCINE_THRESHOLD_G = 2.5
# Below this the meal cannot realistically hit the leucine threshold.
MIN_MEAL_PROTEIN_G = 20

FAT_MIN_FRACTION = 0.20      # never prescribe below 20% of energy from fat


class FitnessService:
    # -- energy ------------------------------------------------------------

    def bmr(self, weight_kg: float, height_cm: float, age: int, gender: str) -> float:
        """Mifflin-St Jeor."""
        base = 10 * weight_kg + 6.25 * height_cm - 5 * age
        return base + (5 if (gender or "").lower().startswith("m") else -161)

    def targets(self, weight_kg: float, height_cm: float, age: int, gender: str,
                activity_level: str = "moderate", goal_type: str = "maintenance",
                target_calories: Optional[int] = None) -> Dict[str, Any]:
        """Daily energy and macro targets for a training individual."""
        bmr = self.bmr(weight_kg, height_cm, age, gender)
        factor = ACTIVITY_FACTORS.get((activity_level or "").lower(), 1.55)
        tdee = bmr * factor

        goal = (goal_type or "maintenance").lower()
        calories = target_calories or round(tdee * (1 + CALORIE_ADJUSTMENT.get(goal, 0.0)))

        # Floors from ICMR/clinical practice -- an aggressive deficit is the
        # most common way these apps hurt people.
        floor = 1200 if (gender or "").lower().startswith("f") else 1500
        floored = False
        if calories < floor:
            calories, floored = floor, True

        protein_g = round(weight_kg * PROTEIN_PER_KG.get(goal, 1.4))
        fat_g = round(calories * FAT_MIN_FRACTION / 9)
        carbs_g = round(max(calories - protein_g * 4 - fat_g * 9, 0) / 4)

        return {
            "bmr_kcal": round(bmr),
            "tdee_kcal": round(tdee),
            "activity_factor": factor,
            "goal": goal,
            "daily_calorie_target": calories,
            "calorie_floor_applied": floored,
            "macro_targets": {
                "protein_g": protein_g,
                "carbs_g": carbs_g,
                "fat_g": fat_g,
            },
            "protein_per_kg": PROTEIN_PER_KG.get(goal, 1.4),
            "hydration_ml": round(weight_kg * 35),
            "method": "Mifflin-St Jeor BMR x activity factor; protein per ISSN "
                      "guidance for exercising adults.",
        }

    # -- protein quality / timing -----------------------------------------

    def meal_protein_quality(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Judge one meal on whether it can trigger muscle protein synthesis.

        Leucine is the trigger, and Indian vegetarian meals routinely miss it
        even at respectable total protein -- that is the insight worth showing.
        """
        protein = sum(i.get("protein_g") or 0 for i in items)
        leucine = sum((i.get("amino_acids_g") or {}).get("leu", 0) for i in items)

        if not any(i.get("amino_acids_g") for i in items):
            return {
                "protein_g": round(protein, 1),
                "leucine_g": None,
                "note": "Leucine unavailable -- these foods resolved through "
                        "USDA, which this app does not read amino acids from.",
            }

        triggers = leucine >= LEUCINE_THRESHOLD_G
        deficit = max(LEUCINE_THRESHOLD_G - leucine, 0)

        suggestions = []
        if not triggers:
            # Grams of a high-leucine food that would close the gap.
            for name, leu_per_100g in (("paneer", 1.841), ("egg", 1.09),
                                       ("soya chunks", 4.2), ("curd", 0.35)):
                if leu_per_100g > 0:
                    grams = round(deficit / leu_per_100g * 100)
                    if 10 <= grams <= 250:
                        suggestions.append(f"{grams} g {name}")

        return {
            "protein_g": round(protein, 1),
            "leucine_g": round(leucine, 2),
            "leucine_threshold_g": LEUCINE_THRESHOLD_G,
            "triggers_mps": triggers,
            "leucine_deficit_g": round(deficit, 2) if deficit else 0,
            "close_the_gap_with": suggestions[:3],
            "note": (
                f"{protein:.0f} g protein in this meal but only {leucine:.2f} g "
                f"leucine -- below the ~{LEUCINE_THRESHOLD_G} g needed to trigger "
                f"muscle protein synthesis. Total protein alone does not tell you this."
                if not triggers else
                f"{leucine:.2f} g leucine clears the ~{LEUCINE_THRESHOLD_G} g "
                f"threshold, so this meal triggers muscle protein synthesis."
            ),
        }

    def distribution_advice(self, meals: List[Dict[str, Any]],
                            daily_protein_target: float) -> Dict[str, Any]:
        """
        Protein spread across the day. Indian eating patterns tend to
        back-load protein into dinner; even distribution builds more muscle
        for the same total.
        """
        per_meal = [round(sum(i.get("protein_g") or 0 for i in (m.get("items") or [])), 1)
                    for m in meals]
        if not per_meal:
            return {"per_meal_protein_g": [], "advice": "No meals to assess."}

        total = sum(per_meal)
        ideal = daily_protein_target / len(per_meal) if meals else 0
        below = [i + 1 for i, p in enumerate(per_meal) if p < MIN_MEAL_PROTEIN_G]

        return {
            "per_meal_protein_g": per_meal,
            "daily_total_g": round(total, 1),
            "daily_target_g": round(daily_protein_target, 1),
            "even_split_target_g": round(ideal, 1),
            "meals_below_threshold": below,
            "advice": (
                f"Meals {below} are under {MIN_MEAL_PROTEIN_G} g protein and "
                f"probably will not trigger muscle protein synthesis. Moving "
                f"protein from your largest meal into them builds more muscle "
                f"at the same daily total."
                if below else
                "Protein is spread well across the day -- every meal clears the "
                f"{MIN_MEAL_PROTEIN_G} g mark."
            ),
        }

    # -- training-day adjustment ------------------------------------------

    def activity_adjustment(self, targets: Dict[str, Any],
                            activity: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Adjust intake for what the user actually did today."""
        activity = activity or {}
        steps = activity.get("steps") or 0
        workout_min = activity.get("workout_minutes") or 0
        intensity = (activity.get("workout_intensity") or "moderate").lower()

        # ~0.04 kcal per step per kg is the usual rough figure; kept simple
        # and stated as approximate rather than presented as measured.
        step_kcal = round(steps * 0.04)
        rate = {"light": 5, "moderate": 8, "vigorous": 12}.get(intensity, 8)
        workout_kcal = workout_min * rate

        burned = step_kcal + workout_kcal
        notes = []

        # TDEE already bakes in an activity factor. Adding measured activity
        # on top of it counts the same exercise twice -- that produced a
        # 4,246 kcal target for a 70 kg lifter. When we have measured
        # activity, rebuild the target from the sedentary baseline instead.
        sedentary_tdee = round(targets["bmr_kcal"] * ACTIVITY_FACTORS["sedentary"])
        goal_adjust = 1 + CALORIE_ADJUSTMENT.get(targets.get("goal", ""), 0.0)
        measured_target = round((sedentary_tdee + burned) * goal_adjust)
        if workout_min >= 45:
            notes.append(
                "Session over 45 minutes -- get 20-40 g protein within about "
                "2 hours, and carbohydrate alongside it if you train again today."
            )
        if steps >= 12000:
            notes.append(f"{steps:,} steps is a high-NEAT day; the extra "
                         f"{step_kcal} kcal is already counted below.")

        return {
            "estimated_activity_kcal": burned,
            "from_steps_kcal": step_kcal,
            "from_workout_kcal": workout_kcal,
            "sedentary_baseline_kcal": sedentary_tdee,
            "adjusted_calorie_target": measured_target,
            "profile_based_target": targets["daily_calorie_target"],
            "basis": (
                "Rebuilt from BMR at a sedentary baseline plus today's measured "
                "activity, so the activity_level multiplier is not applied twice."
            ),
            "extra_hydration_ml": round(workout_min * 12),
            "notes": notes,
            "caveat": "Activity energy is estimated from step count and session "
                      "length, not measured. Treat it as a direction, not a number.",
        }


fitness_service = FitnessService()
