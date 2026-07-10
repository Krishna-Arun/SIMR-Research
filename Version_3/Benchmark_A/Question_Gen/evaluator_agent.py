"""
Evaluator agent — Phi-4-mini.

Role in the question-generation loop: CRITIQUE. Given a patient context and the
optimizer's draft question, it judges the draft on the acceptance dimensions and
either ACCEPTS it or returns a critique for the optimizer to address. It is the
critical half of the evaluator-optimizer pair.

STUB LEVEL: the prompt scaffolding and I/O contract are real; the automatic
(non-model) checks and data backend are not wired yet.
"""
from __future__ import annotations

import json

from backend import LocalLLM
import prompts

MODEL_KEY = "phi-4-mini"

# Acceptance dimensions the Evaluator judges. A question is accepted only if ALL
# pass. Citation is required only for next_procedure / mortality_1y (see PUBMED_RULE).
DIMENSIONS = [
    "answerable_only_via_supplementals",  # unanswerable from the stem alone
    "golden_set_necessary_and_sufficient",# unsolvable without full golden set; solvable with it
    "patient_specific",                   # grounded in THIS patient's real pre-time-zero findings
    "requires_causal_reasoning",          # >=2-step causal chain, not a lookup
    "no_buzzword_leakage",                # stem/options don't name dx/procedure/telltale terms
    "mc_format_valid",                    # multi-select, 4-6 options, ends with "None of the above"
    "no_time_zero_leakage",               # nothing at/after time-zero in stem/options/golden set
    "citation_present",                   # PubMed citation present when the type requires it
]

SYSTEM = f"""You are the EVALUATOR in a clinical-question-generation system.
You critique ONE draft question by the Optimizer and either ACCEPT it or send it
back with a concrete, actionable critique. You run at most 3 rounds; if a draft
still fails after the cap, it is discarded (do not lower your bar to force accept).

{prompts.full_spec()}

YOU JUDGE THESE DIMENSIONS (all must pass to accept):
  - answerable_only_via_supplementals: the stem alone cannot yield the answer.
  - golden_set_necessary_and_sufficient: removing any golden item makes it unsolvable;
    the full set makes it solvable.
  - patient_specific: tied to THIS patient's real findings dated before time-zero.
  - requires_causal_reasoning: needs a >=2-step causal chain, not a single lookup.
  - no_buzzword_leakage: no diagnosis/procedure name or telltale term in stem/options.
  - mc_format_valid: multi-select, 4-6 options, final option exactly "None of the above".
  - no_time_zero_leakage: nothing at/after time-zero appears in stem, options, or golden set.
  - citation_present: a verified PubMed citation exists IF the type requires one
    (required for next_procedure & mortality_1y; optional otherwise).

YOUR RESTRICTIONS (Evaluator):
  - You do NOT rewrite the question and you do NOT assign numeric quality scores.
  - Return STRICT JSON only:
    {{"scores": {{"<dimension>": true|false, ...}}, "accept": true|false, "critique": "..."}}
  - "accept" is true ONLY if every dimension is true.
  - When rejecting, the critique must name each failed dimension and say exactly
    what the Optimizer must change. No prose outside the JSON."""

EVAL_TEMPLATE = """PATIENT CONTEXT:
{context}

DRAFT QUESTION (JSON from the optimizer):
{draft}

Evaluate the draft now."""


class EvaluatorAgent:
    def __init__(self, llm=None):
        self.llm = llm or LocalLLM(MODEL_KEY)

    def evaluate(self, context: dict, draft: str) -> str:
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": EVAL_TEMPLATE.format(
                context=json.dumps(context, indent=2), draft=draft)},
        ]
        return self.llm.chat(messages, temperature=0.2)


if __name__ == "__main__":
    agent = EvaluatorAgent()
    print(agent.evaluate(
        {"note": "stub context"},
        '{"question_text": "stub draft question"}'))
