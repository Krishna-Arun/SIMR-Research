#!/usr/bin/env python3
"""
Orchestrator — the Benchmark A question-generation loop.

For each sampled (patient, admission, question_type):
  1. build the context (context_builder),
  2. [procedure/mortality] gather a grounding PubMed citation via the agentic loop,
  3. OPTIMIZER drafts a question + answer key (strict JSON to schema.py),
  4. EVALUATOR critiques; on reject the OPTIMIZER refines (<=3 rounds; else discard),
  5. SCORER assigns quality + builds the grading rubric,
  6. validate the record, then persist it to questions.jsonl AND write the
     answering-agent supplemental bundle (pre-t0 only) for the MCP server.

Modes:
  --dry-run : NO models, NO network. Synthesizes a schema-valid record straight
              from the context (uses the true outcome to key the answer) so the
              whole pipeline — loop control, validation, persistence, bundle
              export — can be exercised on a laptop. Real runs omit this.

Usage:
  python orchestrator.py --dry-run --n 5
  python orchestrator.py --n 500 --types next_procedure mortality_1y   # GPU node
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import schema
from context_builder import ContextBuilder, to_supplemental_bundle

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "outputs"
BUNDLE_DIR = HERE.parent / "MCP_Server" / "supplementals"


# ── JSON extraction from model text (tolerant of prose / <think>) ────────────
def extract_json(text: str) -> dict | None:
    import re
    clean = re.sub(r"<think>.*?</think>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    best = None
    depth = start = 0
    for i, ch in enumerate(clean):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                frag = clean[start:i + 1]
                try:
                    best = json.loads(frag)      # keep the last top-level object
                except Exception:
                    pass
    return best


# ── dry-run: synthesize a valid record from the context (no models) ──────────
def _synthesize(context: dict, qid: str) -> dict:
    qtype = context["question_type"]
    pat = context["patient"]
    pools = context["pre_t0"]

    # golden set: take up to 3 real pre-t0 items that exist, across categories.
    golden = []
    for cat in ("labs", "microbiology", "fluids_output", "medications",
                "vitals_exam", "dx_history", "prior_procedures"):
        for r in pools.get(cat, [])[:1]:
            name = (r.get("item_name") or r.get("test_name") or r.get("drug")
                    or r.get("title") or "finding")
            golden.append({"category": cat, "item_name": str(name),
                           "patient_value": str(r.get("value") or r.get("interpretation")
                                                 or r.get("amount") or "present"),
                           "why_required": f"This patient's {name} constrains the answer."})
        if len(golden) >= 3:
            break
    if not golden:  # degenerate patient — skip
        raise ValueError("no pre-t0 items to form a golden set")

    correct = ["Outcome consistent with the requested supplementals"]
    options = [correct[0],
               "An alternative course not supported by the evidence",
               "A second unsupported alternative",
               "None of the above"]
    cites = ([{"pmid": "00000000", "claim": "Placeholder grounding claim (dry-run)."}]
             if qtype in schema.CITATION_REQUIRED_TYPES else [])
    return {
        "question_id": qid, "question_type": qtype,
        "subject_id": str(pat["subject_id"]), "hadm_id": str(pat["hadm_id"]),
        "time_zero": context["time_zero"], "time_zero_policy": context["time_zero_policy"],
        "stem": ("Using only supplemental data requestable before the decision point, "
                 "determine the course most consistent with this patient's findings."),
        "options": options, "correct_options": correct,
        "golden_supplementals": golden,
        "distractor_rationale": "Alternatives are clinically plausible but unsupported here.",
        "causal_chain": ["Requested findings establish the clinical state",
                         "That state implies the correct course"],
        "pubmed_citations": cites,
        "reference_answer": correct[0],
        "_provenance": {"mode": "dry_run", "outcome": context["outcome"]},
    }


# ── real generation loop (models) ───────────────────────────────────────────
def _generate_with_models(context, qid, agents, mcp, max_rounds=3):
    from agentic_loop import run_agentic
    from tools import ToolDispatcher
    opt, evalr, scorer = agents

    gen_ctx = dict(context)   # optimizer sees the full context incl. outcome (it writes the key)
    if context["question_type"] in schema.CITATION_REQUIRED_TYPES and mcp is not None:
        disp = ToolDispatcher(mcp)
        task = [{"role": "user", "content":
                 "Find ONE PubMed citation grounding the causal link for a "
                 f"{context['question_type']} decision. Return "
                 '{"action":"final","result":{"pmid":"...","claim":"..."}}.'}]
        cite = run_agentic(opt.llm, disp, mcp.tools, task, budget=4)
        gen_ctx["candidate_citation"] = cite

    draft = opt.draft(gen_ctx)
    for _ in range(max_rounds):
        verdict = extract_json(evalr.evaluate(gen_ctx, draft)) or {}
        if verdict.get("accept"):
            rec = extract_json(draft)
            if rec is None:
                return None
            rec["question_id"] = qid
            rubric = extract_json(scorer.score(json.dumps(rec), json.dumps(verdict)))
            if rubric:
                rec["scorer"] = rubric
            return rec
        draft = opt.refine(gen_ctx, draft, json.dumps(verdict.get("critique", verdict)))
    return None   # never accepted within the round cap -> discard


def run(n, qtypes, dry_run, seed=0, out_name="questions.jsonl"):
    OUT_DIR.mkdir(exist_ok=True)
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    cb = ContextBuilder()

    # deterministic sample of eligible tuples
    elig = list(cb.iter_eligible(qtypes))
    elig.sort(key=lambda e: (e["question_type"], e["hadm_id"]))
    idx = list(range(len(elig)))
    # simple seeded stride (no random import needed for reproducibility)
    picked = [elig[i] for i in idx[seed::max(1, len(elig) // max(n, 1))]][:n] if elig else []

    agents = mcp = None
    if not dry_run:
        from optimizer_agent import OptimizerAgent
        from evaluator_agent import EvaluatorAgent
        from scorer_agent import ScorerAgent
        from mcp_client import pubmed_client
        agents = (OptimizerAgent(), EvaluatorAgent(), ScorerAgent())
        try:
            mcp = pubmed_client().start()
        except Exception as e:
            print(f"WARN: PubMed server unavailable ({e}); citations skipped.")

    out_path = OUT_DIR / out_name
    kept = 0
    with open(out_path, "w") as fout:
        for k, e in enumerate(picked):
            qid = f"A-{e['question_type']}-{e['hadm_id']}"
            try:
                ctx = cb.build_context(e["hadm_id"], e["question_type"])
                if dry_run:
                    rec = _synthesize(ctx, qid)
                else:
                    rec = _generate_with_models(ctx, qid, agents, mcp)
                if rec is None:
                    print(f"[{k+1}/{len(picked)}] {qid}: discarded (not accepted)")
                    continue
                schema.validate(rec)
                fout.write(json.dumps(rec) + "\n")
                with open(BUNDLE_DIR / f"{qid}.json", "w") as bf:
                    json.dump(to_supplemental_bundle(ctx, qid), bf, indent=2, default=str)
                kept += 1
                print(f"[{k+1}/{len(picked)}] {qid}: OK ({ctx['question_type']})")
            except Exception as ex:
                print(f"[{k+1}/{len(picked)}] {qid}: ERROR {type(ex).__name__}: {ex}")
    if mcp:
        mcp.close()
    print(f"\nKept {kept}/{len(picked)} questions -> {out_path}")
    print(f"Supplemental bundles -> {BUNDLE_DIR}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--types", nargs="*", default=list(schema.QUESTION_TYPES))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    # map schema types (schema.QUESTION_TYPES) to context types
    run(args.n, tuple(args.types), args.dry_run, args.seed)
