"""
Household mode: one pot, one photo, per-person nutrition.

Indian families eat from shared serving dishes and one person cooks for
everyone, so per-person logging is the wrong unit. This splits a shared meal
across household members and judges each share against that person's own
ICMR-NIN RDA -- the diabetic father and the anaemic teenage daughter get
different verdicts on the same dish.

Split basis: energy requirement. Each member's share of the pot is
proportional to their estimated daily energy need unless explicit shares are
given. That is an assumption, not an observation, and it is reported as one.
"""
from typing import Any, Dict, List, Optional

from app.services.clinical_safety_service import clinical_safety_service
from app.services.fitness_service import fitness_service
from app.services.micronutrient_service import micronutrient_service

# Below this age, protein adequacy is a growth question against the RDA, not a
# muscle-protein-synthesis question.
MPS_MIN_AGE = 13


class HouseholdService:
    def energy_need(self, member: Dict[str, Any]) -> float:
        """Rough daily energy requirement, used only to weight the split."""
        weight = member.get("weight_kg") or 55
        height = member.get("height_cm") or 160
        age = member.get("age") or 30
        gender = member.get("gender") or "female"
        activity = member.get("activity_level") or "moderate"
        return fitness_service.targets(
            weight, height, age, gender, activity, "maintenance"
        )["tdee_kcal"]

    def split(self, items: List[Dict[str, Any]], members: List[Dict[str, Any]],
              shares: Optional[Dict[str, float]] = None,
              context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Divide a shared meal and assess each member's portion.

        `items` are the scaled foods for the whole pot. `shares` optionally
        maps member name -> fraction (must sum to ~1); otherwise the split is
        proportional to energy need.
        """
        if not members:
            raise ValueError("household split requires at least one member.")

        if shares:
            total_share = sum(shares.values()) or 1.0
            weights = {m["name"]: shares.get(m["name"], 0) / total_share
                       for m in members}
            basis = "explicit shares supplied by the user"
        else:
            needs = {m["name"]: self.energy_need(m) for m in members}
            total_need = sum(needs.values()) or 1.0
            weights = {name: need / total_need for name, need in needs.items()}
            basis = ("estimated energy requirement (Mifflin-St Jeor x activity); "
                     "an assumption, not an observation of who ate what")

        per_person = []
        for member in members:
            name = member["name"]
            weight = weights.get(name, 0)
            portion = [self._scale_item(i, weight) for i in items]

            assessment = micronutrient_service.assess(
                portion,
                age=member.get("age"),
                gender=member.get("gender"),
                life_stage=member.get("life_stage"),
                context=context,
            )
            screening = clinical_safety_service.screen(
                items=portion,
                conditions=member.get("medical_conditions"),
                medications=member.get("medications"),
            )
            # Leucine/MPS framing is resistance-training guidance for adults.
            # Showing a child "add 47 g paneer for muscle protein synthesis"
            # is both wrong and off-putting -- children need adequate protein
            # for growth, judged against the RDA, not an MPS threshold.
            age = member.get("age")
            protein_quality = (
                fitness_service.meal_protein_quality(portion)
                if age is None or age >= MPS_MIN_AGE else None
            )

            per_person.append({
                "name": name,
                "share": round(weight, 3),
                "profile": assessment["profile"],
                "life_stage": member.get("life_stage"),
                "conditions": member.get("medical_conditions") or [],
                "totals": self._totals(portion),
                "top_gaps": assessment["gaps"][:3],
                "iron_absorption": assessment["absorption"],
                "protein_quality": protein_quality,
                "safety": {
                    "safe_to_show": screening["safe_to_show"],
                    "findings": screening["findings"],
                },
                "headline": assessment["headline"],
            })

        return {
            "members": per_person,
            "split_basis": basis,
            "shared_meal_totals": self._totals(items),
            "cooking_plan": self.cooking_plan(per_person),
            "caveat": (
                "Per-person figures assume the pot was divided in the "
                "proportions shown. Adjust the shares if someone ate more."
            ),
        }

    def cooking_plan(self, per_person: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        One cooking session that serves everyone, with the minimum number of
        separate preparations. Conflicting needs become per-person tweaks on
        the shared base rather than separate dishes.
        """
        tweaks, escalate = [], []

        for person in per_person:
            name = person["name"]

            for finding in person["safety"]["findings"]:
                if finding["severity"] == "block":
                    escalate.append({"member": name, "reason": finding["message"],
                                     "action": finding["action"]})
                    continue
                tweaks.append({
                    "member": name,
                    "tweak": finding["action"],
                    "because": finding["message"],
                    "severity": finding["severity"],
                })

            for gap in person["top_gaps"][:2]:
                if gap["status"] == "deficient":
                    tweaks.append({
                        "member": name,
                        "tweak": f"Add a {gap['nutrient'].lower()}-rich side to "
                                 f"{name}'s plate",
                        "because": f"{gap['nutrient']} at {gap['percent_rda']:.0f}% "
                                   f"of their RDA",
                        "severity": "info",
                    })

            pq = person.get("protein_quality") or {}
            if pq.get("triggers_mps") is False and pq.get("close_the_gap_with"):
                tweaks.append({
                    "member": name,
                    "tweak": f"Add {pq['close_the_gap_with'][0]} to {name}'s serving",
                    "because": "meal is below the leucine threshold for muscle "
                               "protein synthesis",
                    "severity": "info",
                })

        return {
            "shared_base": "Cook the base dish once for the whole household.",
            "per_person_tweaks": tweaks,
            "requires_dietitian": escalate,
            "separate_dishes_needed": len({t["member"] for t in tweaks
                                           if t["severity"] == "warn"}),
        }

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _scale_item(item: Dict[str, Any], weight: float) -> Dict[str, Any]:
        out = {"name": item.get("name"), "group": item.get("group"),
               "source": item.get("source"),
               "portion_g": round((item.get("portion_g") or 0) * weight, 1)}

        for field in ("calories", "protein_g", "carbs_g", "fat_g", "fiber_g"):
            value = item.get(field)
            out[field] = round(value * weight, 2) if value is not None else None

        for field in ("amino_acids_g", "micronutrients"):
            block = item.get(field)
            if block:
                out[field] = {k: round(v * weight, 3) for k, v in block.items()}
        return out

    @staticmethod
    def _totals(items: List[Dict[str, Any]]) -> Dict[str, float]:
        totals: Dict[str, float] = {}
        for field in ("calories", "protein_g", "carbs_g", "fat_g", "fiber_g"):
            values = [i[field] for i in items if i.get(field) is not None]
            totals[field] = round(sum(values), 2) if values else 0.0
        return totals


household_service = HouseholdService()
