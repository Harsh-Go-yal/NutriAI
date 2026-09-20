"""
Micronutrient adequacy against ICMR-NIN RDAs, with absorption modelling.

The point of this module is the gap between *intake* and *absorbed* intake.
An Indian vegetarian diet is often adequate on paper for iron and still leaves
the person anaemic, because non-heme iron absorption is knocked down by tea,
coffee, calcium and phytates, and lifted by vitamin C. Reporting intake alone
tells the user to eat more iron when the real fix is timing.

References
----------
RDAs: ICMR-NIN, "Nutrient Requirements for Indians -- RDA and EAR", 2020.
Absorption factors: Hurrell & Egli, Am J Clin Nutr 2010;91(5):1461S-7S
(iron bioavailability); Hallberg et al. on ascorbate enhancement and
calcium/polyphenol inhibition.
"""
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# ICMR-NIN RDA 2020, per day. Keys match the field names produced by
# scripts/build_ifct.py so a food's micronutrients dict can be compared
# directly against a person's requirement.
# ---------------------------------------------------------------------------

RDA = {
    "adult_man": {
        "iron_mg": 19, "calcium_mg": 1000, "zinc_mg": 17,
        "vitamin_a_ug": 1000, "vitamin_c_mg": 80, "folate_ug": 300,
        "magnesium_mg": 440, "thiamine_mg": 1.4, "riboflavin_mg": 2.0,
        "niacin_mg": 18, "vitamin_b6_mg": 1.9,
    },
    "adult_woman": {
        "iron_mg": 29, "calcium_mg": 1000, "zinc_mg": 13.2,
        "vitamin_a_ug": 840, "vitamin_c_mg": 65, "folate_ug": 220,
        "magnesium_mg": 370, "thiamine_mg": 1.4, "riboflavin_mg": 1.9,
        "niacin_mg": 14, "vitamin_b6_mg": 1.9,
    },
    "pregnant": {
        "iron_mg": 27, "calcium_mg": 1000, "zinc_mg": 14.5,
        "vitamin_a_ug": 900, "vitamin_c_mg": 80, "folate_ug": 570,
        "magnesium_mg": 440, "thiamine_mg": 2.0, "riboflavin_mg": 2.7,
        "niacin_mg": 16, "vitamin_b6_mg": 2.3,
    },
    "lactating": {
        "iron_mg": 23, "calcium_mg": 1200, "zinc_mg": 14.1,
        "vitamin_a_ug": 950, "vitamin_c_mg": 115, "folate_ug": 330,
        "magnesium_mg": 440, "thiamine_mg": 2.1, "riboflavin_mg": 2.6,
        "niacin_mg": 17, "vitamin_b6_mg": 2.5,
    },
    "adolescent_girl": {          # 13-15 y
        "iron_mg": 27, "calcium_mg": 1000, "zinc_mg": 12.8,
        "vitamin_a_ug": 800, "vitamin_c_mg": 70, "folate_ug": 220,
        "magnesium_mg": 335, "thiamine_mg": 1.4, "riboflavin_mg": 1.9,
        "niacin_mg": 14, "vitamin_b6_mg": 1.9,
    },
    "adolescent_boy": {           # 13-15 y
        "iron_mg": 22, "calcium_mg": 1000, "zinc_mg": 14.3,
        "vitamin_a_ug": 930, "vitamin_c_mg": 70, "folate_ug": 220,
        "magnesium_mg": 375, "thiamine_mg": 1.6, "riboflavin_mg": 2.1,
        "niacin_mg": 16, "vitamin_b6_mg": 2.0,
    },
    "child": {                    # 7-9 y
        "iron_mg": 15, "calcium_mg": 650, "zinc_mg": 7.6,
        "vitamin_a_ug": 500, "vitamin_c_mg": 45, "folate_ug": 140,
        "magnesium_mg": 205, "thiamine_mg": 1.1, "riboflavin_mg": 1.5,
        "niacin_mg": 11, "vitamin_b6_mg": 1.5,
    },
}

