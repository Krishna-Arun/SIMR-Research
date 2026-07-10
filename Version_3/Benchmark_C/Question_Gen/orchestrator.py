#!/usr/bin/env python3
"""
Orchestrator — the Benchmark C (intervention-attribution) question-generation loop.

For each sampled patient pair:
  1. build the context (context_builder) — pairing + observed panel + answer from data,
  2. OPTIMIZER authors stem + causal chain + reference answer,
  3. EVALUATOR critiques; OPTIMIZER refines (<=3 rounds; else discard),
  4. SCORER assigns quality + builds the 0/1 identification rubric,
  5. assemble + validate (schema.py), persist to questions.jsonl, and write the
     answering view (a strict whitelist — answer + causal reasoning stripped).

Modes:
  --dry-run : NO models. Synthesizes the authored fields from the winner effects.

Usage:
  python orchestrator.py --dry-run --n 5
  python orchestrator.py --n 500                      # GPU node
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import schema
from context_builder import ContextBuilder

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "outputs"
ANSWER_DIR = OUT_DIR / "answering"

# The ONLY fields an answering agent may see (everything else can leak the answer).
ANSWERING_WHITELIST = ("question_id", "question_type", "patient_A", "patient_B",
                       "shared_labs", "observed_post", "stem")


def extract_json(text: str) -> dict | None:
    clean = re.sub(r"<think>.*?</think>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    best, depth, start = None, 0, 0
    for i, ch in enumerate(clean):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    best = json.loads(clean[start:i + 1])
                except Exception:
                    pass
    return best


def _answering_view(record: dict) -> dict:
    return {k: record[k] for k in ANSWERING_WHITELIST if k in record}


def _synthesize_authored(context: dict) -> dict:
    ans = context["answer"]
    winner = context["patient_A" if ans == "A" else "patient_B"]
    proc = winner["procedure"]["name"]
    eff = context.get("_winner_effects", {})
    chain = [f"{proc} drives {l}: {v['pre']} -> {v['post']}" for l, v in list(eff.items())[:6]]
    if len(chain) < 2:
        chain.append("These effect directions distinguish the two procedures despite similar baselines.")
    return {"stem": ("Two patients with similar baselines each underwent a different procedure. "
                     "Given the observed post-procedure labs, identify which patient (A or B) they "
                     "belong to and justify using the procedures' causal effects."),
            "causal_chain": chain,
            "reference_answer": f"Patient {ans} ({proc} explains the observed changes).",
            "pubmed_citations": []}


def _assemble(context, authored, qid):
    rec = dict(context)
    rec.update(authored)
    rec["question_id"] = qid
    return rec


def _generate_with_models(context, qid, agents, max_rounds=3):
    opt, evalr, scorer = agents
    draft = opt.draft(context)
    for _ in range(max_rounds):
        verdict = extract_json(evalr.evaluate(context, draft)) or {}
        if verdict.get("accept"):
            authored = extract_json(draft)
            if not authored:
                return None
            rec = _assemble(context, authored, qid)
            rubric = extract_json(scorer.score(json.dumps(rec, default=str), json.dumps(verdict)))
            if rubric:
                rec["scorer"] = rubric
            return rec
        draft = opt.refine(context, draft, json.dumps(verdict.get("critique", verdict)))
    return None


def run(n, dry_run, seed=0, out_name="questions.jsonl"):
    OUT_DIR.mkdir(exist_ok=True)
    ANSWER_DIR.mkdir(parents=True, exist_ok=True)
    cb = ContextBuilder()

    pairs = list(cb.pair_units())
    picked = ([pairs[i] for i in range(0, len(pairs), max(1, len(pairs) // max(n, 1)))][:n]
              if pairs else [])

    agents = None
    if not dry_run:
        from optimizer_agent import OptimizerAgent
        from evaluator_agent import EvaluatorAgent
        from scorer_agent import ScorerAgent
        agents = (OptimizerAgent(), EvaluatorAgent(), ScorerAgent())

    kept = 0
    with open(OUT_DIR / out_name, "w") as fout:
        for k, (uA, uB, shared, dist) in enumerate(picked):
            answer = "A" if k % 2 == 0 else "B"          # balanced ground truth
            qid = f"C-attr-{uA['subject_id']}-{uB['subject_id']}-{k}"
            try:
                ctx = cb.build_context(uA, uB, shared, dist, answer)
                if dry_run:
                    rec = _assemble(ctx, _synthesize_authored(ctx), qid)
                    rec["_provenance"] = {"mode": "dry_run"}
                else:
                    rec = _generate_with_models(ctx, qid, agents)
                if rec is None:
                    print(f"[{k+1}/{len(picked)}] {qid}: discarded")
                    continue
                schema.validate(rec)
                view = _answering_view(rec)
                # hard leakage guard: the answer/effects must not be in the served view
                assert "answer" not in view and "_winner_effects" not in view and "causal_chain" not in view
                fout.write(json.dumps(rec, default=str) + "\n")
                with open(ANSWER_DIR / f"{qid}.json", "w") as af:
                    json.dump(view, af, indent=2, default=str)
                kept += 1
                print(f"[{k+1}/{len(picked)}] {qid}: OK (ans={answer}, {len(shared)} shared, dist={dist:.2f}, "
                      f"A={uA['proc_name']} vs B={uB['proc_name']})")
            except Exception as ex:
                print(f"[{k+1}/{len(picked)}] {qid}: ERROR {type(ex).__name__}: {ex}")
    print(f"\nKept {kept}/{len(picked)} -> {OUT_DIR / out_name}")
    print(f"Answering views -> {ANSWER_DIR}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    run(args.n, args.dry_run, args.seed)
