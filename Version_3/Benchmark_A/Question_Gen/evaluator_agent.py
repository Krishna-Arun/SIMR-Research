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
import os

from backend import LocalLLM
import prompts

# Evaluator model. Defaults to GPT-OSS 20B: Phi (mini and 14B) proved too weak for the
# 8-dimension rubric (self-contradiction, malformed JSON). Overridable via SIMR_EVAL_MODEL.
MODEL_KEY = os.environ.get("SIMR_EVAL_MODEL", "gpt-oss-20b")

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
  - stem_non_decisive: the qualitative vignette ALONE must NOT be enough to pick the answer.
    Actively test this: reading ONLY the stem (no numbers), could a competent clinician
    confidently choose the correct option? If YES -> FAIL (the narrative gives it away).
    At least 2-3 options must stay genuinely plausible until the solver retrieves the
    quantitative values. Also FAIL if the stem contains ANY numeric value (labs, vitals,
    doses) — all quantitative data must live behind the tools. A rich qualitative vignette
    is expected and good; a narrative that telegraphs the answer is not.
  - golden_set_necessary_and_sufficient: judge NECESSITY — removing any golden item leaves
    the answer undeterminable, and the vignette alone is not enough. "Sufficient" only means
    the golden values + vignette let a clinician reach the answer; it does NOT require the
    set to cover every possible contributing factor. DO NOT fail this dimension merely
    because more labs (BUN, bicarbonate, fluid status, etc.) *could* be added — a minimal
    decisive set is CORRECT and preferred. Fail only if a golden item is not truly needed,
    or if the set genuinely cannot determine the answer.
  - patient_specific: tied to THIS patient's real findings dated before time-zero.
  - requires_causal_reasoning: needs a >=2-step causal chain, not a single lookup.
  - no_answer_giveaway: the stem/options do not name the target outcome or state golden values.
  - mc_format_valid: 4-6 options, final option exactly "None of the above", correct_options
    are a subset of options.
  - no_time_zero_leakage: nothing at/after time-zero appears in stem, options, or golden set.
  - citation_present: BEST-EFFORT — set true if a citation is present OR absent; only set
    false if a citation is present AND obviously fabricated (e.g. an invented PMID). Do NOT
    fail this dimension because a real citation is imperfectly matched to the causal chain.
    Citations do not gate acceptance.

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
        # GPT-OSS is a reasoning model — give room so reasoning + JSON verdict is not
        # truncated (truncation was producing empty/unparseable verdicts).
        return self.llm.chat(messages, temperature=0.2, max_new_tokens=3500)


if __name__ == "__main__":
    agent = EvaluatorAgent()
    print(agent.evaluate(
        {"note": "stub context"},
        '{"question_text": "stub draft question"}'))
