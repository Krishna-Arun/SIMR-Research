"""
Question-record contract for Benchmark C (intervention attribution) + validator.

The pairing + answer are data-derived (context_builder); the Optimizer authors the
framing + causal justification. validate() enforces structure, that the two
procedures differ, that the observed panel covers only shared labs, and that the
true `answer` is present (it is stripped for the answering view by the orchestrator).
Pure stdlib.
"""
from __future__ import annotations

QUESTION_TYPE = "intervention_attribution"
ANSWERS = {"A", "B"}

REQUIRED_KEYS = [
    "question_id", "question_type",
    "patient_A", "patient_B",
    "shared_labs", "observed_post",
    "answer",                 # "A" | "B"  (ground truth; hidden from the agent)
    "pre_state_distance",     # provenance: how similar the baselines are
    "stem", "causal_chain", "pubmed_citations", "reference_answer",
]
PATIENT_KEYS = {"subject_id", "hadm_id", "procedure", "prior_procedures", "pre_labs"}


class SchemaError(ValueError):
    pass


def validate(record: dict) -> dict:
    if not isinstance(record, dict):
        raise SchemaError("record must be a dict")
    missing = [k for k in REQUIRED_KEYS if k not in record]
    if missing:
        raise SchemaError(f"missing keys: {', '.join(missing)}")
    if record["question_type"] != QUESTION_TYPE:
        raise SchemaError(f"question_type must be '{QUESTION_TYPE}'")
    if record["answer"] not in ANSWERS:
        raise SchemaError("answer must be 'A' or 'B'")

    for key in ("patient_A", "patient_B"):
        p = record[key]
        if not isinstance(p, dict) or not PATIENT_KEYS <= set(p):
            raise SchemaError(f"{key} needs keys {sorted(PATIENT_KEYS)}")
        proc = p["procedure"]
        if not isinstance(proc, dict) or "name" not in proc:
            raise SchemaError(f"{key}.procedure needs a name")

    if record["patient_A"]["procedure"]["name"] == record["patient_B"]["procedure"]["name"]:
        raise SchemaError("the two procedures must be different types")

    shared = record["shared_labs"]
    if not isinstance(shared, list) or len(shared) < 3:
        raise SchemaError("shared_labs must list >=3 labs")

    post = record["observed_post"]
    if not isinstance(post, dict) or "labs" not in post:
        raise SchemaError("observed_post must have a 'labs' list")
    post_labs = {r.get("lab") for r in post["labs"]}
    if not post_labs or not post_labs <= set(shared):
        raise SchemaError("observed_post labs must be a non-empty subset of shared_labs")

    if not isinstance(record["causal_chain"], list) or len(record["causal_chain"]) < 2:
        raise SchemaError("causal_chain must be a list with >=2 steps")
    return record


EXAMPLE = {
    "question_id": "C-intervention_attribution-0001",
    "question_type": "intervention_attribution",
    "patient_A": {
        "subject_id": "10000001", "hadm_id": "20000001",
        "procedure": {"name": "Continuous renal replacement therapy", "time": "2150-01-02 08:00:00"},
        "prior_procedures": ["Central venous catheter placement"],
        "pre_labs": [{"lab": "Creatinine", "value": 4.1, "unit": "mg/dL", "charttime": "2150-01-02 05:00:00"},
                     {"lab": "Potassium", "value": 6.1, "unit": "mEq/L", "charttime": "2150-01-02 05:00:00"}],
    },
    "patient_B": {
        "subject_id": "10000002", "hadm_id": "20000002",
        "procedure": {"name": "Endotracheal intubation and mechanical ventilation", "time": "2151-06-10 09:00:00"},
        "prior_procedures": [],
        "pre_labs": [{"lab": "Creatinine", "value": 3.9, "unit": "mg/dL", "charttime": "2151-06-10 06:00:00"},
                     {"lab": "Potassium", "value": 5.9, "unit": "mEq/L", "charttime": "2151-06-10 06:00:00"}],
    },
    "shared_labs": ["Creatinine", "Potassium", "Bicarbonate"],
    "observed_post": {"labs": [
        {"lab": "Creatinine", "value": 2.0, "unit": "mg/dL", "charttime": "+30h"},
        {"lab": "Potassium", "value": 4.0, "unit": "mEq/L", "charttime": "+30h"},
        {"lab": "Bicarbonate", "value": 23, "unit": "mEq/L", "charttime": "+30h"}]},
    "answer": "A",
    "pre_state_distance": 0.12,
    "stem": ("Two patients with similar baselines each underwent a different procedure. Given the "
             "observed post-procedure labs, identify which patient (A or B) they belong to and justify."),
    "causal_chain": [
        "CRRT clears creatinine and potassium and corrects acidosis",
        "The observed fall in creatinine/potassium and rise in bicarbonate matches CRRT, i.e. Patient A",
    ],
    "pubmed_citations": [],
    "reference_answer": "Patient A (CRRT explains the solute clearance and acid-base correction).",
}


if __name__ == "__main__":
    validate(EXAMPLE)
    print("EXAMPLE is schema-valid.")
