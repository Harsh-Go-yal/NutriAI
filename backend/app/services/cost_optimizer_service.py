"""
Nutrition-per-rupee optimiser.

Given a set of nutrient shortfalls and a budget, find the cheapest basket of
foods that closes them. This is a linear program, not a language-model
question: minimise cost subject to nutrient constraints. Solving it with an
LLM would be slower, non-reproducible and wrong.

    minimise   sum(price_i * kg_i)
    subject to sum(nutrient_ij * kg_i) >= gap_j   for each nutrient j
               0 <= kg_i <= max_kg_i

Prices come from app/data/market_prices.json, which is sample data -- see the
warning inside that file.
"""
import json
import logging
import os
from typing import Any, Dict, List, Optional

from app.services.nutrition_service import nutrition_service

logger = logging.getLogger(__name__)

PRICES_PATH = os.path.join(os.path.dirname(__file__), "..", "data",
                           "market_prices.json")

# Nobody should be told to eat 3 kg of spinach to hit an iron target, so each
# food is capped at a sane weekly quantity.
DEFAULT_MAX_KG = 2.0
# A cost-minimising LP will happily answer "eat only soya beans". Capping any
# single food's contribution to a given nutrient forces a basket a person
# would actually cook from.
MAX_SINGLE_FOOD_SHARE = 0.5

MAX_KG_OVERRIDES = {
    "Lemon, acid": 0.3,
    "Sesame seeds, black": 0.3,
    "Groundnut, kernel": 0.5,
    "Paneer": 1.0,
    "Egg, poultry, whole, raw": 1.2,
}

# Which gaps the optimiser can actually solve for, and where the value lives
# on a food record.
SUPPORTED = {
    "protein_g": ("macro", "protein_g"),
    "calories": ("macro", "calories"),
    "iron_mg": ("micro", "iron_mg"),
    "calcium_mg": ("micro", "calcium_mg"),
    "zinc_mg": ("micro", "zinc_mg"),
    "folate_ug": ("micro", "folate_ug"),
    "vitamin_a_ug": ("micro", "vitamin_a_ug"),
    "vitamin_c_mg": ("micro", "vitamin_c_mg"),
}


