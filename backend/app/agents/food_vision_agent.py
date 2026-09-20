import logging
from typing import Any, Dict

from app.agents.base_agent import BaseAgent
from app.agents.prompts.food_vision_prompt import FOOD_VISION_SYSTEM_PROMPT
from app.config import settings
from app.core.groq_client import groq_client
from app.services.nutrition_service import nutrition_service

logger = logging.getLogger(__name__)

# Feature #4: the honest half of Indian food vision.
#
# Pure image models fail on sambhar, biryani and rajma because the calories
# hide in oil and ghee that are not visible. Rather than claim the vision
# model solved that, we ask two cheap questions and apply a cooking-method
# multiplier over the IFCT values. Restaurant food carries a real oil penalty.
COOKING_MULTIPLIERS = {
    "home": {"fat_g": 1.0, "calories": 1.0,
             "note": "Home-cooked: IFCT values used as measured."},
    "restaurant": {"fat_g": 2.2, "calories": 1.35,
                   "note": "Restaurant cooking uses substantially more oil, "
                           "ghee and cream than home cooking; fat is scaled "
                           "2.2x and energy 1.35x."},
    "street": {"fat_g": 2.6, "calories": 1.45,
               "note": "Street food is typically deep-fried in reused oil; "
                       "fat is scaled 2.6x and energy 1.45x."},
}

# Second question: how much oil went in, relative to the method's default.
OIL_LEVELS = {
    "low": 0.6,
    "normal": 1.0,
    "heavy": 1.6,
}

# Added oil is fat and energy only -- it carries no protein or micronutrients,
# so multipliers must never touch those fields.
SCALED_FIELDS = ("fat_g", "calories")


