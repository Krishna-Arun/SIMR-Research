#!/usr/bin/env python3
"""
Version_4 chained-case generator — HARDENED, leak-safe, agentic-`a`.

From each cohort patient's A1/C/B/A2 data spine (longitudinal_contexts.json) build ONE chained
case (a -> b -> c -> d on the same patient) plus a leak-safe answering view, and — for `a` — a
pre-t0 SUPPLEMENTAL BUNDLE consumed by the gated MCP tool server (Benchmark_a/MCP_Server).

Hardening vs V3:
  a  open-ended (NO multiple-choice, NO golden-lab giveaway); agentic: the model must call
     Access_All_supplementals_no_values -> Request_a_supplemental/Request_values (justified) ->
     answer the next-intervention question with a patient-specific causal chain citing values.
  b  the model must SELECT which core labs to track and predict each direction + justification
     (scoring tightened downstream in score_chain.py).
  c  ambiguous real-patient pairs (already z-distance matched); requires the causal MECHANISM.
  d  1-year mortality on the BALANCED case set; graded on correctness + calibration + rationale.

Leak-safety: the answering view NEVER contains answer_family/golden_labs (a), ground-truth
directions (b), the C answer, or the mortality label (d).

Reads:  longitudinal_contexts.json, cohort_data/{balanced_cases.json,labs.parquet,
        d_labitems.parquet,microbiologyevents.parquet,procedures_icd.parquet,d_icd_procedures.parquet}
Writes: outputs_v4/chained.jsonl, outputs_v4/answering/<qid>.json,
        ../Benchmark_a/MCP_Server/supplementals/<qid>.json

Usage:  python generate_v4.py --n 10        # pilot
        python generate_v4.py --all         # full balanced set
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "outputs_v4"
ANSWER = OUT / "answering"
COH = HERE / "cohort_data"
CTX = HERE / "longitudinal_contexts.json"
BUNDLE_DIR = HERE.parent / "Benchmark_a" / "MCP_Server" / "supplementals"

SEQUENCE = ["a", "b", "c", "d"]

V4_RUBRIC = {
    "a": {"request_quality": "per requested item: 0 irrelevant / 0.5 generic-textbook / "
                             "1 patient-specific justification citing this patient's context; "
                             "+1 bonus if the item is in the (hidden) golden set",
          "answer": "0 wrong/irrelevant intervention; 0.5 correct intervention but generic "
                    "reasoning; 1 correct intervention with >=2-step patient-specific causal "
                    "chain citing retrieved lab VALUES (open-ended, agent-judged)"},
    "b": {"direction": "per selected lab: 1 correct direction / 0 incorrect (TIGHTENED: no "
                       "Stable-hedge partial credit); reported as mean and all-correct rate",
          "justification": "agent-judged causal reason per lab (0/0.5/1)"},
    "c": {"identification": "1 if chosen patient == answer else 0",
          "mechanism": "agent-judged causal mechanism (0/0.5/1); full credit needs BOTH"},
    "d": {"correctness": "1 if call == label else 0",
          "calibration": "Brier / ECE vs stated confidence (and token-logit probability)",
          "rationale": "agent-judged causal risk reasoning (0/0.5/1)"},
    "note": "Headline difficulty metric = fraction of cases at FULL causal credit (target <20%).",
}


def _dt(s):
    return pd.to_datetime(s, errors="coerce")


class BundleBuilder:
    """Assemble a patient's PRE-t0 supplemental bundle from the cohort parquet slices."""
    def __init__(self):
        self.labs = pd.read_parquet(COH / "labs.parquet")
        self.labs["charttime"] = _dt(self.labs["charttime"])
        self.lab_label = dict(pd.read_parquet(COH / "d_labitems.parquet")[["itemid", "label"]].values)
        try:
            self.micro = pd.read_parquet(COH / "microbiologyevents.parquet")
            self.micro["charttime"] = _dt(self.micro["charttime"].fillna(self.micro["chartdate"]))
        except Exception:
            self.micro = None
        try:
            self.proc = pd.read_parquet(COH / "procedures_icd.parquet")
            self.proc["chartdate"] = _dt(self.proc["chartdate"])
            self.proc_title = dict(pd.read_parquet(COH / "d_icd_procedures.parquet")
                                   [["icd_code", "long_title"]].values)
        except Exception:
            self.proc = None

    def build(self, subject_id, hadm_id, t0, dx_history):
        # Per the Benchmark-a spec, the agent may request only LABS + MICROBIOLOGY. dx_history /
        # prior_procedures are deliberately EXCLUDED — they'd leak the intervention (e.g. an
        # "acute kidney failure" dx trivially implies dialysis).
        t0 = _dt(t0)
        supp = {"labs": [], "microbiology": []}
        # labs with values (the gate call strips values server-side; requests return them)
        L = self.labs[(self.labs.hadm_id == hadm_id) & (self.labs.charttime < t0)]
        for r in L.itertuples():
            supp["labs"].append({
                "category": "labs",
                "item_name": self.lab_label.get(r.itemid, str(r.itemid)),
                "value": r.valuenum, "unit": getattr(r, "valueuom", None),
                "ref_low": getattr(r, "ref_range_lower", None),
                "ref_high": getattr(r, "ref_range_upper", None),
                "flag": getattr(r, "flag", None), "charttime": str(r.charttime)})
        if self.micro is not None:
            M = self.micro[(self.micro.hadm_id == hadm_id) & (self.micro.charttime < t0)]
            for r in M.itertuples():
                supp["microbiology"].append({
                    "category": "microbiology",
                    "test_name": getattr(r, "test_name", None),
                    "spec_type": getattr(r, "spec_type_desc", None),
                    "charttime": str(r.charttime)})
        return {k: v for k, v in supp.items() if v}


