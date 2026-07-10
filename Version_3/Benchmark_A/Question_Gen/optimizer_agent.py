"""
Optimizer agent — Mistral Small 3.1.

Role in the question-generation loop: DRAFT and REFINE. Given a patient context
(and, on later rounds, the evaluator's critique), it writes/rewrites ONE clinical
question + answer key for Benchmark A. It is the generative half of the
evaluator-optimizer pair.

STUB LEVEL: the prompt scaffolding and I/O contract are real; the data backend
(patient context, supplementals) is not wired yet.
"""
from __future__ import annotations

import json

from backend import LocalLLM
import prompts
import schema

MODEL_KEY = "mistral-small-3.1"

SYSTEM = f"""You are the OPTIMIZER in a clinical-question-generation system.
Your job: author (and later refine) ONE Benchmark A question + full answer key.

{prompts.full_spec()}

{prompts.REQUEST_RUBRIC}

YOUR RESTRICTIONS (Optimizer):
  - Produce exactly ONE question per turn, as STRICT JSON, no prose outside it.
  - The JSON MUST contain these keys: {', '.join(schema.REQUIRED_KEYS)}.
  - Pick ONE question_type and use its correct TIME-ZERO; set time_zero + time_zero_policy.
  - Multiple-choice MUST be multi-select, 4-6 options, last option exactly
    "None of the above", and MUST contain NO buzzwords that leak the answer.
  - You generate the distractors yourself: plausible-for-a-clinician but wrong for
    THIS patient; explain them in distractor_rationale.
  - Define a golden_supplementals set that is NECESSARY (question unsolvable without
    the full set) and SUFFICIENT (answerable with it). Every golden item must be a
    real value in this patient's record strictly BEFORE time-zero.
  - causal_chain must be a >=2-step chain from the golden evidence to the answer.
  - For next_procedure and mortality_1y you MUST call PubMed and attach a verified
    citation (pmid + claim) in pubmed_citations.
  - Never reference any value/event/order/outcome dated at or after time-zero."""

DRAFT_TEMPLATE = """PATIENT CONTEXT:
{context}

Draft the question now."""

REFINE_TEMPLATE = """PATIENT CONTEXT:
{context}

YOUR PREVIOUS DRAFT:
{previous}

EVALUATOR CRITIQUE (address every point):
{critique}

Rewrite the question to fix all issues. Return the full JSON again."""


class OptimizerAgent:
    def __init__(self, load_in_4bit: bool = True, llm=None):
        # Mistral 24B — default to 4-bit so it fits a single GPU.
        # `llm` lets callers inject a shared/stub backend (orchestrator, dry-run).
        self.llm = llm or LocalLLM(MODEL_KEY, load_in_4bit=load_in_4bit)

    def draft(self, context: dict) -> str:
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": DRAFT_TEMPLATE.format(
                context=json.dumps(context, indent=2))},
        ]
        return self.llm.chat(messages, temperature=0.7)

    def refine(self, context: dict, previous: str, critique: str) -> str:
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": REFINE_TEMPLATE.format(
                context=json.dumps(context, indent=2),
                previous=previous, critique=critique)},
        ]
        return self.llm.chat(messages, temperature=0.5)


if __name__ == "__main__":
    # Smoke test with a placeholder context (no real patient data yet).
    agent = OptimizerAgent()
    print(agent.draft({"note": "stub context — no patient data wired yet"}))
