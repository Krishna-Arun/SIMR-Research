"""
Question-record contract for Benchmark B (lab-trajectory prediction) + validator.

The Optimizer authors the framing + causal narrative; the direction LABELS come
from the data (context_builder), not the model. validate() enforces structure and
the anti-leakage rule that target labs carry NO post-procedure values.
Pure stdlib.
"""
from __future__ import annotations

QUESTION_TYPE = "lab_trajectory"
DIRECTIONS = {"Rising", "Falling", "Stable"}

REQUIRED_KEYS = [
    "question_id", "question_type", "subject_id", "hadm_id",
    "time_zero", "post_window_hours",
    "procedures",          # [{name, time}]
    "stem",
    "inputs",              # {pre_labs:[...], microbiology:[...]}  (given to the agent)
    "targets",             # [{lab, ref_low, ref_high, pre_value, pre_time, post_times:[...]}] NO post values
    "ground_truth",        # [{lab, direction, pre_value, post_value, delta, ref_width}]  answer key (hidden)
    "causal_chain",
    "pubmed_citations",
    "reference_answer",
]

TARGET_KEYS = {"lab", "ref_low", "ref_high", "pre_value", "pre_time", "post_times"}
GT_KEYS = {"lab", "direction", "pre_value", "post_value", "delta", "ref_width"}
_LEAKY = {"post_value", "post_values", "direction", "delta"}   # must NOT appear in a target


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

    procs = record["procedures"]
    if not isinstance(procs, list) or not procs:
        raise SchemaError("procedures must be a non-empty list")

    targets = record["targets"]
    if not isinstance(targets, list) or len(targets) < 3:
        raise SchemaError("targets must be a list of >=3 core labs")
    for i, t in enumerate(targets):
        if not isinstance(t, dict) or not TARGET_KEYS <= set(t):
            raise SchemaError(f"targets[{i}] needs keys {sorted(TARGET_KEYS)}")
        leaked = _LEAKY & set(t)
        if leaked:
            raise SchemaError(f"targets[{i}] leaks post-procedure info: {sorted(leaked)}")
        if not isinstance(t["post_times"], list) or not t["post_times"]:
            raise SchemaError(f"targets[{i}].post_times must be a non-empty list")

    gt = record["ground_truth"]
    if not isinstance(gt, list) or len(gt) != len(targets):
        raise SchemaError("ground_truth must align 1:1 with targets")
    gt_labs, tgt_labs = {g.get("lab") for g in gt}, {t["lab"] for t in targets}
    if gt_labs != tgt_labs:
        raise SchemaError("ground_truth labs must match target labs")
    for i, g in enumerate(gt):
        if not GT_KEYS <= set(g):
            raise SchemaError(f"ground_truth[{i}] needs keys {sorted(GT_KEYS)}")
        if g["direction"] not in DIRECTIONS:
            raise SchemaError(f"ground_truth[{i}].direction '{g['direction']}' invalid")

    if not isinstance(record["causal_chain"], list) or len(record["causal_chain"]) < 2:
        raise SchemaError("causal_chain must be a list with >=2 steps")
    return record


EXAMPLE = {
    "question_id": "B-lab_trajectory-20000000-1",
    "question_type": "lab_trajectory",
    "subject_id": "10000000", "hadm_id": "20000000",
    "time_zero": "2150-01-02 08:00:00", "post_window_hours": 72,
    "procedures": [{"name": "Continuous renal replacement therapy", "time": "2150-01-02 08:00:00"}],
    "stem": ("Given the pre-procedure labs below and the procedure performed, predict how each "
             "listed lab will trend over the following 72 hours."),
    "inputs": {
        "pre_labs": [{"lab": "Potassium", "value": 6.3, "unit": "mEq/L", "charttime": "2150-01-02 06:00:00"}],
        "microbiology": [],
    },
    "targets": [
        {"lab": "Potassium", "ref_low": 3.5, "ref_high": 5.0, "pre_value": 6.3,
         "pre_time": "2150-01-02 06:00:00", "post_times": ["2150-01-02 14:00:00", "2150-01-03 06:00:00"]},
        {"lab": "Creatinine", "ref_low": 0.5, "ref_high": 1.2, "pre_value": 4.2,
         "pre_time": "2150-01-02 05:00:00", "post_times": ["2150-01-02 18:00:00", "2150-01-03 06:00:00"]},
        {"lab": "Bicarbonate", "ref_low": 22, "ref_high": 29, "pre_value": 16,
         "pre_time": "2150-01-02 05:00:00", "post_times": ["2150-01-02 18:00:00", "2150-01-03 06:00:00"]},
    ],
    "ground_truth": [
        {"lab": "Potassium", "direction": "Falling", "pre_value": 6.3, "post_value": 4.1,
         "delta": -2.2, "ref_width": 1.5},
        {"lab": "Creatinine", "direction": "Falling", "pre_value": 4.2, "post_value": 2.1,
         "delta": -2.1, "ref_width": 0.7},
        {"lab": "Bicarbonate", "direction": "Rising", "pre_value": 16, "post_value": 22,
         "delta": 6, "ref_width": 7},
    ],
    "causal_chain": [
        "CRRT clears potassium and uremic solutes -> potassium and creatinine fall",
        "Correcting acidosis via CRRT -> bicarbonate rises toward normal",
    ],
    "pubmed_citations": [],
    "reference_answer": "Potassium Falling, Creatinine Falling, Bicarbonate Rising.",
}


if __name__ == "__main__":
    validate(EXAMPLE)
    print("EXAMPLE is schema-valid.")
