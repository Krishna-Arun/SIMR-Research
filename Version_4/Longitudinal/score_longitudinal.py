#!/usr/bin/env python3
"""
Longitudinal scorer — grades an agent's answers to one longitudinal case against the
answer keys, per step, and aggregates. This IS the RL reward function for GRPO.

An `answers` dict looks like:
  {"A1": ["Dialysis"],                       # chosen option(s)
   "C":  "A",                                 # chosen patient
   "B":  {"Creatinine": "Falling", ...},      # per-target direction
   "A2": ["No"]}                              # chosen option(s)

Returns {"per_step": {...}, "total": float in [0,1]} — total = mean over answered steps.
"""
from __future__ import annotations


def _mc_score(chosen, correct):
    cs, co = set(chosen or []), set(correct or [])
    if not co:
        return 0.0
    return 1.0 if cs == co else (0.5 if cs & co else 0.0)


def _direction_score(pred_dir, true_dir):
    if pred_dir == true_dir:
        return 1.0
    if true_dir in ("Rising", "Falling") and pred_dir == "Stable":
        return 0.5
    return 0.0                                  # opposite, or true Stable but predicted a direction


def score_case(record: dict, answers: dict) -> dict:
    steps = record.get("steps", {})
    per = {}

    a1 = steps.get("A1")
    if a1:
        per["A1"] = _mc_score(answers.get("A1"), a1.get("correct_options"))

    C = steps.get("C")
    if C:
        per["C"] = 1.0 if str(answers.get("C", "")).strip().upper() == str(C.get("answer", "")).upper() else 0.0

    b = steps.get("B")
    if b and b.get("ground_truth"):
        truth = {g["lab"]: g["direction"] for g in b["ground_truth"]}
        pred = answers.get("B", {}) or {}
        if truth:
            per["B"] = sum(_direction_score(pred.get(l), d) for l, d in truth.items()) / len(truth)

    a2 = steps.get("A2")
    if a2:
        per["A2"] = _mc_score(answers.get("A2"), a2.get("correct_options"))

    total = sum(per.values()) / len(per) if per else 0.0
    return {"per_step": per, "total": round(total, 4)}


if __name__ == "__main__":
    # self-test with a synthesized record + perfect answers
    rec = {"steps": {
        "A1": {"correct_options": ["Dialysis"]},
        "C": {"answer": "A"},
        "B": {"ground_truth": [{"lab": "Creatinine", "direction": "Falling"},
                               {"lab": "Potassium", "direction": "Stable"}]},
        "A2": {"correct_options": ["No"]}}}
    perfect = {"A1": ["Dialysis"], "C": "A",
               "B": {"Creatinine": "Falling", "Potassium": "Stable"}, "A2": ["No"]}
    print("perfect:", score_case(rec, perfect))
    print("mixed:", score_case(rec, {"A1": ["Intubation"], "C": "A",
                                     "B": {"Creatinine": "Stable", "Potassium": "Rising"}, "A2": ["No"]}))
