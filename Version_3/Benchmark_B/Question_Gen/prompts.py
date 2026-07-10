"""
Shared spec text for the Benchmark B question-generation agents.

Single source of truth so the Optimizer, Evaluator, and Scorer never drift.
Benchmark B = post-procedure lab-trajectory prediction.
"""
from __future__ import annotations

# Tunable: the "Stable" band as a fraction of each lab's reference-range width.
# |post - pre| <= STABLE_BAND_FRAC * (ref_high - ref_low)  =>  Stable.
STABLE_BAND_FRAC = 0.25
POST_WINDOW_HOURS = 72

BENCHMARK_SPEC = f"""\
BENCHMARK B — what it tests.
Given a patient's PRE-procedure clinical state (labs + microbiology, with values)
and the procedure(s) performed, an answering agent must PREDICT, with a CAUSAL
justification, how each of a set of "core" labs will trend over the {POST_WINDOW_HOURS} hours
AFTER the procedure: RISING, FALLING, or STABLE.

This is a STANDALONE prediction task (no data-request tools): the pre-procedure
labs/micro are given directly. The agent knows WHICH labs to predict and the times
they were re-sampled after the procedure, but NOT their post-procedure values.

You (Optimizer / Evaluator / Scorer) are BUILDING this benchmark and see the full
record INCLUDING the ground-truth directions. The answering agent never sees the
post-procedure values or the ground-truth directions."""

DIRECTION_RULE = f"""\
GROUND-TRUTH DIRECTION (computed from data, NOT authored). For each core lab with
reference range [ref_low, ref_high], width W = ref_high - ref_low:
  pre  = last measured value strictly BEFORE the procedure (time-zero).
  post = last measured value within (time-zero, time-zero + {POST_WINDOW_HOURS}h].
  delta = post - pre.
  STABLE  if |delta| <= {STABLE_BAND_FRAC} * W
  RISING  if delta >  {STABLE_BAND_FRAC} * W
  FALLING if delta < -{STABLE_BAND_FRAC} * W
The direction is measured RELATIVE TO THE REFERENCE-RANGE WIDTH so a change counts
only if it is clinically meaningful for that lab. A core lab must have >=2 pre and
>=2 post measurements and a valid reference range."""

OUTPUT_FORMAT = """\
ANSWERING-AGENT OUTPUT (for reference; the generator does not produce this): for
each target lab the agent returns
  {lab, direction: "Rising"|"Falling"|"Stable",
   confidence: {"Rising": p, "Falling": p, "Stable": p},   # sums to 1
   causal_justification: "..."}
Confidence is RECORDED for calibration analysis but does NOT affect the score."""

SCORING = """\
DIRECTION SCORING (per target lab; added onto the Benchmark A answer rubric):
  1.0  correct direction (predicted == actual).
  0.5  actual is Rising or Falling but the agent predicted Stable (hedge).
  0.0  opposite direction; OR actual is Stable but the agent predicted any direction.
The final answer is ALSO graded on the quality of the causal justification."""

LEAKAGE_RULES = f"""\
ANTI-LEAKAGE RULES (violation = reject):
  - The stem / inputs may include pre-procedure lab VALUES and the TIMES of post
    measurements, but NEVER the post-procedure VALUES or the ground-truth direction.
  - Only labs/micro dated strictly before time-zero may appear with values.
  - The post window is exactly {POST_WINDOW_HOURS}h after the procedure."""


def full_spec() -> str:
    return "\n\n".join([BENCHMARK_SPEC, DIRECTION_RULE, OUTPUT_FORMAT, SCORING, LEAKAGE_RULES])
