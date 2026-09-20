"""
Deterministic clinical guardrails that sit over every recommendation.

Nothing in this module asks an LLM. Drug-food interactions and condition
limits are the part of a nutrition app where a plausible-sounding wrong
answer does real harm, so they are hard-coded rules with citations, applied
after generation. An LLM may phrase advice; it may not decide whether advice
is safe.

Escalation policy: anything matching a `block` rule is removed from the
output and replaced with a referral. Nothing here is a substitute for a
clinician, and the module never tells a user to change a medication.
"""
from typing import Any, Dict, List, Optional

SEVERITY_ORDER = {"block": 0, "warn": 1, "info": 2}


# ---------------------------------------------------------------------------
# Drug <-> nutrient interactions.
# `nutrient` keys match the micronutrient field names.
# ---------------------------------------------------------------------------

DRUG_INTERACTIONS = [
    {
        "drug": "warfarin",
        "aliases": ["warf", "coumadin", "acitrom", "acenocoumarol"],
        "nutrient": "vitamin_k_ug",
        "severity": "warn",
        "threshold_ug": 150,
        "message": (
            "This meal is high in vitamin K, which opposes warfarin and can move "
            "your INR. The goal is a *consistent* daily vitamin K intake, not "
            "avoidance -- sudden increases or drops are what destabilise INR."
        ),
        "action": "Keep green leafy vegetable intake steady day to day and tell "
                  "the clinician managing your INR about any lasting change.",
        "citation": "Vitamin K antagonist interaction; standard anticoagulation guidance.",
    },
    {
        "drug": "metformin",
        "aliases": ["glycomet", "glucophage"],
        "nutrient": "vitamin_b12_ug",
        "severity": "info",
        "message": (
            "Long-term metformin lowers vitamin B12 absorption. This app cannot "
            "assess B12 because IFCT 2017 does not measure it."
        ),
        "action": "Ask for a periodic serum B12 test. Do not self-supplement at "
                  "high doses without one.",
        "citation": "Metformin-associated B12 malabsorption; ADA standards of care.",
    },
    {
        "drug": "levothyroxine",
        "aliases": ["thyronorm", "eltroxin", "thyroxine"],
        "nutrient": "calcium_mg",
        "severity": "warn",
        "threshold_mg": 200,
        "message": (
            "Calcium and iron bind levothyroxine and block its absorption when "
            "taken close together."
        ),
        "action": "Take levothyroxine on an empty stomach and keep milk, curd, "
                  "calcium or iron supplements at least 4 hours away.",
        "citation": "Levothyroxine absorption interference with divalent cations.",
    },
    {
        "drug": "ace_inhibitor",
        "aliases": ["ramipril", "enalapril", "lisinopril", "telmisartan",
                    "losartan", "spironolactone"],
        "nutrient": "potassium_mg",
        "severity": "warn",
        "threshold_mg": 1500,
        "message": (
            "These medicines raise blood potassium. This meal is high in "
            "potassium, which adds to that effect."
        ),
        "action": "Avoid salt substitutes (they are potassium chloride) and have "
                  "potassium checked as your clinician directs.",
        "citation": "RAAS-inhibitor hyperkalaemia risk.",
    },
]


# ---------------------------------------------------------------------------
# Condition-based limits.
# ---------------------------------------------------------------------------

