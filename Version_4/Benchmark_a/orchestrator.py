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


# ── real generation loop (models, agentic retrieval) ────────────────────────
def _light_ctx(context, qid):
    """Compact context for the author — NO raw values (those are pulled via tools)."""
    return {"question_id": qid, "question_type": context["question_type"],
            "time_zero": context["time_zero"], "time_zero_policy": context["time_zero_policy"],
            "patient": context["patient"], "outcome": context["outcome"]}


def _author_task(context, qid):
    import prompts
    light = json.dumps(_light_ctx(context, qid), indent=2, default=str)
    cite_step = ("\nSTEP 3 (this type REQUIRES a citation): you MUST call search_articles and "
                 "use a pmid that appears IN THE RESULTS. NEVER invent or guess a PMID "
                 "(e.g. 12345678 is invalid). If a search returns nothing, try a broader query."
                 if context["question_type"] in schema.CITATION_REQUIRED_TYPES else "")
    content = f"""You are the OPTIMIZER authoring ONE Benchmark A question for question_id "{qid}".

{prompts.full_spec()}

{prompts.REQUEST_RUBRIC}

LIGHTWEIGHT CONTEXT (ground truth you must build an answer key for):
{light}

Do NOT expect the raw patient values in this prompt. Retrieve ONLY what you need using the
provided tools (question_id is "{qid}"):
STEP 1: call Access_All_supplementals_no_values to see the catalog (names/dates, no values).
STEP 2: call Request_values with items=[{{"category":"labs","item_name":"Creatinine"}}, ...]
        to pull ONLY the values you need to build the golden set + causal chain.
        Retrieve dx_history / prior_procedures too if useful for the clinical narrative.{cite_step}

WRITING THE STEM — a DETAILED but DELIBERATELY NON-DECISIVE clinical vignette:
- Write a RICH vignette (5-8 sentences): age, sex, chief complaint, relevant history &
  comorbidities, physical exam findings, and the hospital course up to time-zero.
- QUALITATIVE ONLY. State observations in words, NEVER numbers: no lab values, no vital-sign
  numbers, no doses, no thresholds. ALL quantitative data lives behind the tools (the solver
  retrieves it). E.g. write "appeared volume-overloaded and lethargic", NOT "creatinine 4.3"
  and NOT "potassium was elevated".
- CRITICAL — the vignette must be NON-DECISIVE: a competent clinician reading ONLY the stem
  must NOT be able to confidently pick the answer. At least 2-3 of the options must remain
  genuinely plausible from the narrative alone. The answer must hinge on the QUANTITATIVE
  values the solver retrieves through the tools — not on a phrase in the stem. Do NOT describe
  the picture so specifically that one option becomes obvious (e.g. avoid "oliguric CKD patient"
  when the answer is dialysis — that gives it away; instead describe a sicker, ambiguous patient
  in whom dialysis, fluid resuscitation, or other options are all on the table until you see
  the numbers).
- Do NOT name the answer/target procedure.

CHOOSING THE ANSWER + GOLDEN SET (most important — this is what makes the question hard):
- The outcome includes a field "lab_driven" listing the procedure(s) whose necessity is
  driven by specific labs, and which labs drive them (already filtered to labs that are
  ABNORMAL for THIS patient). Make correct_options EXACTLY ONE of those procedures (a
  single answer, e.g. "Dialysis" — never list two synonyms), and make the golden set
  EXACTLY the driving labs listed for it (retrieve their real values). Every golden item
  must be an ABNORMAL value for this patient — never include a normal-range lab.
- KEEP THE GOLDEN SET MINIMAL: include ONLY 2 labs — the driving labs listed for that
  procedure — and NO extras. Each must be individually necessary: removing either one
  should make the answer undeterminable. Do NOT add a broad panel of related labs.
- The stem must describe the presentation QUALITATIVELY only (e.g. "worsening respiratory
  distress", "tiring on non-invasive support") — NEVER write the numeric lab values or
  even name the golden labs in the stem.
- The test of NECESSITY: a clinician could NOT choose the right option from the vignette
  alone — only the golden values decide it. If your golden labs are renal (creatinine/K/
  eGFR), the answer must be the renally-driven procedure (e.g. dialysis/CRRT), NOT a
  generic one like an arterial line. Align the answer to what the labs cause.
- Do NOT pick a generic monitoring/line procedure as the answer unless a specific lab
  value makes it necessary.

WRITING THE OPTIONS:
- Provide 4 to 6 options TOTAL, the last EXACTLY "None of the above".
- Options are candidate interventions in neutral clinical language. Write plausible
  DISTRACTORS yourself — each distractor should be the procedure a clinician would choose
  under DIFFERENT lab findings, so the golden values are what discriminate. Do NOT copy
  the raw outcome list.
- correct_options must be worded IDENTICALLY to the matching entries in options.

When finished, STOP calling tools and reply with ONLY this JSON object (no tool call, no prose):
{{
  "stem": "...", "options": ["...", "...", "...", "None of the above"], "correct_options": ["..."],
  "golden_supplementals": [{{"category":"...","item_name":"...","patient_value":"...","why_required":"..."}}],
  "distractor_rationale": "...", "causal_chain": ["...", "..."],
  "pubmed_citations": [{{"pmid":"...","claim":"..."}}], "reference_answer": "..."
}}"""
    return [{"role": "user", "content": content}]


# tools the author may call: the 3 supplementals + a few PubMed (keep the surface small)
_AUTHOR_TOOLS = {"Access_All_supplementals_no_values", "Request_a_supplemental", "Request_values",
                 "search_articles", "get_abstract", "validate_pmid"}