class FoodVisionAgent(BaseAgent):
    """
    Turns a meal photo into resolved, per-ingredient nutrition.

    The split matters: the model only names ingredients and estimates grams,
    and every nutrient number comes from IFCT 2017 or USDA. That keeps
    measured values in the log instead of plausible-sounding invented ones.
    """

    def __init__(self):
        self.name = "food_vision"
        self.model_id = settings.FOOD_VISION_MODEL
        self.system_prompt = FOOD_VISION_SYSTEM_PROMPT

    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        image_data_url = input_data.get("image_data_url")
        if not image_data_url:
            raise ValueError("food_vision requires an 'image_data_url'.")

        response_schema = {
            "type": "object",
            "properties": {
                "dish_name": {"type": "string"},
                "components": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "estimated_portion_g": {"type": "integer"},
                            "confidence": {"type": "number"},
                        },
                        "required": ["name", "estimated_portion_g", "confidence"],
                    },
                },
                "notes": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["dish_name", "components", "notes"],
        }

        seen = await groq_client.chat_json_vision(
            system_prompt=self.system_prompt,
            image_data_url=image_data_url,
            response_schema=response_schema,
            model=self.model_id,
            user_text=input_data.get("user_hint") or "Identify this meal.",
        )

        components = seen.get("components") or []
        notes = list(seen.get("notes") or [])

        # The two questions that carry the oil the camera cannot see.
        cooking = (input_data.get("cooking_method") or "home").lower()
        oil_level = (input_data.get("oil_level") or "normal").lower()
        if cooking in COOKING_MULTIPLIERS:
            notes.append(COOKING_MULTIPLIERS[cooking]["note"])
        if oil_level != "normal" and oil_level in OIL_LEVELS:
            notes.append(
                f"Oil reported as '{oil_level}', scaling added fat by "
                f"{OIL_LEVELS[oil_level]}x on top of the cooking method."
            )

        items, unresolved = [], []
        for comp in components:
            name = (comp.get("name") or "").strip()
            grams = comp.get("estimated_portion_g") or 0
            if not name or grams <= 0:
                continue

            food = await nutrition_service.resolve(name)
            if not food:
                unresolved.append({"name": name, "estimated_portion_g": grams})
                continue

            scaled = nutrition_service.scale(food, grams)
            scaled = self._apply_cooking_method(scaled, cooking, oil_level)
            scaled["detected_as"] = name
            scaled["vision_confidence"] = comp.get("confidence")
            scaled["match_confidence"] = food.get("confidence")
            scaled["match_score"] = food.get("match_score")
            if food.get("alternatives"):
                scaled["alternatives"] = food["alternatives"]
            items.append(scaled)

        totals = {}
        for field in ("calories", "protein_g", "carbs_g", "fat_g", "fiber_g"):
            values = [i[field] for i in items if i.get(field) is not None]
            totals[field] = round(sum(values), 2) if values else 0.0

        if unresolved:
            notes.append(
                "No composition data found for: "
                + ", ".join(u["name"] for u in unresolved)
                + ". These are excluded from the totals."
            )

        return {
            "dish_name": seen.get("dish_name") or "Unidentified meal",
            "cooking_method": cooking,
            "oil_level": oil_level,
            "estimation_method": (
                "Hybrid: the vision model identifies ingredients and portions "
                "only; nutrients come from IFCT 2017 / USDA; oil and energy are "
                "adjusted by a cooking-method multiplier from two user "
                "questions, because oil content is not visible in a photo."
            ),
            "items": items,
            "unresolved": unresolved,
            "totals": totals,
            "protein_quality": self._protein_quality(items),
            "notes": notes,
            "sources": sorted({i["source"] for i in items if i.get("source")}),
            "disclaimer": (
                "Portion sizes are estimated from a single photo and are the "
                "largest source of error here -- check the grams before logging. "
                "Nutrient values are looked up, not estimated."
            ),
        }

    @staticmethod
    def _apply_cooking_method(item, cooking, oil_level):
        """
        Scale fat and energy for how the food was cooked.

        Protein, micronutrients and amino acids are deliberately untouched --
        added cooking oil contributes fat and calories and nothing else, so
        scaling them would silently inflate the nutrition report.
        """
        method = COOKING_MULTIPLIERS.get(cooking)
        if not method:
            return item

        oil_mult = OIL_LEVELS.get(oil_level, 1.0)
        for field in SCALED_FIELDS:
            value = item.get(field)
            if value is None:
                continue
            extra = (method[field] - 1.0) * oil_mult
            item[field] = round(value * (1.0 + extra), 2)

        if cooking != "home" or oil_level != "normal":
            item["cooking_adjusted"] = True
        return item

    @staticmethod
    def _protein_quality(items):
        """
        Sum essential amino acids and name the limiting one.

        Only IFCT rows carry amino acids, so this is skipped when the meal
        resolved entirely through USDA.
        """
        # mg of each essential amino acid per g of protein, FAO/WHO adult
        # scoring pattern -- the reference a mixed meal is judged against.
        reference = {
            "his": 15, "ile": 30, "leu": 59, "lys": 45, "met": 22,
            "phe": 38, "thr": 23, "trp": 6, "val": 39,
        }

        totals, protein = {}, 0.0
        for item in items:
            aminos = item.get("amino_acids_g")
            if not aminos:
                continue
            protein += item.get("protein_g") or 0
            for key, value in aminos.items():
                totals[key] = totals.get(key, 0.0) + value

        if not totals or protein <= 0:
            return None

        scores = {}
        for key, ref in reference.items():
            if key in totals:
                # mg per g of protein, against the reference requirement
                scores[key] = round((totals[key] * 1000 / protein) / ref, 2)

        if not scores:
            return None

        limiting = min(scores, key=scores.get)
        return {
            "essential_amino_acids_g": {k: round(v, 3) for k, v in totals.items()
                                        if k in reference},
            "amino_acid_scores": scores,
            "limiting_amino_acid": limiting,
            "limiting_score": scores[limiting],
            "note": (
                f"Limiting amino acid is {limiting} at {scores[limiting]:.2f} of the "
                "FAO/WHO reference. Below 1.0 means this meal's protein is "
                "incomplete on its own; pairing cereals with pulses raises it."
            ),
        }
