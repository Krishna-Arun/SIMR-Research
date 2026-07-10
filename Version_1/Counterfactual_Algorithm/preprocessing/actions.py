"""Grouped intervention vocabulary a_t.

Interventions are derived from two event sources:
  * procedures_icd  -> procedure action groups (revascularization, ventilation, dialysis, ...)
  * prescriptions   -> drug-class action groups (vasopressors, anticoagulants, antibiotics, ...)

Each clinical event maps to at most one *action group*. Non-intervention events (labs,
diagnoses, admit/discharge) map to NO_OP, which is action id 0. Keeping the action space small
and grouped keeps the demo tractable and the world model identifiable; the mapping is the single
place to enrich for the full cohort.

CAVEAT: these groupings are coarse research conveniences, not a clinical ontology. The CLMBR
path uses standardized OMOP/SNOMED codes directly; this module is for the from-scratch / GRU path
and for the RL action space.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

NO_OP = "no_op"

# ---- ICD procedure code -> action group ----------------------------------------------------
# ICD-9 procedure codes are 3-4 digit (no dot here); ICD-10-PCS are 7-char alphanumeric.
# Matched by prefix. Revascularization set mirrors the user's prior CAUSAL_BENCHMARK work.
PROCEDURE_PREFIXES = {
    # PCI / coronary revascularization (ICD-9: 0066, 3606/3607; ICD-10-PCS: 027*)
    "revascularization_pci": ["0066", "3606", "3607", "027"],
    # CABG (ICD-9: 361-369; ICD-10-PCS: 021*)
    "cabg": ["361", "362", "363", "364", "365", "366", "367", "368", "021"],
    # Mechanical ventilation (ICD-9: 9670-9672; ICD-10-PCS: 5A19)
    "mechanical_ventilation": ["9670", "9671", "9672", "5A19"],
    # Dialysis / RRT (ICD-9: 3995, 5498; ICD-10-PCS: 5A1D)
    "dialysis": ["3995", "5498", "5A1D"],
    # Cardiac catheterization / angiography (ICD-9: 3722, 8855, 8856)
    "cardiac_cath": ["3722", "8855", "8856", "B21"],
}

# ---- drug name keyword -> action group -----------------------------------------------------
# Matched case-insensitively as substrings of prescriptions.drug.
DRUG_KEYWORDS = {
    "vasopressor": ["norepinephrine", "epinephrine", "dopamine", "vasopressin",
                    "phenylephrine", "dobutamine"],
    "anticoagulant": ["heparin", "warfarin", "enoxaparin", "apixaban", "rivaroxaban",
                      "dabigatran", "fondaparinux"],
    "antiplatelet": ["aspirin", "clopidogrel", "ticagrelor", "prasugrel"],
    "diuretic": ["furosemide", "bumetanide", "spironolactone", "hydrochlorothiazide",
                 "torsemide"],
    "beta_blocker": ["metoprolol", "carvedilol", "atenolol", "bisoprolol", "labetalol"],
    "statin": ["atorvastatin", "simvastatin", "rosuvastatin", "pravastatin"],
    "antibiotic": ["vancomycin", "piperacillin", "ceftriaxone", "cefepime", "meropenem",
                   "ciprofloxacin", "levofloxacin", "metronidazole", "azithromycin"],
    "insulin": ["insulin"],
}


@dataclass
class ActionVocab:
    """Fixed action vocabulary; id 0 is reserved for NO_OP."""
    groups: list = field(default_factory=list)

    def __post_init__(self):
        if not self.groups:
            self.groups = [NO_OP] + list(PROCEDURE_PREFIXES) + list(DRUG_KEYWORDS)
        self.id_of = {g: i for i, g in enumerate(self.groups)}

    @property
    def n_actions(self) -> int:
        return len(self.groups)

    def to_id(self, group: str) -> int:
        return self.id_of.get(group, 0)

    def name(self, idx: int) -> str:
        return self.groups[idx] if 0 <= idx < len(self.groups) else NO_OP


def procedure_to_group(icd_code: str) -> Optional[str]:
    code = str(icd_code).replace(".", "").strip().upper()
    for group, prefixes in PROCEDURE_PREFIXES.items():
        for p in prefixes:
            if code.startswith(p.upper()):
                return group
    return None


def drug_to_group(drug_name: str) -> Optional[str]:
    name = str(drug_name).lower()
    for group, kws in DRUG_KEYWORDS.items():
        for kw in kws:
            if kw in name:
                return group
    return None


def event_to_action(event: dict) -> str:
    """Map a trajectory event to its action group (NO_OP if it is not an intervention)."""
    et = event.get("type")
    if et == "procedure":
        g = procedure_to_group(event.get("code", ""))
        return g if g else NO_OP
    if et == "drug":
        g = drug_to_group(event.get("code", ""))
        return g if g else NO_OP
    return NO_OP
