"""Benchmark C optimizer — drafts/refines a counterfactual intervention-identification question +
causal justification. Runs inside the agentic loop (consults PubMed). Shown the TRUE owner; must
justify it causally and must NOT reveal it in the stem (anti-leakage / anti-buzzword).
"""
from __future__ import annotations

import json

from qgen.agentic_loop import run_agentic
from qgen.schema import CANDIDATE_TEMPLATE


def _labs_line(d: dict) -> str:
    return ", ".join(f"{k}={v['latest']}" for k, v in sorted(d.items())) or "(none)"


def render_context(context: dict) -> str:
    A, B = context["patient_A"], context["patient_B"]
    post = ", ".join(f"{k}: " + "->".join(str(p["value"]) for p in v)
                     for k, v in sorted(context["shown_post_labs"].items())) or "(none)"
    return (
        f"PATIENT A — procedure: {A['procedure']}; age {A['demographics'].get('anchor_age','?')} "
        f"{A['demographics'].get('gender','?')}; comorbidities: {', '.join(A['comorbidities']) or 'none'}\n"
        f"  pre-procedure labs: {_labs_line(A['pre_labs'])}\n"
        f"PATIENT B — procedure: {B['procedure']}; age {B['demographics'].get('anchor_age','?')} "
        f"{B['demographics'].get('gender','?')}; comorbidities: {', '.join(B['comorbidities']) or 'none'}\n"
        f"  pre-procedure labs: {_labs_line(B['pre_labs'])}\n"
        f"OBSERVED POST-PROCEDURE LABS (from exactly ONE of the patients): {post}\n"
        f"GROUND TRUTH (do NOT reveal in the stem): the post-state belongs to patient "
        f"{context['shown_post_owner']}."
    )


DRAFT_INSTRUCTIONS = """Write ONE counterfactual intervention-identification question. The benchmark gives
both patients' PRE-procedure states + one patient's OBSERVED post-procedure labs, and asks which patient
(A or B) — i.e. which procedure — produced that post-state.

Requirements:
- predicted_owner = the correct patient ({owner}); write a causal_justification explaining why the shown
  post-state is consistent with that patient's procedure and NOT the other's (contrast the two procedures'
  physiologic effects on the labs that moved). Use PubMed to support each procedure's effect.
- distinguishing_features: for each procedure, the expected causal effect on the relevant labs.
- AVOID BUZZWORD BINGO / NO LEAKAGE: the question_text must NOT state or hint which patient is the answer,
  must not name the diagnosis, and must present A and B neutrally. The answer + reasoning live only in
  predicted_owner / causal_justification.
- USE THESE PATIENTS (critical): present A and B with their ACTUAL ages/sex shown above — never placeholders
  or numbers copied from an example. Each generated question must read as specific to this pair, not boilerplate.

BREVITY (critical — keep the JSON COMPLETE, never truncated): keep causal_justification and each
distinguishing_feature to ONE short sentence. predicted_owner + causal_justification + distinguishing_features
+ citations MUST be fully present and not cut off. Completeness beats verbosity.

Return {{"action":"final","result":<CANDIDATE>}} where CANDIDATE matches:
{template}"""


class OptimizerAgent:
    def __init__(self, llm, dispatcher, mcp_tools, budget: int):
        self.llm, self.dispatcher, self.mcp_tools, self.budget = llm, dispatcher, mcp_tools, budget

    def _run(self, context, messages):
        forbidden = [str(context["patient_A"]["demographics"]["hadm_id"]),
                     str(context["patient_B"]["demographics"]["hadm_id"]),
                     str(context["patient_A"]["demographics"]["subject_id"]),
                     str(context["patient_B"]["demographics"]["subject_id"])]
        return run_agentic(self.llm, self.dispatcher, self.mcp_tools, messages,
                           budget=self.budget, forbidden_ids=forbidden)

    def draft(self, context: dict, qtype=None) -> dict | None:
        prompt = render_context(context) + "\n\n" + DRAFT_INSTRUCTIONS.format(
            owner=context["shown_post_owner"], template=json.dumps(CANDIDATE_TEMPLATE, indent=2))
        return self._run(context, [{"role": "user", "content": prompt}])

    def refine(self, context: dict, qtype, prev: dict, feedback: str) -> dict | None:
        prompt = (render_context(context) + "\n\n" +
                  DRAFT_INSTRUCTIONS.format(owner=context["shown_post_owner"],
                                            template=json.dumps(CANDIDATE_TEMPLATE, indent=2)) +
                  f"\n\nYOUR PREVIOUS DRAFT:\n{json.dumps(prev, default=str)[:8000]}"
                  f"\n\nEVALUATOR FEEDBACK (address ALL):\n{feedback}")
        return self._run(context, [{"role": "user", "content": prompt}])
