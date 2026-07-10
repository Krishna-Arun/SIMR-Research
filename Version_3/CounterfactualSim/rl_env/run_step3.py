#!/usr/bin/env python3
"""
Step 3 — score the three test-subject LLMs on the longitudinal benchmark (vanilla arm).

Each model answers all cases from the leak-safe answering views (NO simulate tool),
and every reply is graded by Longitudinal/score_longitudinal.score_case. We report the
per-step means (A1 / C / B / A2) and the aggregate longitudinal score per model — this
is the vanilla baseline the CounterfactualSim ablation is measured against.

Run:
  SIMR_BACKEND=ollama python rl_env/run_step3.py                 # all 3 models, all cases
  SIMR_BACKEND=ollama python rl_env/run_step3.py --n 10          # quick smoke
  SIMR_BACKEND=ollama python rl_env/run_step3.py --models qwen3-8b
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
CFSIM_DIR = HERE.parent.parent
V3_DIR = CFSIM_DIR.parent
LONG_DIR = V3_DIR / "Longitudinal"
QGEN_DIR = V3_DIR / "Benchmark_A" / "Question_Gen"
OUT = LONG_DIR / "outputs" / "step3_model_scores.json"

sys.path.insert(0, str(HERE.parent))     # ablation helpers
sys.path.insert(0, str(LONG_DIR))        # score_longitudinal
sys.path.insert(0, str(QGEN_DIR))        # backend

from ablation import load_records, load_answering, llm_answer   # noqa: E402
from score_longitudinal import score_case                        # noqa: E402

DEFAULT_MODELS = ["qwen3-8b", "llama-3.1-8b", "gemma-4-e4b"]
STEPS = ["A1", "C", "B", "A2"]


def score_model(model_key: str, records: dict) -> dict:
    from backend import LocalLLM
    llm = LocalLLM(model_key)
    per_step_sums = {s: 0.0 for s in STEPS}
    per_step_n = {s: 0 for s in STEPS}
    totals = []
    t0 = time.time()
    n = len(records)
    for i, (qid, record) in enumerate(records.items(), 1):
        view = load_answering(qid)
        if view is None:
            continue
        answers = llm_answer(llm, view, record, sim_ctx=None)   # vanilla: no sim
        sc = score_case(record, answers)
        totals.append(sc["total"])
        for s, v in sc["per_step"].items():
            per_step_sums[s] += v
            per_step_n[s] += 1
        if i % 10 == 0 or i == n:
            avg = sum(totals) / len(totals)
            print(f"  [{model_key}] {i}/{n}  running mean_total={avg:.4f}  "
                  f"({time.time()-t0:.0f}s)", flush=True)
    per_step = {s: (per_step_sums[s] / per_step_n[s] if per_step_n[s] else None) for s in STEPS}
    return {
        "model": model_key,
        "n_cases": len(totals),
        "per_step_mean": {s: (round(v, 4) if v is not None else None) for s, v in per_step.items()},
        "per_step_n": per_step_n,
        "mean_total": round(sum(totals) / len(totals), 4) if totals else 0.0,
        "seconds": round(time.time() - t0, 1),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=None, help="limit number of cases")
    ap.add_argument("--models", nargs="*", default=DEFAULT_MODELS)
    args = ap.parse_args()

    records = load_records()
    if args.n is not None:
        records = dict(list(records.items())[:args.n])
    print(f"Step 3 — scoring {len(args.models)} model(s) on {len(records)} case(s)\n")

    results = []
    for m in args.models:
        print(f"== model: {m} ==")
        try:
            results.append(score_model(m, records))
        except Exception as e:
            print(f"  [error] {m} failed: {type(e).__name__}: {e}")
            results.append({"model": m, "error": f"{type(e).__name__}: {e}"})

    OUT.write_text(json.dumps({"benchmark": "longitudinal", "arm": "vanilla",
                               "results": results}, indent=2))
    print(f"\n=== Step 3: vanilla longitudinal scores  (saved -> {OUT}) ===")
    hdr = f"{'model':<16}{'total':>8}{'A1':>8}{'C':>8}{'B':>8}{'A2':>8}"
    print(hdr); print("-" * len(hdr))
    for r in results:
        if "error" in r:
            print(f"{r['model']:<16}   ERROR: {r['error']}")
            continue
        ps = r["per_step_mean"]
        def f(x): return f"{x:>8.3f}" if isinstance(x, (int, float)) else f"{'-':>8}"
        print(f"{r['model']:<16}{r['mean_total']:>8.3f}{f(ps['A1'])}{f(ps['C'])}{f(ps['B'])}{f(ps['A2'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
