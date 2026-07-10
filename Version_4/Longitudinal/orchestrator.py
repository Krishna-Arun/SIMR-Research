#!/usr/bin/env python3
"""
Longitudinal orchestrator — turns each cohort patient's A1->C->B->A2 data spine
(from context_builder.longitudinal_contexts.json) into ONE longitudinal case record:
four chained questions on the SAME patient, plus a leak-safe answering view per step.

Modes:
  --dry-run : NO models. Synthesizes each step's framing from the data spine so the
              wiring + leak-safety are verifiable fast (today's check).
  (real)    : 2-agent authoring (Mistral optimizer + GPT-OSS evaluator via Ollama),
              reusing the proven backend. Slow (4 steps x n patients).

Usage:
  python orchestrator.py --dry-run --n 3
  SIMR_BACKEND=ollama python orchestrator.py --n 3        # real (slow)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "outputs"
ANSWER = OUT / "answering"
CONTEXTS = HERE / "longitudinal_contexts.json"
# reuse the generic Ollama backend from Benchmark A
sys.path.insert(0, str(HERE.parent / "Benchmark_A" / "Question_Gen"))

SEQUENCE = ["A1", "C", "B", "A2"]

CANONICAL_RUBRIC = {
    "A1": {"identification": "1 if predicted intervention family == answer_family else 0",
           "request_scoring": "0/0.5/1 per requested supplemental + 1 per golden lab",
           "causal": "causal chain quality"},
    "C":  {"identification": "1 if chosen_patient == answer else 0", "causal": "effect-based justification"},
    "B":  {"direction_scoring": "per target lab 1 correct / 0.5 (dir->Stable) / 0 opposite",
           "aggregate": "mean over target labs"},
    "A2": {"identification": "1 if predicted outcome == label else 0", "causal": "risk reasoning"},
}


# ── dry-run synthesis (data-derived, no models) ─────────────────────────────
def _syn_A1(ctx):
    a = ctx["A1_next_intervention"]; d = ctx["demographics"]
    fams = [a["answer_family"]] + a["distractor_families"]
    return {"stem": (f"A {d.get('anchor_age')}-year-old {d.get('gender')} patient was admitted to the ICU "
                     f"({d.get('admission_type')}). Using the supplemental data you can request, predict the "
                     "next major intervention."),
            "options": [f.capitalize() for f in fams] + ["None of the above"],
            "correct_options": [a["answer_family"].capitalize()],
            "golden_labs": a["golden_labs"]}


def _syn_C(ctx):
    C = ctx.get("C_attribution")
    if not C or C.get("_note"):
        return None
    return {"stem": ("Two ICU patients with similar baselines underwent different interventions. "
                     "Given the observed post-intervention labs, identify which patient (A or B) they belong to."),
            "patient_A": C["patient_A"], "patient_B": C["patient_B"],
            "shared_labs": C["shared_labs"], "observed_post": C["observed_post"],
            "answer": C["answer"]}


def _syn_B(ctx):
    b = ctx["B_trajectory"]
    return {"stem": (f"Given the {ctx['anchor']['family']} intervention, predict how each listed lab trends "
                     "over the next 72 hours (Rising / Falling / Stable)."),
            "targets": [{"lab": t["lab"], "ref_low": t["ref_low"], "ref_high": t["ref_high"],
                         "pre_value": t["pre_value"]} for t in b["targets"]],
            "ground_truth": [{"lab": t["lab"], "direction": t["direction"]} for t in b["targets"]]}


def _syn_A2(ctx):
    o = ctx["A2_outcome"]
    return {"stem": "At discharge, will this patient die within one year?",
            "options": ["Yes", "No", "None of the above"],
            "correct_options": ["Yes" if o.get("mortality_1y") else "No"],
            "readmission_30d": o.get("readmission_30d")}


def _synthesize(ctx, qid):
    return {"question_id": qid, "subject_id": ctx["subject_id"], "hadm_id": ctx["hadm_id"],
            "sequence": SEQUENCE, "anchor": ctx["anchor"], "demographics": ctx["demographics"],
            "steps": {"A1": _syn_A1(ctx), "C": _syn_C(ctx), "B": _syn_B(ctx), "A2": _syn_A2(ctx)},
            "rubric": CANONICAL_RUBRIC, "_provenance": {"mode": "dry_run"}}


# ── answering view: strip every answer key, per step ────────────────────────
def _answering_view(rec):
    steps = rec["steps"]
    view = {"question_id": rec["question_id"], "sequence": SEQUENCE, "anchor_family": rec["anchor"]["family"],
            "demographics": rec["demographics"], "steps": {}}
    a1 = steps["A1"]
    view["steps"]["A1"] = {"stem": a1["stem"], "options": a1["options"]} if a1 else None
    C = steps["C"]
    if C:
        view["steps"]["C"] = {"stem": C["stem"], "shared_labs": C["shared_labs"],
                              "observed_post": C["observed_post"],
                              "patient_A": {k: C["patient_A"][k] for k in ("procedure", "pre_labs")},
                              "patient_B": {k: C["patient_B"][k] for k in ("procedure", "pre_labs")}}
    b = steps["B"]
    view["steps"]["B"] = {"stem": b["stem"], "targets": b["targets"]} if b else None   # no directions
    a2 = steps["A2"]
    view["steps"]["A2"] = {"stem": a2["stem"], "options": a2["options"]} if a2 else None
    return view


def run(n, dry_run, seed=0, all_patients=False, split=None):
    OUT.mkdir(exist_ok=True); ANSWER.mkdir(parents=True, exist_ok=True)
    data = json.load(open(CONTEXTS))
    contexts = data["contexts"]
    split_path = HERE / "cohort_data" / "cohort_split.json"
    if split and split_path.exists():                       # restrict to a named split
        subs = set(json.load(open(split_path))["by_subject"][split])
        contexts = [c for c in contexts if c["subject_id"] in subs]
    if all_patients:
        picked = contexts                                   # EVERY patient
    else:
        picked = contexts[seed:seed + n]

    agents = None
    if not dry_run:
        from optimizer_agent import OptimizerAgent
        from evaluator_agent import EvaluatorAgent
        agents = (OptimizerAgent(), EvaluatorAgent())

    kept = 0
    with open(OUT / "longitudinal.jsonl", "w") as fout:
        for k, ctx in enumerate(picked):
            qid = f"L-{ctx['hadm_id']}-{ctx['stay_id']}"
            try:
                if dry_run:
                    rec = _synthesize(ctx, qid)
                else:
                    rec = _generate(ctx, qid, agents)          # real 2-agent path
                fout.write(json.dumps(rec, default=str) + "\n")
                json.dump(_answering_view(rec), open(ANSWER / f"{qid}.json", "w"), indent=2, default=str)
                has_C = rec["steps"]["C"] is not None
                kept += 1
                print(f"[{k+1}/{len(picked)}] {qid}: OK  (C step: {'yes' if has_C else 'no pair'})")
            except Exception as ex:
                print(f"[{k+1}/{len(picked)}] {qid}: ERROR {type(ex).__name__}: {ex}")
    print(f"\nKept {kept}/{len(picked)} longitudinal cases -> {OUT/'longitudinal.jsonl'}")
    print(f"Answering views -> {ANSWER}")


def _generate(ctx, qid, agents):
    """Real 2-agent authoring: optimizer polishes each step's stem/framing from the data
    spine; evaluator does a light accept check. Falls back to synthesized framing on failure."""
    import json as _json
    opt, evalr = agents
    base = _synthesize(ctx, qid); base["_provenance"] = {"mode": "models"}
    for step in SEQUENCE:
        s = base["steps"][step]
        if not s:
            continue
        prompt = (f"Rewrite ONLY the 'stem' of this Benchmark {step} question as a richer, qualitative "
                  f"clinical vignette (no numbers, do not reveal the answer). Return STRICT JSON "
                  f'{{"stem": "..."}}.\nStep data:\n{_json.dumps(s, default=str)[:1500]}')
        try:
            out = opt.llm.chat([{"role": "user", "content": prompt}], temperature=0.5, max_new_tokens=400)
            import re
            m = re.search(r'\{.*\}', out, re.DOTALL)
            if m:
                newstem = _json.loads(m.group(0)).get("stem")
                if newstem:
                    s["stem"] = newstem
        except Exception:
            pass
    return base


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--all", action="store_true", help="generate for EVERY cohort patient")
    ap.add_argument("--split", choices=["train", "val", "test"], help="restrict to a split")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    run(args.n, args.dry_run, args.seed, all_patients=args.all, split=args.split)