CONDITION_RULES = [
    {
        "condition": "ckd",
        "aliases": ["chronic kidney disease", "kidney disease", "renal failure",
                    "ckd stage 3", "ckd stage 4", "dialysis"],
        "limits": {"potassium_mg": 2000, "phosphorus_mg": 800, "sodium_mg": 2000},
        "severity": "block",
        "message": (
            "Chronic kidney disease requires potassium, phosphorus, sodium and "
            "protein targets set for your specific stage and labs. Generic meal "
            "plans are unsafe here."
        ),
        "action": "This plan needs review by a renal dietitian before you follow it.",
        "citation": "KDIGO nutrition guidance; targets are stage- and lab-specific.",
    },
    {
        "condition": "gout",
        "aliases": ["hyperuricemia", "high uric acid"],
        "high_purine_groups": ["Animal Meat", "Marine Fish", "Marine Shellfish",
                               "Marine Mollusks", "Fresh Water Fish and Shellfish"],
        "severity": "warn",
        "message": "Organ meat, red meat and shellfish are high in purines and "
                   "can precipitate a gout flare.",
        "action": "Favour dairy and plant protein, and keep fluid intake high.",
        "citation": "ACR gout management -- dietary purine reduction.",
    },
    {
        "condition": "pregnancy",
        "aliases": ["pregnant", "gestation"],
        "avoid_foods": ["papaya", "raw papaya", "shark", "swordfish", "king mackerel",
                        "tilefish", "raw egg", "unpasteurised", "alcohol"],
        "severity": "block",
        "message": (
            "Unripe papaya, high-mercury fish, raw egg and unpasteurised dairy "
            "are avoided in pregnancy."
        ),
        "action": "Remove these items. Antenatal nutrition should be confirmed "
                  "with your obstetrician or a registered dietitian.",
        "citation": "FSSAI/ICMR antenatal dietary guidance; mercury advisories.",
    },
    {
        "condition": "hypertension",
        "aliases": ["high blood pressure", "htn"],
        "limits": {"sodium_mg": 2000},
        "severity": "warn",
        "message": "Sodium in this plan exceeds the 2 g/day target used for "
                   "blood-pressure control.",
        "action": "Cut pickles, papad, namkeen and added salt before reducing "
                  "anything else.",
        "citation": "WHO sodium intake guideline (<2 g/day sodium).",
    },
]

# Anything in this space is clinical, not lifestyle -- the app must not answer.
ESCALATION_TRIGGERS = [
    "insulin dose", "change my medication", "stop taking", "how much insulin",
    "chemotherapy diet", "feeding tube", "eating disorder", "anorexia",
    "bulimia", "purge", "starve",
]


def _norm(text: str) -> str:
    return (text or "").strip().lower()


