"""
Optimizer agent — Mistral Small 3.1 (Benchmark C).

Role: given a paired context (two patients, their procedures, the observed
post-panel, and the true answer), author the stem, a causal chain that explains
WHY the observed changes match the answer patient's procedure (and NOT the other's),
and a reference answer. It does NOT choose the answer — that is data-derived.
"""
from __future__ import annotations

import json

from backend import LocalLLM
import prompts

MODEL_KEY = "mistral-small-3.1"

SYSTEM = f"""You are the OPTIMIZER in an intervention-attribution question-generation system.

{prompts.full_spec()}

YOUR RESTRICTIONS (Optimizer):
  - The pairing and the true answer are GIVEN (data-derived). Do NOT change the answer
    and do NOT reveal it (or any owner label) in the stem.
  - Return STRICT JSON only, no prose outside it, with keys:
    {{"stem": str,
      "causal_chain": [str, str, ...],   // >=2 steps: how each procedure would move the
                                         // shared labs, and why the observed panel matches
                                         // the answer patient and NOT the other
      "reference_answer": str,           // states A or B + the causal reason
      "pubmed_citations": [{{"pmid": str, "claim": str}}]  // optional; [] if none
    }}
  - Ground the discrimination in the CAUSAL EFFECTS of the two procedures, since the
    baselines are similar by construction."""

DRAFT_TEMPLATE = """CONTEXT (two patients, observed post-panel, GROUND-TRUTH answer, winner effects):
{context}

Author the stem, causal_chain, reference_answer (and optional citations) now."""

REFINE_TEMPLATE = """CONTEXT:
{context}

YOUR PREVIOUS DRAFT:
{previous}

EVALUATOR CRITIQUE (address every point):
{critique}

Rewrite. Return the full JSON again."""


class OptimizerAgent:
    def __init__(self, load_in_4bit: bool = True, llm=None):
        self.llm = llm or LocalLLM(MODEL_KEY, load_in_4bit=load_in_4bit)

    def draft(self, context: dict) -> str:
        return self.llm.chat([
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": DRAFT_TEMPLATE.format(context=json.dumps(context, indent=2))},
        ], temperature=0.7)

    def refine(self, context: dict, previous: str, critique: str) -> str:
        return self.llm.chat([
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": REFINE_TEMPLATE.format(
                context=json.dumps(context, indent=2), previous=previous, critique=critique)},
        ], temperature=0.5)


if __name__ == "__main__":
    print(OptimizerAgent().draft({"note": "stub"}))
