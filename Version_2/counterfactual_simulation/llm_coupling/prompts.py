"""prompts.py — time-zero-safe prompt construction + fixed answer grammar for the ablation.

All prompt text is built ONLY from information available at/before the question's time-zero: no future
labs, no post-outcome, no treatment-arm label leaked into attribution questions (build_cf_questions
controls exactly which fields are passed in). Answers use a fixed grammar so generations parse
deterministically in grade_cf.

Question families (all three benchmarks map here):
  A  intervention-attribution   -> which of two similar patients received {procedure}      (choice A/B)
  B  factual lab-direction       -> direction of {lab} under the treatment actually given    (Rising/Falling/Stable)
  C  counterfactual sign         -> effect on {lab or mortality} of adding/withholding {agent} (Higher/Lower/Unchanged)
"""
from __future__ import annotations

from typing import Optional

SYSTEM_PROMPT = (
    "You are a careful critical-care physician reasoning about an ICU patient. "
    "Think step by step, weigh the evidence, and be calibrated: express genuine uncertainty. "
    "Always finish with exactly one line in the format:\n"
    "ANSWER: <choice>. CONFIDENCE: <0.0-1.0>."
)

# canonical answer choices per family (grade_cf parses against these, case-insensitive)
CHOICES = {
    "A": ["A", "B"],
    "B": ["Rising", "Falling", "Stable"],
    "C": ["Higher", "Lower", "Unchanged"],
}


def _fmt_labs(labs: dict) -> str:
    if not labs:
        return "  (no recent labs available)"
    return ", ".join(f"{k} {v:g}" for k, v in labs.items() if v is not None)


def _fmt_meds(meds: list) -> str:
    return ", ".join(meds) if meds else "none active"


def case_block(baseline_labs: dict, active_meds: Optional[list] = None,
               demographics: Optional[str] = None, reveal_meds: bool = True) -> str:
    """Assemble the shared, time-zero-safe patient description. `reveal_meds=False` hides the active
    treatment (used for attribution questions where the treatment is the answer)."""
    lines = ["PATIENT (ICU, time zero):"]
    if demographics:
        lines.append(f"  Demographics: {demographics}")
    lines.append(f"  Recent labs: {_fmt_labs(baseline_labs)}")
    if reveal_meds:
        lines.append(f"  Active ICU treatments: {_fmt_meds(active_meds or [])}")
    return "\n".join(lines)


# ---------- question builders: return (question_text, family, choices) ----------

def question_A_attribution(procedure: str) -> "tuple[str, str, list]":
    q = (f"Two similar ICU patients are described (Patient A and Patient B). Exactly one of them "
         f"underwent {procedure}. Based on their trajectories, which patient received {procedure}?")
    return q, "A", CHOICES["A"]


def question_B_direction(lab: str, horizon_h: int = 48) -> "tuple[str, str, list]":
    q = (f"Under the treatment actually being administered, how will the patient's {lab} most likely "
         f"trend over the next {horizon_h} hours: Rising, Falling, or Stable?")
    return q, "B", CHOICES["B"]


def question_C_counterfactual(agent: str, target: str, action: str = "add",
                              is_outcome: bool = False) -> "tuple[str, str, list]":
    what = "the patient's mortality risk" if is_outcome else f"the patient's {target}"
    q = (f"Counterfactual: compared with the current management, if we were to {action} {agent}, "
         f"would {what} most likely be Higher, Lower, or Unchanged?")
    return q, "C", CHOICES["C"]


def build_prompt(case: str, question: str, evidence: Optional[str] = None) -> str:
    """Full user message. `evidence` (the serialized SIMULATOR block) is appended for Route-A arms only;
    the vanilla and Route-B (latent) prompts pass evidence=None so text is byte-identical to vanilla."""
    parts = [case, ""]
    if evidence:
        parts += [evidence, ""]
    parts += [f"QUESTION: {question}", "",
              "Reason briefly, then end with the required ANSWER/CONFIDENCE line."]
    return "\n".join(parts)