# Nutrients IFCT 2017 does not measure, so we can never report on them.
UNMEASURED = {
    "vitamin_b12_ug": (
        "IFCT 2017 does not measure vitamin B12, so this app cannot assess it. "
        "This matters for vegetarian diets, where B12 deficiency is common in "
        "India -- ask a clinician for a serum B12 test rather than relying on "
        "any food-tracking estimate."
    ),
}

DISPLAY = {
    "iron_mg": "Iron", "calcium_mg": "Calcium", "zinc_mg": "Zinc",
    "vitamin_a_ug": "Vitamin A", "vitamin_c_mg": "Vitamin C",
    "folate_ug": "Folate", "magnesium_mg": "Magnesium",
    "thiamine_mg": "Thiamine (B1)", "riboflavin_mg": "Riboflavin (B2)",
    "niacin_mg": "Niacin (B3)", "vitamin_b6_mg": "Vitamin B6",
}

# ---------------------------------------------------------------------------
# Absorption model (non-heme iron and zinc)
# ---------------------------------------------------------------------------

# Baseline fractional absorption from a mixed vegetarian meal.
BASE_ABSORPTION = {"iron_mg": 0.10, "zinc_mg": 0.26}

# Polyphenols in tea/coffee bind non-heme iron in the gut. The effect is
# large and time-dependent, which is what makes it actionable: the same cup
# an hour later costs almost nothing.
TEA_COFFEE_WITH_MEAL = 0.40      # ~60% reduction when taken with the meal
TEA_COFFEE_WITHIN_HOUR = 0.65    # ~35% reduction within an hour after

# Ascorbate reduces Fe3+ to the absorbable Fe2+ form and chelates it away
# from inhibitors. Saturates -- more vitamin C past a point adds little.
VITC_MAX_MULTIPLIER = 3.0
VITC_SATURATION_MG = 100.0

CALCIUM_INHIBITION_MG = 300.0    # per meal, above which iron uptake drops
CALCIUM_FACTOR = 0.50

# Wholegrain/legume phytate is the background inhibitor in Indian diets.
PHYTATE_FACTOR = 0.70

HEME_GROUPS = {"Animal Meat", "Poultry", "Marine Fish",
               "Fresh Water Fish and Shellfish", "Marine Shellfish",
               "Marine Mollusks"}
PHYTATE_GROUPS = {"Cereals and Millets", "Grain Legumes", "Nuts and Oil Seeds"}


def profile_key(age: Optional[int], gender: str,
                life_stage: Optional[str] = None) -> str:
    """Map a person onto an RDA row."""
    stage = (life_stage or "").strip().lower()
    if stage in {"pregnant", "lactating"}:
        return stage

    gender = (gender or "").strip().lower()
    age = age if age is not None else 30

    if age < 10:
        return "child"
    if age < 16:
        return "adolescent_girl" if gender.startswith("f") else "adolescent_boy"
    return "adult_woman" if gender.startswith("f") else "adult_man"


