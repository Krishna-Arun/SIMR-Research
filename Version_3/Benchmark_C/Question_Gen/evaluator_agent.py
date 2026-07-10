"""
Evaluator agent — Phi-4-mini (Benchmark C).

Critiques the Optimizer's framing + causal chain for an attribution question.
Accept or return a concrete critique (<=3 rounds, else discard).
"""
from __future__ import annotations

import json

from backend import LocalLLM
import prompts

MODEL_KEY = "phi-4-mini"

DIMENSIONS = [
    "different_procedures",        # the two procedures are genuinely different types
    "causal_discrimination",       # the chain distinguishes via procedure EFFECTS, not baselines
    "matches_observed",            # the reasoning matches the observed post-panel to the answer patient
    "reference_answer_matches",    # reference_answer states the correct patient (== answer)
    "no_answer_leakage",           # stem reveals neither the answer nor an owner label
]

SYSTEM = f"""You are the EVALUATOR in an intervention-attribution question-generation system.
You judge the Optimizer's draft and ACCEPT it or send it back with a concrete critique.
At most 3 rounds; if it still fails, it is discarded.

{prompts.full_spec()}

YOU JUDGE (all must pass to accept):
  - different_procedures: Patient A and B underwent different procedure types.
  - causal_discrimination: the causal_chain distinguishes the patients via the CAUSAL
    EFFECTS of their procedures, NOT via baseline values (baselines are similar).
  - matches_observed: the chain ties the observed post-panel changes to the answer patient.
  - reference_answer_matches: the reference_answer names the correct patient (the true answer).
  - no_answer_leakage: the stem discloses neither the answer nor a telltale owner label.

YOUR RESTRICTIONS (Evaluator):
  - You do NOT rewrite the draft and you do NOT change the answer.
  - Return STRICT JSON only:
    {{"scores": {{"<dimension>": true|false, ...}}, "accept": true|false, "critique": "..."}}
  - accept is true only if every dimension is true; else the critique must name each
    failed dimension and say exactly what to fix. No prose outside the JSON."""

EVAL_TEMPLATE = """CONTEXT (incl. ground-truth answer + winner effects):
{context}

OPTIMIZER DRAFT (JSON):
{draft}

Evaluate now."""


class EvaluatorAgent:
    def __init__(self, llm=None):
        self.llm = llm or LocalLLM(MODEL_KEY)

    def evaluate(self, context: dict, draft: str) -> str:
        return self.llm.chat([
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": EVAL_TEMPLATE.format(
                context=json.dumps(context, indent=2), draft=draft)},
        ], temperature=0.2)


if __name__ == "__main__":
    print(EvaluatorAgent().evaluate({"note": "stub"}, '{"stem": "stub"}'))