def _generate_with_models(context, qid, agents, dispatcher, max_rounds=3):
    from agentic_loop import run_agentic_native
    import prompts
    opt, evalr = agents[0], agents[1]        # scorer role removed

    authored = run_agentic_native(opt.llm, dispatcher, dispatcher.tools,
                                  _author_task(context, qid), budget=10,
                                  allow=_AUTHOR_TOOLS, max_new_tokens=1500)
    if not authored:
        return None

    def _repair_correct(options, correct):
        """Map each correct label to the exact option string it best matches (models
        often paraphrase, e.g. 'Arterial Line' vs 'Arterial Line Placement')."""
        opts = options if isinstance(options, list) else []
        fixed = []
        for c in (correct or []):
            if c in opts:
                fixed.append(c); continue
            cl = str(c).lower()
            hit = next((o for o in opts if cl in o.lower() or o.lower() in cl), None)
            if hit:
                fixed.append(hit)
        # de-dup preserving order
        seen = set()
        return [x for x in fixed if not (x in seen or seen.add(x))]

    def assemble(a):
        options = a.get("options")
        rec = {"question_id": qid, "question_type": context["question_type"],
               "subject_id": str(context["patient"]["subject_id"]),
               "hadm_id": str(context["patient"]["hadm_id"]),
               "time_zero": context["time_zero"], "time_zero_policy": context["time_zero_policy"],
               **{k: a.get(k) for k in ("stem", "options", "golden_supplementals",
                                        "distractor_rationale", "causal_chain",
                                        "pubmed_citations", "reference_answer")}}
        rec["correct_options"] = _repair_correct(options, a.get("correct_options"))
        return rec

    import os as _os
    _dbg = _os.environ.get("SIMR_DEBUG")
    rec = assemble(authored)
    for _round in range(max_rounds):
        verdict = extract_json(evalr.evaluate(_light_ctx(context, qid), json.dumps(rec, default=str))) or {}
        if _dbg:
            print(f"  [round {_round}] correct={rec.get('correct_options')} "
                  f"golden={[g.get('item_name') for g in rec.get('golden_supplementals',[])]}")
            print(f"  [round {_round}] accept={verdict.get('accept')} scores={verdict.get('scores')}")
            print(f"  [round {_round}] critique={str(verdict.get('critique',''))[:300]}", flush=True)
        if verdict.get("accept"):
            rec["rubric"] = prompts.canonical_rubric()   # deterministic; no LLM scorer
            rec["evaluator_scores"] = verdict.get("scores")
            return rec
        # INCREMENTAL refine: keep the previous good draft, fix ONLY the failed dims.
        failed = [d for d, ok in (verdict.get("scores") or {}).items() if not ok]
        task = _author_task(context, qid)
        task.append({"role": "user", "content":
                     "Here is your PREVIOUS draft JSON (keep everything that already works):\n"
                     + json.dumps({k: rec.get(k) for k in (
                         "stem", "options", "correct_options", "golden_supplementals",
                         "distractor_rationale", "causal_chain", "pubmed_citations",
                         "reference_answer")}, default=str)[:2500]
                     + f"\n\nIt FAILED only these dimensions: {failed}\nCritique: "
                     + json.dumps(verdict.get("critique", ""))[:600]
                     + "\n\nFix ONLY those issues, leave everything else IDENTICAL, and output "
                       "ONLY the corrected final JSON object. You may retrieve more values if needed."})
        authored = run_agentic_native(opt.llm, dispatcher, dispatcher.tools, task, budget=6,
                                      allow=_AUTHOR_TOOLS, max_new_tokens=1500)
        if not authored:
            return None
        rec = assemble(authored)
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

    agents = dispatcher = supp = pub = None
    if not dry_run:
        from optimizer_agent import OptimizerAgent
        from evaluator_agent import EvaluatorAgent
        from mcp_client import pubmed_client, supplementals_client
        from tools import MultiDispatcher
        agents = (OptimizerAgent(), EvaluatorAgent())   # scorer role removed
        clients = []
        supp = supplementals_client(BUNDLE_DIR).start()   # serves the bundles we write below
        clients.append(supp)
        try:
            pub = pubmed_client().start()
            clients.append(pub)
        except Exception as e:
            print(f"WARN: PubMed server unavailable ({e}); citations skipped.")
        dispatcher = MultiDispatcher(clients)

    out_path = OUT_DIR / out_name
    kept = 0
    with open(out_path, "w") as fout:
        for k, e in enumerate(picked):
            qid = f"A-{e['question_type']}-{e['hadm_id']}"
            try:
                ctx = cb.build_context(e["hadm_id"], e["question_type"])
                # write the bundle FIRST so the supplementals server can serve it to the author
                with open(BUNDLE_DIR / f"{qid}.json", "w") as bf:
                    json.dump(to_supplemental_bundle(ctx, qid), bf, indent=2, default=str)
                if dry_run:
                    rec = _synthesize(ctx, qid)
                else:
                    rec = _generate_with_models(ctx, qid, agents, dispatcher)
                if rec is None:
                    print(f"[{k+1}/{len(picked)}] {qid}: discarded (not accepted)")
                    continue
                schema.validate(rec)
                fout.write(json.dumps(rec) + "\n")
                kept += 1
                print(f"[{k+1}/{len(picked)}] {qid}: OK ({ctx['question_type']})")
            except Exception as ex:
                print(f"[{k+1}/{len(picked)}] {qid}: ERROR {type(ex).__name__}: {ex}")
    for c in (supp, pub):
        if c:
            c.close()
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