class MicronutrientService:
    def rda_for(self, age=None, gender="", life_stage=None) -> Dict[str, Any]:
        key = profile_key(age, gender, life_stage)
        return {"profile": key, "rda": dict(RDA[key]),
                "source": "ICMR-NIN RDA 2020"}

    def total_micros(self, items: List[Dict[str, Any]]) -> Dict[str, float]:
        """Sum the micronutrient dicts already scaled to portion size."""
        totals: Dict[str, float] = {}
        for item in items:
            for key, value in (item.get("micronutrients") or {}).items():
                if value is not None:
                    totals[key] = round(totals.get(key, 0.0) + value, 3)
        return totals

    # -- absorption -------------------------------------------------------

    def absorption(self, items: List[Dict[str, Any]],
                   context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Model how much of the meal's iron and zinc is actually absorbable,
        and explain each factor so the UI can show *why*.

        `context` accepts:
          tea_coffee_timing: "with_meal" | "within_hour" | "separated" | None
        """
        context = context or {}
        totals = self.total_micros(items)

        iron_total = totals.get("iron_mg", 0.0)
        vitamin_c = totals.get("vitamin_c_mg", 0.0)
        calcium = totals.get("calcium_mg", 0.0)

        heme_share = self._heme_share(items)
        factors, notes = [], []

        # Vitamin C enhancement, saturating.
        if vitamin_c > 0:
            ratio = min(vitamin_c / VITC_SATURATION_MG, 1.0)
            vitc_mult = 1.0 + (VITC_MAX_MULTIPLIER - 1.0) * ratio
            factors.append(("vitamin_c", round(vitc_mult, 2)))
            notes.append(
                f"{vitamin_c:.0f} mg vitamin C in this meal raises non-heme "
                f"iron absorption about {vitc_mult:.1f}x."
            )
        else:
            vitc_mult = 1.0
            notes.append(
                "No vitamin C in this meal. Adding lemon, amla, tomato or "
                "raw onion would raise iron absorption substantially."
            )

        # Tea / coffee timing -- the actionable one.
        timing = (context.get("tea_coffee_timing") or "").lower()
        if timing == "with_meal":
            tea_mult = TEA_COFFEE_WITH_MEAL
            notes.append(
                "Tea or coffee with the meal cuts non-heme iron absorption by "
                "roughly 60%. Moving it to 90 minutes after the meal removes "
                "almost all of this loss."
            )
        elif timing == "within_hour":
            tea_mult = TEA_COFFEE_WITHIN_HOUR
            notes.append(
                "Tea or coffee within an hour of the meal costs roughly 35% of "
                "the iron. A 90-minute gap is enough to avoid it."
            )
        else:
            tea_mult = 1.0
        if tea_mult < 1.0:
            factors.append(("tea_coffee", tea_mult))

        # Calcium competition.
        if calcium >= CALCIUM_INHIBITION_MG:
            factors.append(("calcium", CALCIUM_FACTOR))
            notes.append(
                f"{calcium:.0f} mg calcium in one sitting competes with iron "
                "for absorption. Milk, curd or a calcium tablet is better "
                "moved to a different meal than the iron-rich one."
            )

        # Phytates.
        if self._has_phytate(items):
            factors.append(("phytates", PHYTATE_FACTOR))
            notes.append(
                "Wholegrain and legume phytates lower mineral absorption. "
                "Soaking, sprouting or fermenting (idli/dosa batter, sprouted "
                "moong) reduces this."
            )

        multiplier = 1.0
        for _, value in factors:
            multiplier *= value

        # Heme iron absorbs at ~25% and is not affected by these inhibitors.
        nonheme = iron_total * (1 - heme_share)
        heme = iron_total * heme_share
        absorbed = (nonheme * BASE_ABSORPTION["iron_mg"] * multiplier
                    + heme * 0.25)

        # What a *timing* change alone could recover. Phytates are inherent to
        # the food and are not fixed by rescheduling, so they stay applied --
        # otherwise the advice claims a win the user cannot actually get.
        TIMING_FIXABLE = {"tea_coffee", "calcium"}
        timing_free = 1.0
        for name, value in factors:
            if name not in TIMING_FIXABLE:
                timing_free *= value
        baseline = nonheme * BASE_ABSORPTION["iron_mg"] * timing_free + heme * 0.25

        return {
            "iron_intake_mg": round(iron_total, 2),
            "iron_absorbed_mg": round(absorbed, 3),
            "absorption_rate": round(absorbed / iron_total, 3) if iron_total else 0.0,
            "heme_share": round(heme_share, 2),
            "modifiers": [{"factor": name, "multiplier": value}
                          for name, value in factors],
            "recoverable_mg": round(max(baseline - absorbed, 0), 3),
            "explanations": notes,
            "method": (
                "Non-heme iron modelled at 10% baseline absorption, heme at "
                "25%, adjusted for ascorbate, polyphenol timing, calcium load "
                "and phytates (Hurrell & Egli 2010)."
            ),
        }

    @staticmethod
    def _heme_share(items) -> float:
        """Fraction of iron coming from animal foods, which absorbs far better."""
        total = heme = 0.0
        for item in items:
            iron = (item.get("micronutrients") or {}).get("iron_mg") or 0
            total += iron
            if item.get("group") in HEME_GROUPS:
                heme += iron
        return (heme / total) if total else 0.0

    @staticmethod
    def _has_phytate(items) -> bool:
        return any(i.get("group") in PHYTATE_GROUPS for i in items)

    # -- adequacy ---------------------------------------------------------

    def assess(self, items, age=None, gender="", life_stage=None,
               context=None, days: int = 1) -> Dict[str, Any]:
        """
        Compare intake against the RDA and report gaps, with iron judged on
        absorbed rather than ingested amount.
        """
        ref = self.rda_for(age, gender, life_stage)
        rda, totals = ref["rda"], self.total_micros(items)
        absorption = self.absorption(items, context)

        rows = []
        for key, target in rda.items():
            target_total = target * days
            intake = totals.get(key, 0.0)

            row = {
                "nutrient": DISPLAY.get(key, key),
                "key": key,
                "intake": round(intake, 2),
                "rda": round(target_total, 2),
                "percent_rda": round(intake / target_total * 100, 1) if target_total else None,
                "unit": key.rsplit("_", 1)[-1],
            }

            if key == "iron_mg":
                # The number that actually determines iron status.
                row["absorbed"] = absorption["iron_absorbed_mg"]
                row["percent_rda_absorbed"] = round(
                    absorption["iron_absorbed_mg"] / (target_total * 0.10) * 100, 1
                ) if target_total else None
                row["note"] = (
                    "RDA percentage is based on absorbed iron, not the amount "
                    "on the plate."
                )

            row["status"] = (
                "deficient" if row["percent_rda"] is not None and row["percent_rda"] < 50
                else "low" if row["percent_rda"] is not None and row["percent_rda"] < 80
                else "adequate"
            )
            rows.append(row)

        rows.sort(key=lambda r: r["percent_rda"] if r["percent_rda"] is not None else 999)
        gaps = [r for r in rows if r["status"] in {"deficient", "low"}]

        return {
            "profile": ref["profile"],
            "rda_source": ref["source"],
            "period_days": days,
            "nutrients": rows,
            "gaps": gaps,
            "absorption": absorption,
            "cannot_assess": [
                {"nutrient": k, "reason": v} for k, v in UNMEASURED.items()
            ],
            "headline": self._headline(gaps, absorption),
        }

    @staticmethod
    def _headline(gaps, absorption) -> str:
        """The one sentence worth saying out loud."""
        recoverable = absorption.get("recoverable_mg", 0)
        blockers = {m["factor"] for m in absorption.get("modifiers", [])}
        timing_blockers = blockers & {"tea_coffee", "calcium"}

        # Only claim a timing win when there is actually a timing blocker to
        # move; otherwise this reads as advice the user has already followed.
        if recoverable >= 0.2 and timing_blockers:
            what = ("tea or coffee" if "tea_coffee" in timing_blockers
                    else "milk, curd or a calcium supplement")
            return (
                f"Iron intake is not the problem -- absorption is. About "
                f"{recoverable:.1f} mg more iron per day is available just by "
                f"moving {what} 90 minutes away from this meal."
            )
        if gaps:
            worst = gaps[0]
            return (
                f"{worst['nutrient']} is the biggest gap at "
                f"{worst['percent_rda']:.0f}% of the ICMR RDA."
            )
        return "All assessed micronutrients meet the ICMR-NIN RDA for this profile."


micronutrient_service = MicronutrientService()
