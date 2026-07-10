"""
Question-record contract for Benchmark A + a light validator.

The Optimizer emits a record shaped like EXAMPLE; the Evaluator judges it; the
Scorer finalizes it (adds quality_score + grading rubric). `validate()` enforces
the structural + policy rules that can be checked WITHOUT a model:
multi-select MC with a trailing "None of the above", a non-empty golden set, and
a PubMed citation when the question type requires one.

No third-party deps — pure stdlib so it runs anywhere.
"""
from __future__ import annotations

QUESTION_TYPES = {"next_procedure", "readmission_30d", "mortality_1y", "deterioration"}
CITATION_REQUIRED_TYPES = {"next_procedure", "mortality_1y"}
SUPPLEMENTAL_CATEGORIES = {
    "labs", "microbiology", "medications", "vitals_exam",
    "dx_history", "prior_procedures", "fluids_output",
}
NONE_OF_THE_ABOVE = "None of the above"

# The record the Optimizer must produce (Scorer later adds quality_score + rubric).
REQUIRED_KEYS = [
    "question_id", "question_type", "subject_id", "hadm_id",
    "time_zero", "time_zero_policy",
    "stem", "options", "correct_options",
    "golden_supplementals", "distractor_rationale",
    "causal_chain", "pubmed_citations", "reference_answer",
]

GOLDEN_ITEM_KEYS = {"category", "item_name", "patient_value", "why_required"}


class SchemaError(ValueError):
    """Raised by validate() with a human-readable reason."""


def validate(record: dict) -> dict:
    """Return the record if valid; raise SchemaError with a clear message otherwise."""
    if not isinstance(record, dict):
        raise SchemaError("record must be a dict")

    missing = [k for k in REQUIRED_KEYS if k not in record]
    if missing:
        raise SchemaError(f"missing keys: {', '.join(missing)}")

    qtype = record["question_type"]
    if qtype not in QUESTION_TYPES:
        raise SchemaError(f"question_type '{qtype}' not in {sorted(QUESTION_TYPES)}")

    # --- multiple-choice format ---
    options = record["options"]
    if not isinstance(options, list) or not (4 <= len(options) <= 6):
        raise SchemaError("options must be a list of 4-6 entries")
    if options[-1] != NONE_OF_THE_ABOVE:
        raise SchemaError(f'last option must be exactly "{NONE_OF_THE_ABOVE}"')
    if len(set(options)) != len(options):
        raise SchemaError("options must be unique")

    correct = record["correct_options"]
    if not isinstance(correct, list):
        raise SchemaError("correct_options must be a list (multi-select)")
    bad = [c for c in correct if c not in options]
    if bad:
        raise SchemaError(f"correct_options not among options: {bad}")

    # --- golden supplemental set (necessary/sufficient set; must be non-empty) ---
    golden = record["golden_supplementals"]
    if not isinstance(golden, list) or not golden:
        raise SchemaError("golden_supplementals must be a non-empty list")
    for i, item in enumerate(golden):
        if not isinstance(item, dict) or not GOLDEN_ITEM_KEYS <= set(item):
            raise SchemaError(
                f"golden_supplementals[{i}] needs keys {sorted(GOLDEN_ITEM_KEYS)}")
        cat = item["category"]
        if cat not in SUPPLEMENTAL_CATEGORIES:
            raise SchemaError(
                f"golden_supplementals[{i}].category '{cat}' invalid")

    # --- causal chain must be a real (>=2-step) chain ---
    chain = record["causal_chain"]
    if not isinstance(chain, list) or len(chain) < 2:
        raise SchemaError("causal_chain must be a list with >=2 steps")

    # --- PubMed citation required for some types ---
    cites = record["pubmed_citations"]
    if not isinstance(cites, list):
        raise SchemaError("pubmed_citations must be a list")
    if qtype in CITATION_REQUIRED_TYPES and len(cites) == 0:
        raise SchemaError(f"question_type '{qtype}' requires >=1 pubmed citation")
    for i, c in enumerate(cites):
        if not isinstance(c, dict) or "pmid" not in c or "claim" not in c:
            raise SchemaError(f"pubmed_citations[{i}] needs 'pmid' and 'claim'")

    return record


# A minimal, schema-valid example (values illustrative, not from a real patient).
EXAMPLE = {
    "question_id": "A-next_procedure-0001",
    "question_type": "next_procedure",
    "subject_id": "10000000",
    "hadm_id": "20000000",
    "time_zero": "2150-01-02 08:00:00",
    "time_zero_policy": "ICU intime",
    "stem": ("A patient is admitted to the ICU. Using only the supplemental data you "
             "can request, determine which intervention(s), if any, the care team "
             "will initiate next."),
    "options": [
        "Initiation of continuous renal replacement therapy",
        "Insertion of a central venous catheter",
        "Endotracheal intubation and mechanical ventilation",
        "Packed red blood cell transfusion",
        "None of the above",
    ],
    "correct_options": ["Initiation of continuous renal replacement therapy"],
    "golden_supplementals": [
        {"category": "labs", "item_name": "Creatinine",
         "patient_value": "4.2 mg/dL (ref 0.5-1.2)",
         "why_required": "Rising creatinine establishes acute kidney injury severity."},
        {"category": "labs", "item_name": "Potassium",
         "patient_value": "6.3 mEq/L (ref 3.5-5.0)",
         "why_required": "Refractory hyperkalemia is a dialysis indication."},
        {"category": "fluids_output", "item_name": "Urine output",
         "patient_value": "80 mL over 12h",
         "why_required": "Oliguria unresponsive to fluids supports RRT over conservative care."},
    ],
    "distractor_rationale": ("Central line / intubation / transfusion are plausible ICU "
                             "actions but unsupported by this patient's evidence."),
    "causal_chain": [
        "Creatinine rising + oliguria -> acute kidney injury with poor clearance",
        "Potassium 6.3 refractory to medical management -> emergent dialysis indication",
        "Therefore RRT is the next intervention",
    ],
    "pubmed_citations": [
        {"pmid": "00000000", "claim": "Refractory hyperkalemia with AKI is an indication for RRT."},
    ],
    "reference_answer": "Initiation of continuous renal replacement therapy",
}


if __name__ == "__main__":
    validate(EXAMPLE)
    print("EXAMPLE is schema-valid.")
