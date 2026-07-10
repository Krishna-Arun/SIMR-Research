#!/usr/bin/env python3
"""
Orchestrator — the Benchmark B (lab-trajectory) question-generation loop.

For each sampled procedure-anchored context:
  1. build the context (context_builder) — targets + ground-truth directions from data,
  2. OPTIMIZER authors stem + causal chain + reference answer,
  3. EVALUATOR critiques; OPTIMIZER refines (<=3 rounds; else discard),
  4. SCORER assigns quality + builds the direction rubric,
  5. assemble the full record, validate (schema.py), persist to questions.jsonl,
     and write the answering-agent view (ground_truth stripped).

Modes:
  --dry-run : NO models. Synthesizes the authored fields straight from the
              ground-truth directions so the whole loop can run on a laptop.

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
    """What the answering agent sees: everything EXCEPT the ground truth."""
    return {k: v for k, v in record.items() if k != "ground_truth"}


def _synthesize_authored(context: dict) -> dict:
    gt = context["ground_truth"]
    proc = context["procedures"][0]["name"]
    chain = [f"{proc} affects {g['lab']} -> {g['direction']}" for g in gt[:6]]
    if len(chain) < 2:
        chain.append("Pre-procedure state modulates the magnitude of change.")
    ref = "; ".join(f"{g['lab']} {g['direction']}" for g in gt)
    return {"stem": ("Given the pre-procedure labs and the procedure performed, predict how each "
                     f"listed lab trends over the next {context['post_window_hours']} hours "
                     "(Rising / Falling / Stable) with causal justification."),
            "causal_chain": chain, "reference_answer": ref, "pubmed_citations": []}


def _assemble(context, authored, qid):
    rec = dict(context)
    rec.update(authored)
    rec["question_id"] = qid
    rec["question_type"] = schema.QUESTION_TYPE
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

    elig = list(cb.iter_eligible())
    elig.sort(key=lambda e: (e["hadm_id"], str(e["proc_time"]), e["proc_itemid"]))
    picked = ([elig[i] for i in range(0, len(elig), max(1, len(elig) // max(n, 1)))][:n]
              if elig else [])

    agents = None
    if not dry_run:
        from optimizer_agent import OptimizerAgent
        from evaluator_agent import EvaluatorAgent
        from scorer_agent import ScorerAgent
        agents = (OptimizerAgent(), EvaluatorAgent(), ScorerAgent())

    kept = 0
    with open(OUT_DIR / out_name, "w") as fout:
        for k, e in enumerate(picked):
            safe_t = str(e["proc_time"]).replace(" ", "_").replace(":", "")
            qid = f"B-lab_trajectory-{e['hadm_id']}-{e['proc_itemid']}-{safe_t}"
            try:
                ctx = cb.build_context(e["hadm_id"], e["proc_itemid"], e["proc_time"], e["proc_name"])
                if dry_run:
                    rec = _assemble(ctx, _synthesize_authored(ctx), qid)
                    rec["_provenance"] = {"mode": "dry_run"}
                else:
                    rec = _generate_with_models(ctx, qid, agents)
                if rec is None:
                    print(f"[{k+1}/{len(picked)}] {qid}: discarded")
                    continue
                schema.validate(rec)
                fout.write(json.dumps(rec, default=str) + "\n")
                with open(ANSWER_DIR / f"{qid}.json", "w") as af:
                    json.dump(_answering_view(rec), af, indent=2, default=str)
                kept += 1
                dirs = {}
                for g in ctx["ground_truth"]:
                    dirs[g["direction"]] = dirs.get(g["direction"], 0) + 1
                print(f"[{k+1}/{len(picked)}] {qid}: OK ({len(ctx['targets'])} labs, {dirs})")
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