# ── step framing (leak-safe by construction) ────────────────────────────────
def _step_a(ctx):
    a = ctx["A1_next_intervention"]; d = ctx["demographics"]; anc = ctx["anchor"]
    stem = (f"A {d.get('anchor_age')}-year-old {d.get('gender')} patient was admitted to the ICU. "
            "Using ONLY the supplemental data you can request (labs and microbiology are available "
            "by name/date first; you must justify and request the values you need), determine the "
            "SINGLE most likely next major intervention this patient requires, and justify it with "
            "a patient-specific causal chain that cites the specific lab values you retrieved.")
    full = {"stem": stem, "question_type": "next_intervention_openended",
            "reference_answer": {"family": anc["family"], "procedure": anc.get("procedure")},
            "golden_labs": a.get("golden_labs", []),        # HIDDEN (judge only)
            "time_zero": a.get("time_zero")}
    return full


def _step_b(ctx):
    b = ctx["B_trajectory"]; anc = ctx["anchor"]
    targets = b.get("targets", [])
    stem = (f"Given that this patient underwent {anc['family']} ({anc.get('procedure')}), select "
            "the core labs whose 72-hour trajectory is most informative and predict each one's "
            "direction (Rising / Falling / Stable) with a causal justification and a confidence.")
    return {"stem": stem,
            "candidate_labs": [{"lab": t["lab"], "ref_low": t["ref_low"], "ref_high": t["ref_high"],
                                "pre_value": t["pre_value"]} for t in targets],
            "ground_truth": [{"lab": t["lab"], "direction": t["direction"]} for t in targets]}  # HIDDEN


def _step_c(ctx):
    C = ctx.get("C_attribution")
    if not C or C.get("_note") or "answer" not in C:
        return None
    stem = ("Two ICU patients (A and B) with similar baselines underwent DIFFERENT interventions. "
            "Given the observed post-intervention labs below, identify which patient they belong to "
            "and justify using the causal physiological effect of each intervention.")
    return {"stem": stem, "patient_A": C["patient_A"], "patient_B": C["patient_B"],
            "shared_labs": C["shared_labs"], "observed_post": C["observed_post"],
            "pre_state_distance": C.get("pre_state_distance"),
            "answer": C["answer"]}                            # HIDDEN


