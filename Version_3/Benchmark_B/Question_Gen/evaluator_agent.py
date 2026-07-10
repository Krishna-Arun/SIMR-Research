"""
Evaluator agent — GPT-OSS 20B (Benchmark B, lab-trajectory).

Critiques the Optimizer's framing + causal chain for a trajectory question; accept
or return a concrete critique (<=3 rounds, else discard). GPT-OSS replaced Phi
(too weak for the rubric). Model overridable via SIMR_EVAL_MODEL.
"""
from __future__ import annotations

import json
import os

from backend import LocalLLM
import prompts

MODEL_KEY = os.environ.get("SIMR_EVAL_MODEL", "gpt-oss-20b")

DIMENSIONS = [
    "causal_chain_sound", "one_link_per_target", "non_trivial",
    "no_post_value_leakage", "reference_answer_matches",
]

SYSTEM = f"""You are the EVALUATOR in a lab-trajectory question-generation system.
You judge the Optimizer's draft and ACCEPT it or send it back with a concrete
critique. At most 3 rounds; if it still fails, it is discarded.

{prompts.full_spec()}

YOU JUDGE (all must pass to accept):
  - causal_chain_sound: the mechanism plausibly explains each GIVEN direction.
  - one_link_per_target: every target lab is addressed in the causal_chain.
  - non_trivial: at least one target is Rising or Falling (not all Stable).
  - no_post_value_leakage: the stem/reference_answer reveal no post-procedure value.
  - reference_answer_matches: the reference_answer's directions equal the ground truth.

YOUR RESTRICTIONS (Evaluator):
  - You do NOT rewrite the draft and you do NOT change directions.
  - Return STRICT JSON only:
    {{"scores": {{"<dimension>": true|false, ...}}, "accept": true|false, "critique": "..."}}
  - accept is true only if every dimension is true; else the critique must name each
    failed dimension and say exactly what to fix. No prose outside the JSON."""

EVAL_TEMPLATE = """CONTEXT (incl. ground-truth directions):
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
                context=json.dumps(context, indent=2, default=str), draft=draft)},
        ], temperature=0.2, max_new_tokens=3500)


if __name__ == "__main__":
    print(EvaluatorAgent().evaluate({"note": "stub"}, '{"stem": "stub"}'))
