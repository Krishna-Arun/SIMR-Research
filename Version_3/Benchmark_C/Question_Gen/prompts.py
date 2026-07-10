"""
Shared spec text for the Benchmark C question-generation agents.

Benchmark C = intervention attribution / counterfactual discrimination.
Single source of truth spliced into every agent prompt.
"""
from __future__ import annotations

POST_WINDOW_HOURS = 72
# Pairing knobs (see context_builder): two units pair only if their procedures
# differ in TYPE, they share >= MIN_SHARED_LABS core labs, and their pre-state
# distance (mean |z| over shared labs) is <= MAX_PRESTATE_DISTANCE (similar baselines).
MIN_SHARED_LABS = 3
MAX_PRESTATE_DISTANCE = 0.75

BENCHMARK_SPEC = f"""\
BENCHMARK C — what it tests.
Two patients (A and B) each have a PRE-intervention clinical state (labs +
microbiology) and each underwent a DIFFERENT procedure. The two patients were
chosen to have SIMILAR pre-intervention states, so their baselines alone do NOT
reveal anything. You are then shown ONE observed POST-procedure lab panel (over
{POST_WINDOW_HOURS}h), which belongs to exactly ONE of the two patients.

The answering agent must identify WHICH patient (A or B) the observed post-panel
came from, and justify it using the CAUSAL EFFECT each patient's procedure would
have on that patient's physiology — not by matching baseline values (they are
similar by construction).

You (Optimizer / Evaluator / Scorer) are BUILDING this benchmark and see the full
record INCLUDING the true answer. The answering agent never sees the answer."""

TASK_IO = f"""\
INPUT the answering agent receives:
  - Patient A and Patient B, each with: prior procedures, the name(s) of the
    procedure performed, and pre-procedure lab values (within this admission).
  - ONE observed post-procedure lab panel (absolute values, over {POST_WINDOW_HOURS}h) from
    one of the two patients. Both pre-states are given so the agent can reason about
    the expected change (delta) each procedure would produce.
OUTPUT:
  - chosen_patient: "A" or "B"
  - confidence in [0,1]  (RECORDED for calibration, NOT scored)
  - causal_justification: why the observed changes match that patient's procedure."""

SCORING = """\
SCORING (added onto the Benchmark A answer rubric):
  1  correctly identifies the patient who had the procedure.
  0  incorrect.
Confidence is recorded and compared with the model's activation probability
externally; it does NOT change the 0/1 score. The causal justification is ALSO
graded for quality."""

PAIRING_RULE = f"""\
PAIRING (data-derived, NOT authored): the two patients are selected so that
  - their procedures are DIFFERENT types,
  - they share >= {MIN_SHARED_LABS} core labs (>=2 pre & >=2 post-{POST_WINDOW_HOURS}h each, valid ref range),
  - their pre-state distance (mean |z| over shared labs, z = (value - ref_mid)/(ref_width/2))
    is <= {MAX_PRESTATE_DISTANCE}  (similar baselines).
The observed post-panel is restricted to the SHARED core labs so the comparison is aligned."""

LEAKAGE_RULES = """\
ANTI-LEAKAGE RULES (violation = reject):
  - The stem/inputs must NOT reveal which patient the post-panel belongs to, nor
    the true answer, nor any patient identifier that trivially discloses it.
  - Only pre-procedure values may be shown per patient; the single post-panel is the
    only post-procedure evidence and must be presented WITHOUT its owner's label."""


def full_spec() -> str:
    return "\n\n".join([BENCHMARK_SPEC, TASK_IO, SCORING, PAIRING_RULE, LEAKAGE_RULES])