class CostOptimizerService:
    def __init__(self):
        self.meta: Dict[str, Any] = {}
        self.priced_foods: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        try:
            with open(PRICES_PATH, encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as e:
            logger.warning(f"Could not load market prices: {e}")
            return

        self.meta = {k: v for k, v in payload.items() if k != "prices"}

        for row in payload.get("prices", []):
            food = nutrition_service.lookup(row["food"])
            if not food:
                logger.debug(f"Priced food not in IFCT: {row['food']}")
                continue
            self.priced_foods.append({
                "name": food["name"],
                "price_per_kg": row["price_per_kg"],
                "group": food.get("group"),
                "tags": food.get("tags") or [],
                "macro": {k: food.get(k) for k in ("calories", "protein_g",
                                                   "carbs_g", "fat_g")},
                "micro": food.get("micronutrients") or {},
            })

        logger.info(f"Cost optimiser loaded {len(self.priced_foods)} priced foods.")

    def _nutrient_per_kg(self, food: Dict[str, Any], key: str) -> float:
        """Foods are stored per 100 g; prices are per kg."""
        kind, field = SUPPORTED[key]
        per_100g = (food[kind] or {}).get(field) or 0
        return per_100g * 10.0

    def optimize(self, gaps: Dict[str, float], budget: Optional[float] = None,
                 diet_type: Optional[str] = None,
                 exclude: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Cheapest basket closing `gaps` (nutrient key -> amount still needed).
        """
        gaps = {k: v for k, v in (gaps or {}).items()
                if k in SUPPORTED and v and v > 0}
        if not gaps:
            return {"status": "nothing_to_close", "basket": [], "total_cost": 0.0,
                    "message": "No supported nutrient gaps were supplied."}

        exclude = {e.lower() for e in (exclude or [])}
        candidates = [
            f for f in self.priced_foods
            if f["name"].lower() not in exclude
            and (diet_type not in {"veg", "vegetarian", "vegan"}
                 or "veg" in f["tags"])
        ]
        if not candidates:
            return {"status": "no_candidates", "basket": [], "total_cost": 0.0,
                    "message": "No priced foods match these dietary restrictions."}

        result = self._solve_lp(candidates, gaps, budget)
        if result is None:
            result = self._solve_greedy(candidates, gaps, budget)

        result["prices"] = {
            "source": self.meta.get("region"),
            "warning": self.meta.get("warning"),
            "last_updated": self.meta.get("last_updated"),
        }
        result["gaps_targeted"] = gaps
        return result

    # -- solvers -----------------------------------------------------------

    def _solve_lp(self, candidates, gaps, budget):
        try:
            from scipy.optimize import linprog
        except ImportError:
            logger.info("scipy unavailable; using greedy fallback.")
            return None

        cost = [f["price_per_kg"] for f in candidates]

        # linprog does A_ub @ x <= b_ub, so nutrient floors are negated.
        a_ub, b_ub = [], []
        for key, needed in gaps.items():
            a_ub.append([-self._nutrient_per_kg(f, key) for f in candidates])
            b_ub.append(-needed)

        # Diversity: nutrient_ij * kg_i <= share * gap_j, one row per
        # (food, nutrient) pair. Linear, so the LP stays an LP.
        for key, needed in gaps.items():
            for idx, food in enumerate(candidates):
                per_kg = self._nutrient_per_kg(food, key)
                if per_kg <= 0:
                    continue
                row = [0.0] * len(candidates)
                row[idx] = per_kg
                a_ub.append(row)
                b_ub.append(needed * MAX_SINGLE_FOOD_SHARE)

        bounds = [(0, MAX_KG_OVERRIDES.get(f["name"], DEFAULT_MAX_KG))
                  for f in candidates]

        try:
            res = linprog(c=cost, A_ub=a_ub, b_ub=b_ub, bounds=bounds,
                          method="highs")
        except Exception as e:
            logger.warning(f"LP solve failed: {e}")
            return None

        if not res.success:
            return {
                "status": "infeasible",
                "basket": [],
                "total_cost": 0.0,
                "solver": "scipy linprog (HiGHS)",
                "message": (
                    "These targets cannot be met from the priced food list "
                    "within per-food quantity caps. Widen the food list or "
                    "relax the targets."
                ),
            }

        basket = []
        for food, kg in zip(candidates, res.x):
            kg = float(kg)          # numpy float is not JSON-serialisable
            grams = round(kg * 1000)
            if grams < 10:          # ignore solver dust
                continue
            basket.append({
                "food": food["name"],
                "grams": grams,
                "cost": round(kg * food["price_per_kg"], 2),
                "provides": {k: round(float(self._nutrient_per_kg(food, k) * kg), 2)
                             for k in gaps},
            })

        basket.sort(key=lambda b: -b["cost"])
        total = round(sum(b["cost"] for b in basket), 2)

        return {
            "status": "optimal",
            "solver": "scipy linprog (HiGHS)",
            "basket": basket,
            "total_cost": total,
            "within_budget": (budget is None or total <= budget),
            "budget": budget,
            "delivered": self._delivered(basket, gaps),
            "message": self._describe(basket, gaps, total),
        }

    def _solve_greedy(self, candidates, gaps, budget):
        """
        Fallback when scipy is missing: repeatedly buy whichever food closes
        the most remaining need per rupee. Not optimal, but explicable.
        """
        remaining = dict(gaps)
        basket, total = [], 0.0

        for _ in range(len(candidates)):
            if not any(v > 0 for v in remaining.values()):
                break

            best, best_value = None, 0.0
            for food in candidates:
                if any(b["food"] == food["name"] for b in basket):
                    continue
                value = sum(
                    min(self._nutrient_per_kg(food, k), need) / need
                    for k, need in remaining.items() if need > 0
                ) / max(food["price_per_kg"], 1)
                if value > best_value:
                    best, best_value = food, value

            if best is None:
                break

            cap = MAX_KG_OVERRIDES.get(best["name"], DEFAULT_MAX_KG)
            kg = 0.0
            for key, need in remaining.items():
                if need > 0:
                    per_kg = self._nutrient_per_kg(best, key)
                    if per_kg > 0:
                        kg = max(kg, min(need / per_kg, cap))
            kg = min(kg, cap)
            if kg <= 0:
                break

            cost = kg * best["price_per_kg"]
            if budget is not None and total + cost > budget:
                break

            basket.append({
                "food": best["name"],
                "grams": round(kg * 1000),
                "cost": round(cost, 2),
                "provides": {k: round(self._nutrient_per_kg(best, k) * kg, 2)
                             for k in gaps},
            })
            total += cost
            for key in remaining:
                remaining[key] = max(
                    remaining[key] - self._nutrient_per_kg(best, key) * kg, 0
                )

        return {
            "status": "heuristic",
            "solver": "greedy nutrient-per-rupee (scipy not installed)",
            "basket": basket,
            "total_cost": round(total, 2),
            "within_budget": (budget is None or total <= budget),
            "budget": budget,
            "delivered": self._delivered(basket, gaps),
            "message": self._describe(basket, gaps, round(total, 2)),
        }

    # -- reporting ---------------------------------------------------------

    @staticmethod
    def _delivered(basket, gaps):
        out = {}
        for key, needed in gaps.items():
            got = float(sum(b["provides"].get(key, 0) for b in basket))
            out[key] = {"needed": round(float(needed), 2), "provided": round(got, 2),
                        "percent": round(got / needed * 100, 1) if needed else None}
        return out

    @staticmethod
    def _describe(basket, gaps, total):
        if not basket:
            return "No basket could be assembled for these targets."
        names = ", ".join(b["food"] for b in basket[:3])
        gap_names = ", ".join(k.rsplit("_", 1)[0] for k in gaps)
        return (f"Rs {total:.0f} of {names} closes your {gap_names} gap for "
                f"the period.")


cost_optimizer_service = CostOptimizerService()