class ClinicalSafetyService:
    def screen(
        self,
        items: Optional[List[Dict[str, Any]]] = None,
        totals: Optional[Dict[str, float]] = None,
        conditions: Optional[List[str]] = None,
        medications: Optional[List[str]] = None,
        free_text: str = "",
    ) -> Dict[str, Any]:
        """
        Screen a meal/plan against the user's conditions and medications.

        Returns findings plus a `safe_to_show` flag. A `block` finding means
        the caller must withhold the recommendation and surface the referral.
        """
        items = items or []
        totals = totals or self._sum_micros(items)
        conditions = [_norm(c) for c in (conditions or []) if c]
        medications = [_norm(m) for m in (medications or []) if m]

        findings: List[Dict[str, Any]] = []
        findings += self._check_drugs(totals, medications)
        findings += self._check_conditions(items, totals, conditions)
        findings += self._check_escalation(free_text)

        findings.sort(key=lambda f: SEVERITY_ORDER.get(f["severity"], 9))
        blocked = [f for f in findings if f["severity"] == "block"]

        return {
            "findings": findings,
            "blocking": blocked,
            "safe_to_show": not blocked,
            "requires_dietitian": bool(blocked),
            "disclaimer": (
                "This is nutrition information, not medical advice. It does not "
                "replace your doctor or a registered dietitian, and no "
                "medication should be changed based on it."
            ),
        }

    # -- individual checks -------------------------------------------------

    def _check_drugs(self, totals, medications):
        out = []
        for rule in DRUG_INTERACTIONS:
            if not self._mentions(medications, [rule["drug"]] + rule["aliases"]):
                continue

            value = totals.get(rule["nutrient"])
            threshold = rule.get("threshold_ug") or rule.get("threshold_mg")

            # Rules without a threshold (B12 depletion) always apply; rules
            # with one only fire when the meal actually crosses it.
            if threshold is not None and (value is None or value < threshold):
                continue

            out.append({
                "type": "drug_nutrient_interaction",
                "severity": rule["severity"],
                "drug": rule["drug"],
                "nutrient": rule["nutrient"],
                "observed": value,
                "threshold": threshold,
                "message": rule["message"],
                "action": rule["action"],
                "citation": rule["citation"],
            })
        return out

    def _check_conditions(self, items, totals, conditions):
        out = []
        for rule in CONDITION_RULES:
            if not self._mentions(conditions, [rule["condition"]] + rule["aliases"]):
                continue

            exceeded = []
            for nutrient, cap in (rule.get("limits") or {}).items():
                value = totals.get(nutrient)
                if value is not None and value > cap:
                    exceeded.append({"nutrient": nutrient, "observed": round(value, 1),
                                     "limit": cap})

            flagged_foods = []
            for group in (rule.get("high_purine_groups") or []):
                flagged_foods += [i["name"] for i in items if i.get("group") == group]
            for term in (rule.get("avoid_foods") or []):
                flagged_foods += [i["name"] for i in items
                                  if term in _norm(i.get("name"))]

            # A `block` condition fires on the condition alone -- CKD needs a
            # dietitian whether or not this particular meal breaches a cap.
            if rule["severity"] != "block" and not exceeded and not flagged_foods:
                continue

            out.append({
                "type": "condition_guardrail",
                "severity": rule["severity"],
                "condition": rule["condition"],
                "exceeded": exceeded,
                "flagged_foods": sorted(set(flagged_foods)),
                "message": rule["message"],
                "action": rule["action"],
                "citation": rule["citation"],
            })
        return out

    def _check_escalation(self, free_text):
        text = _norm(free_text)
        hits = [t for t in ESCALATION_TRIGGERS if t in text]
        if not hits:
            return []
        return [{
            "type": "escalation",
            "severity": "block",
            "matched": hits,
            "message": "This is a clinical question, not a nutrition-planning one.",
            "action": "Speak to your treating clinician or a registered "
                      "dietitian. This app will not advise on it.",
            "citation": "Scope-of-practice boundary.",
        }]

    @staticmethod
    def _mentions(haystack, needles) -> bool:
        return any(n in item for item in haystack for n in needles)

    @staticmethod
    def _sum_micros(items) -> Dict[str, float]:
        totals: Dict[str, float] = {}
        for item in items:
            for key, value in (item.get("micronutrients") or {}).items():
                if value is not None:
                    totals[key] = totals.get(key, 0.0) + value
        return totals

    # -- clinician handoff -------------------------------------------------

    def clinical_summary(self, profile, assessment, screening) -> Dict[str, Any]:
        """One-page handoff a dietitian can actually act on."""
        gaps = assessment.get("gaps", [])
        absorption = assessment.get("absorption", {})
        return {
            "patient": {
                "age": profile.get("age"),
                "gender": profile.get("gender"),
                "life_stage": profile.get("life_stage"),
                "conditions": profile.get("medical_conditions") or [],
                "medications": profile.get("medications") or [],
            },
            "assessed_against": assessment.get("rda_source"),
            "period_days": assessment.get("period_days"),
            "deficits": [
                {"nutrient": g["nutrient"], "intake": g["intake"],
                 "rda": g["rda"], "unit": g["unit"],
                 "percent_rda": g["percent_rda"], "status": g["status"]}
                for g in gaps
            ],
            "iron_absorption": {
                "intake_mg": absorption.get("iron_intake_mg"),
                "modelled_absorbed_mg": absorption.get("iron_absorbed_mg"),
                "modifiers": absorption.get("modifiers"),
                "method": absorption.get("method"),
            },
            "unassessable": assessment.get("cannot_assess"),
            "safety_findings": screening.get("findings"),
            "generated_by": "NutriAI -- deterministic rules over IFCT 2017 / "
                            "ICMR-NIN RDA 2020. Not a diagnosis.",
        }


clinical_safety_service = ClinicalSafetyService()
