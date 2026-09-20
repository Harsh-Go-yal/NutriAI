"""
Build app/data/ifct2017.json from the IFCT 2017 compositions CSV.

Data source: Indian Food Composition Tables 2017, National Institute of
Nutrition (ICMR), Hyderabad. Government publication; reproduction permitted
with acknowledgement. Only the underlying data is used here -- none of the
AGPL-licensed helper packages are vendored.

Usage:  python scripts/build_ifct.py
"""
import csv
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "app", "data", "ifct_raw.csv")
DST = os.path.join(HERE, "..", "app", "data", "ifct2017.json")

KJ_PER_KCAL = 4.184

AMINO = ["his", "ile", "leu", "lys", "met", "cys", "phe", "thr", "trp",
         "val", "ala", "arg", "asp", "glu", "gly", "pro", "ser", "tyr"]

# IFCT stores every nutrient as grams per 100 g. Verified against known
# values before trusting it: spinach fe = 0.00295 g = 2.95 mg (published
# ~2.7 mg) and vitc = 0.03028 g = 30.3 mg (published ~28 mg).
G_TO_MG = 1_000
G_TO_UG = 1_000_000

# source column -> (output field, multiplier)
MICRONUTRIENTS = {
    "ca":     ("calcium_mg", G_TO_MG),
    "fe":     ("iron_mg", G_TO_MG),
    "zn":     ("zinc_mg", G_TO_MG),
    "mg":     ("magnesium_mg", G_TO_MG),
    "na":     ("sodium_mg", G_TO_MG),
    "k":      ("potassium_mg", G_TO_MG),
    "p":      ("phosphorus_mg", G_TO_MG),
    "cu":     ("copper_mg", G_TO_MG),
    "se":     ("selenium_ug", G_TO_UG),
    "vita":   ("vitamin_a_ug", G_TO_UG),
    "carot":  ("carotenes_ug", G_TO_UG),
    "vitc":   ("vitamin_c_mg", G_TO_MG),
    "vite":   ("vitamin_e_mg", G_TO_MG),
    "vitk":   ("vitamin_k_ug", G_TO_UG),
    "folsum": ("folate_ug", G_TO_UG),
    "thia":   ("thiamine_mg", G_TO_MG),
    "ribf":   ("riboflavin_mg", G_TO_MG),
    "nia":    ("niacin_mg", G_TO_MG),
    "vitb6c": ("vitamin_b6_mg", G_TO_MG),
}

# Amino acids the body cannot synthesise -- used for protein-quality scoring.
ESSENTIAL = ["his", "ile", "leu", "lys", "met", "phe", "thr", "trp", "val"]


def num(raw, ndigits=2):
    """IFCT leaves unmeasured cells blank; treat those as None, not zero."""
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return round(float(raw), ndigits)
    except ValueError:
        return None


def aliases(lang_field):
    """
    'A. Moricha guti; H. Ramdana; E. Pearl millet' -> ['Moricha guti', 'Ramdana', 'Pearl millet']

    Each entry is a two-or-three letter language prefix followed by the local
    name. Some entries share a prefix ('A., Kash. Baajra'), so strip every
    leading prefix group rather than just the first.
    """
    out = []
    for part in (lang_field or "").split(";"):
        part = part.strip().rstrip(".")
        if not part:
            continue
        name = re.sub(r"^(?:[A-Za-z]{1,4}\.\s*,?\s*)+", "", part).strip()
        if name and len(name) > 1:
            out.append(name)
    # de-duplicate, preserve order
    seen, uniq = set(), []
    for a in out:
        k = a.lower()
        if k not in seen:
            seen.add(k)
            uniq.append(a)
    return uniq


def main():
    with open(SRC, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    foods = []
    for r in rows:
        kj = num(r.get("enerc"))
        protein = num(r.get("protcnt"))

        amino_acids = {a: num(r.get(a), 3) for a in AMINO}
        amino_acids = {k: v for k, v in amino_acids.items() if v is not None}

        micros = {}
        for col, (field, mult) in MICRONUTRIENTS.items():
            grams = num(r.get(col), 12)
            if grams is not None:
                micros[field] = round(grams * mult, 3)

        foods.append({
            "code": r["code"],
            "name": r["name"],
            "group": r.get("grup") or None,
            "scientific_name": r.get("scie") or None,
            "aliases": aliases(r.get("lang")),
            "tags": (r.get("tags") or "").split(),
            # Per 100 g edible portion -- same shape as the legacy food table
            # so the diet planner keeps working unchanged.
            "portion_g": 100,
            "calories": round(kj / KJ_PER_KCAL) if kj is not None else None,
            "protein_g": protein,
            "carbs_g": num(r.get("choavldf")),
            "fat_g": num(r.get("fatce")),
            "fiber_g": num(r.get("fibtg")),
            "amino_acids_g": amino_acids or None,
            "micronutrients": micros or None,
        })

    payload = {
        "source": "Indian Food Composition Tables 2017 (IFCT 2017)",
        "publisher": "National Institute of Nutrition (ICMR), Hyderabad, India",
        "url": "https://www.nin.res.in/ebooks/IFCT2017.pdf",
        "basis": "per 100 g edible portion",
        "note": "Energy converted from kJ to kcal at 4.184 kJ/kcal. Source "
                "nutrient values are grams per 100 g; minerals and vitamins "
                "are converted to mg/ug as the field name states. null means "
                "the nutrient was not measured for that food.",
        "known_gaps": ["vitamin B12 is not measured in IFCT 2017"],
        "count": len(foods),
        "foods": foods,
    }

    with open(DST, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    with_micros = sum(1 for x in foods if x["micronutrients"])
    with_protein = sum(1 for x in foods if x["protein_g"] is not None)
    with_amino = sum(1 for x in foods if x["amino_acids_g"])
    print(f"wrote {DST}")
    print(f"  foods         : {len(foods)}")
    print(f"  with protein  : {with_protein}")
    print(f"  with aminos   : {with_amino}")
    print(f"  with micros   : {with_micros}")
    print(f"  groups        : {len({x['group'] for x in foods})}")


if __name__ == "__main__":
    main()