def _step_d(ctx):
    o = ctx["A2_outcome"]
    stem = ("At discharge, considering this patient's clinical course, predict whether they will "
            "die within one year. Give a Yes/No call, a calibrated confidence (0-1), and a causal "
            "risk rationale referencing the patient's specific abnormal values/trends.")
    return {"stem": stem, "options": ["Yes", "No"],
            "correct": "Yes" if o.get("mortality_1y") else "No",   # HIDDEN
            "readmission_30d": o.get("readmission_30d")}


def _answering_view(rec):
    s = rec["steps"]; v = {"question_id": rec["question_id"], "sequence": SEQUENCE,
                           "anchor_family_hidden": True, "demographics": rec["demographics"],
                           "steps": {}}
    a = s["a"]
    v["steps"]["a"] = {"stem": a["stem"], "question_type": a["question_type"],
                       "tool_use": "Call Access_All_supplementals_no_values(question_id) first, "
                       "then Request_a_supplemental / Request_values with justification.",
                       "question_id_for_tools": rec["question_id"]}
    b = s["b"]
    v["steps"]["b"] = {"stem": b["stem"], "candidate_labs": b["candidate_labs"]}   # no directions
    c = s["c"]
    if c:
        v["steps"]["c"] = {"stem": c["stem"], "shared_labs": c["shared_labs"],
                           "observed_post": c["observed_post"],
                           "patient_A": {k: c["patient_A"].get(k) for k in ("procedure", "pre_labs")},
                           "patient_B": {k: c["patient_B"].get(k) for k in ("procedure", "pre_labs")}}
    d = s["d"]
    v["steps"]["d"] = {"stem": d["stem"], "options": d["options"]}                  # no label
    return v


def run(n, all_cases):
    OUT.mkdir(exist_ok=True); ANSWER.mkdir(parents=True, exist_ok=True)
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    data = json.load(open(CTX)); contexts = {str(c["subject_id"]): c for c in data["contexts"]}
    bal = json.load(open(COH / "balanced_cases.json"))["subject_ids"]
    picked = [str(s) for s in bal]
    if not all_cases:
        picked = picked[:n]
    bb = BundleBuilder()
    kept = 0
    with open(OUT / "chained.jsonl", "w") as fout:
        for i, sid in enumerate(picked):
            ctx = contexts.get(sid)
            if not ctx:
                continue
            qid = f"L4-{ctx['hadm_id']}-{ctx['stay_id']}"
            rec = {"question_id": qid, "subject_id": ctx["subject_id"], "hadm_id": ctx["hadm_id"],
                   "stay_id": ctx["stay_id"], "sequence": SEQUENCE, "anchor": ctx["anchor"],
                   "demographics": ctx["demographics"],
                   "steps": {"a": _step_a(ctx), "b": _step_b(ctx),
                             "c": _step_c(ctx), "d": _step_d(ctx)},
                   "rubric": V4_RUBRIC}
            # supplemental bundle for agentic a
            bundle = {"question_id": qid, "time_zero": ctx["A1_next_intervention"].get("time_zero"),
                      "supplementals": bb.build(ctx["subject_id"], ctx["hadm_id"],
                                                ctx["A1_next_intervention"].get("time_zero"),
                                                ctx.get("dx_history"))}
            (BUNDLE_DIR / f"{qid}.json").write_text(json.dumps(bundle, default=str))
            fout.write(json.dumps(rec, default=str) + "\n")
            json.dump(_answering_view(rec), open(ANSWER / f"{qid}.json", "w"), indent=2, default=str)
            n_supp = sum(len(v) for v in bundle["supplementals"].values())
            kept += 1
            print(f"[{i+1}/{len(picked)}] {qid}: OK  (C:{'y' if rec['steps']['c'] else 'no-pair'} "
                  f"| bundle {n_supp} items | arm {ctx['anchor']['family']})")
    print(f"\nKept {kept}/{len(picked)} chained cases -> {OUT/'chained.jsonl'}")
    print(f"Answering views -> {ANSWER} | supplemental bundles -> {BUNDLE_DIR}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    run(args.n, args.all)
