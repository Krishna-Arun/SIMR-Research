"""Benchmark B optimizer — drafts/refines a post-procedure trajectory-prediction question + per-lab
causal justification. Runs inside the agentic loop (consults PubMed for guideline support).

The optimizer is shown the DATA-DERIVED true directions and must justify them causally; it must NOT
reveal the directions or the diagnosis in the question stem (anti-buzzword).
"""
from __future__ import annotations

import json

from qgen.agentic_loop import run_agentic
from qgen.schema import CANDIDATE_TEMPLATE


def render_context(context: dict) -> str:
    proc = context["procedure"]; demo = context.get("demographics", {})
    pre = context.get("pre_labs_summary", {})
    pre_lines = [f"  - {k}: latest {v.get('latest')} (range seen {v.get('min')}–{v.get('max')}, n={v.get('n')})"
                 for k, v in sorted(pre.items())]
    traj_lines = []
    for lab, t in sorted(context.get("trajectories", {}).items()):
        rng = (f"[{t['ref_lower']}–{t['ref_upper']}]" if t.get("ref_lower") is not None else "[no ref range]")
        traj_lines.append(f"  - {lab}: TRUE post-procedure direction = {t['direction']} "
                          f"(baseline {t['baseline']} -> post {t['post_rep']} {t['unit']}, ref {rng}, basis {t['basis']})")
    return (
        f"PROCEDURE (time-zero): {proc['label']}\n"
        f"PATIENT: age {demo.get('anchor_age','?')} {demo.get('gender','?')}; "
        f"comorbidities: {', '.join(context.get('comorbidities', {})) or 'none coded'}; "
        f"prior procedures: {', '.join(context.get('prior_procedures', [])[:8]) or 'none'}\n"
        f"PRE-PROCEDURE CORE LABS:\n" + ("\n".join(pre_lines) or "  (none)") +
        f"\nTRAJECTORY-ABLE CORE LABS (ground truth — justify these, do NOT reveal directions in the stem):\n" +
        ("\n".join(traj_lines) or "  (none)")
    )


DRAFT_INSTRUCTIONS = """Write ONE post-procedure TRAJECTORY-PREDICTION question for THIS patient and procedure.
The benchmark tests whether an AI can predict, from the PRE-procedure state + the procedure, how each
core lab moves afterward: Rising / Falling / Stable (Stable = stays within the lab's reference range).

Requirements:
- target_labs = the trajectory-able core labs listed above (use their exact names).
- For each, set expected_direction to the TRUE direction shown, and write a patient-specific
  causal_justification: procedure -> physiologic mechanism -> why THIS lab moves that way for THIS
  patient (reference the patient's actual baseline). Use PubMed to cite the procedure's effect on the lab.
- AVOID BUZZWORD BINGO: the question stem must NOT reveal any direction (Rising/Falling/Stable), must NOT
  name the diagnosis/answer, and must not pile up diagnostic buzzwords. The stem gives pre-state +
  procedure and asks the test-taker to predict; the directions + reasoning live ONLY in per_lab.
- USE THIS PATIENT (critical): the stem MUST use the patient's ACTUAL age and sex shown above — never a
  placeholder or a number copied from any example. Two different patients must NEVER receive the same stem.

BREVITY (critical — keep the JSON COMPLETE, never truncated): keep each causal_justification to ONE short
sentence and claims terse. EVERY target lab's expected_direction + causal_justification + citation MUST be
fully present and not cut off. Completeness beats verbosity.

Return {{"action":"final","result":<CANDIDATE>}} where CANDIDATE matches:
{template}"""


class OptimizerAgent:
    def __init__(self, llm, dispatcher, mcp_tools, budget: int):
        self.llm, self.dispatcher, self.mcp_tools, self.budget = llm, dispatcher, mcp_tools, budget

    def _run(self, context, messages):
        forbidden = [str(context["subject_id"]), str(context["hadm_id"])]
        return run_agentic(self.llm, self.dispatcher, self.mcp_tools, messages,
                           budget=self.budget, forbidden_ids=forbidden)

    def draft(self, context: dict, qtype: str = None) -> dict | None:
        prompt = render_context(context) + "\n\n" + DRAFT_INSTRUCTIONS.format(
            template=json.dumps(CANDIDATE_TEMPLATE, indent=2))
        return self._run(context, [{"role": "user", "content": prompt}])

    def refine(self, context: dict, qtype, prev: dict, feedback: str) -> dict | None:
        prompt = (render_context(context) + "\n\n" +
                  DRAFT_INSTRUCTIONS.format(template=json.dumps(CANDIDATE_TEMPLATE, indent=2)) +
                  f"\n\nYOUR PREVIOUS DRAFT:\n{json.dumps(prev, default=str)[:8000]}"
                  f"\n\nEVALUATOR FEEDBACK (address ALL):\n{feedback}")
        return self._run(context, [{"role": "user", "content": prompt}])
