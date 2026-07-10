"""
Optimizer agent — Mistral Small 3.1 (Benchmark B).

Role: given a procedure-anchored context (pre-procedure labs/micro, the procedure,
the target core labs AND their ground-truth post-procedure directions), author the
human-facing framing: the question stem, a causal chain explaining WHY each lab
trends as it does, and a reference answer. It does NOT invent the directions — those
are computed from data — it must EXPLAIN them causally.
"""
from __future__ import annotations

import json

from backend import LocalLLM
import prompts

MODEL_KEY = "mistral-small-3.1"

SYSTEM = f"""You are the OPTIMIZER in a lab-trajectory question-generation system.
You author the framing + causal explanation for ONE Benchmark B question.

{prompts.full_spec()}

YOUR RESTRICTIONS (Optimizer):
  - The target labs and their ground-truth directions are GIVEN (data-derived). Do
    NOT change them and do NOT restate post-procedure values in the stem.
  - Return STRICT JSON only, no prose outside it, with keys:
    {{"stem": str,
      "causal_chain": [str, str, ...],   // >=2 steps, procedure + pre-state -> each lab's trend
      "reference_answer": str,           // e.g. "Potassium Falling; Creatinine Falling; ..."
      "pubmed_citations": [{{"pmid": str, "claim": str}}]  // optional; [] if none
    }}
  - The causal_chain must mechanistically justify the GIVEN directions using the
    procedure and the pre-procedure findings (labs/micro). One link per target lab.
  - The stem gives the pre-procedure state + procedure + which labs to predict; it
    must NOT reveal any post-procedure value or the answer."""

DRAFT_TEMPLATE = """CONTEXT (procedure, pre-procedure inputs, targets, and GROUND-TRUTH directions):
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
    print(OptimizerAgent().draft({"note": "stub context"}))
