import json
import logging
import os
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
IFCT_PATH = os.path.join(DATA_DIR, "ifct2017.json")
LEGACY_PATH = os.path.join(DATA_DIR, "indian_food_nutrition.json")

USDA_SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"

# USDA nutrient ids -> our field names (per 100 g)
USDA_NUTRIENTS = {
    1008: "calories",   # Energy (kcal)
    1003: "protein_g",
    1005: "carbs_g",
    1004: "fat_g",
    1079: "fiber_g",
}

# Words that add no discriminating power when matching a dish to a food row.
STOPWORDS = {
    "raw", "cooked", "boiled", "fresh", "dried", "whole", "plain",
    "and", "with", "of", "the", "a", "in", "or",
}

# Below this a candidate is a coincidence, not a match, and we fall through
# to USDA rather than return a confidently wrong number.
MATCH_THRESHOLD = 0.80

# IFCT catalogues ingredients, not prepared dishes, so these can never have a
# correct IFCT row. Matching them anyway produced nonsense ('chapati' scored
# against turkey breast, 'dosa' against a Telugu name for cucumber), so they
# skip IFCT and go straight to USDA, which does carry composite foods.
PREPARED_DISHES = {
    "chapati", "chapatti", "roti", "phulka", "naan", "paratha", "puri", "poori",
    "idli", "dosa", "vada", "upma", "poha", "uttapam", "appam",
    "samosa", "pakora", "biryani", "pulao", "khichdi", "halwa", "kheer",
    "curd", "dahi", "yogurt", "lassi", "buttermilk",
    "pizza", "pasta", "burger", "sandwich", "noodles", "cake", "biscuit",
}

# A bare ingredient name almost never means the spice of the same name
# ('mango' -> the fruit, not 'Mango ginger'), so spices lose ties.
DEPRIORITISED_GROUPS = {"Condiments and Spices"}

# Fuzzy token matching is restricted to long tokens at a high ratio; short
# tokens must match exactly (see _score).
FUZZY_MIN_LEN = 6
FUZZY_MIN_RATIO = 0.88

# Everyday Indian names that IFCT files under a different head word. Without
# these the lookup misses foods the database genuinely contains.
QUERY_SYNONYMS = {
    "toor dal": "arhar dal",
    "tur dal": "arhar dal",
    "tuvar dal": "arhar dal",
    "chana dal": "bengal gram dal",
    "kabuli chana": "bengal gram whole",
    "moong dal": "mung dal",
    "masoor dal": "lentil dal",
    "urad dal": "urad dal",
    "atta": "wheat flour",
    "maida": "refined wheat flour",
    "dahi": "curd",
    "jeera": "cumin seeds",
    "haldi": "turmeric powder",
    "aloo": "potato",
    "gobhi": "cauliflower",
    "gobi": "cauliflower",
    "baingan": "brinjal",
    "bhindi": "ladies finger",
    "methi": "fenugreek leaves",
    "sarson": "mustard leaves",
    "lauki": "bottle gourd",
    "matar": "green peas",
}


def _normalize(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"\(.*?\)", " ", text)       # drop parenthetical qualifiers
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(text: str) -> set:
    return {t for t in _normalize(text).split() if t and t not in STOPWORDS}


class NutritionService:
    """
    Nutrient lookup backed by IFCT 2017 (local, Indian, lab-measured), with an
    optional USDA FoodData Central fallback for foods IFCT does not cover.

    IFCT is consulted first because it is measured on Indian foods; USDA is
    only reached for misses, so a missing or rate-limited USDA key degrades
    the service rather than breaking it.
    """

    def __init__(self):
        self.foods: List[Dict[str, Any]] = []
        self.source_meta: Dict[str, Any] = {}
        self._index: List[Dict[str, Any]] = []
        self._usda_cache: Dict[str, Optional[Dict[str, Any]]] = {}
        self._llm_cache: Dict[str, Optional[Dict[str, Any]]] = {}
        self._load()

    # ---------- loading ----------

    def _load(self):
        try:
            with open(IFCT_PATH, encoding="utf-8") as f:
                payload = json.load(f)
            self.foods = payload.get("foods", [])
            self.source_meta = {k: v for k, v in payload.items() if k != "foods"}
            logger.info(f"Loaded {len(self.foods)} foods from IFCT 2017.")
        except Exception as e:
            logger.warning(f"Could not load IFCT data ({e}); falling back to legacy table.")
            try:
                with open(LEGACY_PATH, encoding="utf-8") as f:
                    self.foods = json.load(f)
                self.source_meta = {"source": "legacy indian_food_nutrition.json"}
            except Exception:
                self.foods = []

        self._build_index()

    def _build_index(self):
        """Flatten every name and alias into one searchable list of terms."""
        self._index = []
        for food in self.foods:
            terms = [(food["name"], True)]
            terms += [(a, False) for a in (food.get("aliases") or [])]
            for term, is_primary in terms:
                norm = _normalize(term)
                if norm:
                    self._index.append({
                        "term": norm,
                        "tokens": _tokens(term),
                        "is_primary": is_primary,
                        "food": food,
                    })

    # ---------- retrieval ----------

    def get_all_foods(self, diet_type: Optional[str] = None,
                      compact: bool = True) -> List[Dict[str, Any]]:
        """
        Foods to offer the diet planner. Filtering by diet_type keeps the
        prompt small and stops the model proposing food the user will not eat.
        """
        foods = self.foods
        if diet_type:
            key = diet_type.strip().lower()
            if key in {"veg", "vegetarian", "vegan"}:
                foods = [f for f in foods if "veg" in (f.get("tags") or [])]
            elif key == "eggetarian":
                foods = [f for f in foods
                         if {"veg", "eggetarian"} & set(f.get("tags") or [])]

        if not compact:
            return foods

        return [{
            "name": f["name"],
            "calories": f.get("calories"),
            "protein_g": f.get("protein_g"),
            "carbs_g": f.get("carbs_g"),
            "fat_g": f.get("fat_g"),
        } for f in foods if f.get("calories") is not None]

    def _score(self, q_tokens: set, entry: Dict[str, Any], query: str) -> float:
        """
        Token-level score. Whole-string fuzzy ratios were tried first and are
        useless at these lengths -- they scored 'chapati' against 'Onion, stalk'
        at 0.69. Every query token must find a partner token in the candidate,
        which is what actually separates a real match from a coincidence.
        """
        if entry["term"] == query:
            return 1.0

        t_tokens = entry["tokens"]
        if not q_tokens or not t_tokens:
            return 0.0

        matched = 0.0
        for qt in q_tokens:
            best_tok = 0.0
            for tt in t_tokens:
                if qt == tt:
                    best_tok = 1.0
                    break
                # Fuzzy matching is only safe on long tokens. On short ones it
                # equates unrelated words -- it scored 'mango' against a Bengali
                # alias of quail meat at 0.91 -- so short tokens must match exactly.
                if len(qt) >= FUZZY_MIN_LEN and len(tt) >= FUZZY_MIN_LEN:
                    r = SequenceMatcher(None, qt, tt).ratio()
                    if r >= FUZZY_MIN_RATIO and r > best_tok:
                        best_tok = r
            matched += best_tok

        if not matched:
            return 0.0

        coverage = matched / len(q_tokens)          # how much of the query is explained
        precision = matched / len(t_tokens)         # how much of the candidate is used
        # Rounded so a score that is exactly at the threshold in exact
        # arithmetic is not rejected by float drift (0.7999... < 0.80).
        return round(coverage * 0.7 + precision * 0.3, 4)

    def lookup(self, name: str) -> Optional[Dict[str, Any]]:
        """Best IFCT match for a food name, or None below the score floor."""
        query = _normalize(name)
        query = QUERY_SYNONYMS.get(query, query)
        if not query or not self._index:
            return None

        if any(word in PREPARED_DISHES for word in query.split()):
            return None

        q_tokens = {t for t in query.split() if t not in STOPWORDS} or set(query.split())

        scored = []
        for entry in self._index:
            score = self._score(q_tokens, entry, query)
            if score > 0:
                scored.append((score, entry))

        if not scored:
            return None

        top = max(s for s, _ in scored)
        if top < MATCH_THRESHOLD:
            return None

        # Several foods can share an alias ("Palak" is both Spinach and
        # Basella leaves). Prefer the one the alias fits most often, then the
        # plainer name -- that lands on the everyday food rather than a
        # regional namesake.
        tied = [e for s, e in scored if s == top]
        alias_hits = {}
        for e in tied:
            key = e["food"]["code"]
            alias_hits[key] = alias_hits.get(key, 0) + 1

        best = min(
            tied,
            key=lambda e: (
                e["food"].get("group") in DEPRIORITISED_GROUPS,  # spices lose
                not e["is_primary"],                       # own name beats alias
                -alias_hits[e["food"]["code"]],            # then most alias support
                len(e["food"]["name"]),                    # then the plainer entry
            ),
        )

        food = dict(best["food"])
        food["match_score"] = round(top, 3)
        food["matched_on"] = best["term"]
        food["source"] = "IFCT 2017"
        # Anything short of an exact hit is worth a human glance, especially
        # where IFCT splits one food into cultivars (7 mango varieties).
        food["confidence"] = "exact" if top >= 1.0 else ("strong" if top >= 0.9 else "weak")

        seen, alts = {best["food"]["code"]}, []
        for s, e in sorted(scored, key=lambda x: -x[0]):
            code = e["food"]["code"]
            if code in seen:
                continue
            seen.add(code)
            alts.append({"name": e["food"]["name"], "score": round(s, 3)})
            if len(alts) == 3:
                break
        food["alternatives"] = alts
        return food

    async def lookup_usda(self, name: str) -> Optional[Dict[str, Any]]:
        """USDA FoodData Central fallback. Returns None if unavailable."""
        if name in self._usda_cache:
            return self._usda_cache[name]

        key = settings.USDA_API_KEY or "DEMO_KEY"
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(
                    USDA_SEARCH_URL,
                    params={
                        "query": name,
                        "pageSize": 1,
                        "dataType": "Foundation,SR Legacy",
                        "api_key": key,
                    },
                    timeout=15.0,
                )
            if res.status_code != 200:
                logger.warning(f"USDA lookup for '{name}' returned {res.status_code}.")
                self._usda_cache[name] = None
                return None

            hits = res.json().get("foods") or []
            if not hits:
                self._usda_cache[name] = None
                return None

            hit = hits[0]
            food = {
                "name": hit.get("description"),
                "portion_g": 100,
                "source": "USDA FoodData Central",
                "fdc_id": hit.get("fdcId"),
            }
            for n in hit.get("foodNutrients") or []:
                field = USDA_NUTRIENTS.get(n.get("nutrientId"))
                if field:
                    food[field] = n.get("value")

            self._usda_cache[name] = food
            return food

        except Exception as e:
            logger.warning(f"USDA lookup for '{name}' failed: {e}")
            self._usda_cache[name] = None
            return None

    async def lookup_llm(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Last-resort estimate from the language model.

        Only reached when neither IFCT nor USDA has the food -- typically a
        composite restaurant dish or a regional preparation. The result is
        flagged `estimated: True` and carries a distinct `source`, because it
        is the one path in this service where the numbers were not measured
        by anyone. Callers and the UI must be able to tell the difference.
        """
        if name in self._llm_cache:
            return self._llm_cache[name]

        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "calories": {"type": "number"},
                "protein_g": {"type": "number"},
                "carbs_g": {"type": "number"},
                "fat_g": {"type": "number"},
                "fiber_g": {"type": "number"},
                "confidence": {"type": "string"},
                "basis": {"type": "string"},
            },
            "required": ["name", "calories", "protein_g", "carbs_g", "fat_g"],
        }

        try:
            # Imported here: the LLM client is only needed on this fallback
            # path, and a top-level import would couple every lookup to it.
            from app.core.groq_client import groq_client

            result = await groq_client.chat_json(
                system_prompt=(
                    "You are a food composition estimator for Indian foods. "
                    "Give values PER 100 g of the edible portion, as prepared. "
                    "Prefer typical home-cooked Indian preparation. State your "
                    "confidence honestly in `confidence` (high|medium|low) and "
                    "name what you based it on in `basis`. Do not invent "
                    "precision -- round sensibly."
                ),
                user_payload={"food": name},
                response_schema=schema,
                model=settings.RECOMMENDATION_MODEL,
            )
        except Exception as e:
            logger.warning(f"LLM nutrition estimate for '{name}' failed: {e}")
            self._llm_cache[name] = None
            return None

        food = {
            "name": result.get("name") or name,
            "portion_g": 100,
            "calories": result.get("calories"),
            "protein_g": result.get("protein_g"),
            "carbs_g": result.get("carbs_g"),
            "fat_g": result.get("fat_g"),
            "fiber_g": result.get("fiber_g"),
            "source": "OpenAI estimate (not measured)",
            "estimated": True,
            "confidence": result.get("confidence") or "low",
            "basis": result.get("basis"),
            "warning": "Estimated by a language model because this food is in "
                       "neither IFCT 2017 nor USDA. Treat as approximate.",
        }
        self._llm_cache[name] = food
        return food

    async def resolve(self, name: str, allow_estimate: bool = True) -> Optional[Dict[str, Any]]:
        """
        The single entry point callers should use.

        Tier 1  IFCT 2017  -- Indian foods, lab-measured (NIN Hyderabad)
        Tier 2  USDA FDC   -- prepared/non-Indian foods, lab-measured
        Tier 3  OpenAI     -- estimate, flagged as such

        Pass allow_estimate=False where an unmeasured number would be
        misleading (clinical screening, the cost optimiser).
        """
        found = self.lookup(name) or await self.lookup_usda(name)
        if found or not allow_estimate:
            return found
        return await self.lookup_llm(name)

    # ---------- scaling ----------

    @staticmethod
    def scale(food: Dict[str, Any], grams: float) -> Dict[str, Any]:
        """Scale per-100g values to an actual portion."""
        factor = (grams or 0) / 100.0
        out = {
            "name": food.get("name"),
            "group": food.get("group"),
            "portion_g": grams,
            "source": food.get("source"),
        }
        for field in ("calories", "protein_g", "carbs_g", "fat_g", "fiber_g"):
            value = food.get(field)
            out[field] = round(value * factor, 2) if value is not None else None

        aminos = food.get("amino_acids_g")
        if aminos:
            out["amino_acids_g"] = {k: round(v * factor, 3) for k, v in aminos.items()}

        # Carried through scaled so the micronutrient engine can sum a meal
        # without re-reading the database.
        micros = food.get("micronutrients")
        if micros:
            out["micronutrients"] = {k: round(v * factor, 3) for k, v in micros.items()}
        return out


nutrition_service = NutritionService()
