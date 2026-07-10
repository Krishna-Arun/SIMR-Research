"""
Shared spec text for the Benchmark A question-generation agents.

Single source of truth so the Optimizer, Evaluator, and Scorer never drift on
what a valid question is. Each constant is a plain string spliced into the
agents' system prompts. Edit the benchmark's rules HERE, not in three places.
"""
from __future__ import annotations

# --------------------------------------------------------------------------
# What the benchmark is (shared preamble for all three agents)
# --------------------------------------------------------------------------
BENCHMARK_SPEC = """\
BENCHMARK A — what it tests.
An answering agent is shown a multiple-choice clinical question about ONE real
MIMIC-IV patient, frozen at a moment called TIME-ZERO. The patient's raw clinical
detail is HIDDEN behind two tools. To answer, the agent must:
  1. discover what supplemental data exists (Access_All_supplementals_no_values),
  2. REQUEST each item it needs (Request_a_supplemental) WITH a patient-specific
     justification, and avoid requesting irrelevant items,
  3. answer the multiple-choice question and defend it with an explicit CAUSAL chain.
The whole point is to test causal, evidence-seeking reasoning — not recall.

You (Optimizer / Evaluator / Scorer) are BUILDING this benchmark. You see the FULL
patient record. The answering agent that will later be tested does NOT — it only
sees the stem and whatever it successfully requests through the tools."""

# --------------------------------------------------------------------------
# The four question targets + per-type TIME-ZERO (anti-leakage anchor)
# --------------------------------------------------------------------------
TARGET_DEFS = """\
QUESTION TYPES (each question is exactly one type):
  - next_procedure       : which major procedure(s) the patient will undergo next.
  - readmission_30d      : whether the patient is readmitted within 30 days of discharge.
  - mortality_1y         : whether the patient dies within one year.
  - deterioration        : whether the patient deteriorates in-hospital (ICU transfer /
                           escalation of care) during this admission.

TIME-ZERO (freeze point). Everything BEFORE time-zero is requestable supplemental
data; the correct answer is what happens AFTER. Never let the stem or options refer
to anything at or after time-zero.
  - next_procedure   -> ICU admission time (intime); fall back to hospital admit if no ICU.
  - deterioration    -> 24 hours after hospital admission.
  - readmission_30d  -> hospital discharge time (dischtime).
  - mortality_1y     -> hospital discharge time (dischtime)."""

# --------------------------------------------------------------------------
# Supplemental data categories the golden set may draw from
# --------------------------------------------------------------------------
SUPPLEMENTAL_CATEGORIES = """\
SUPPLEMENTAL CATEGORIES (any golden item must be one of these, and must be a real
value present in THIS patient's record strictly BEFORE time-zero):
  - labs              : lab values with reference ranges & abnormal flags (labevents).
  - microbiology      : cultures, organisms, antibiotic sensitivities (microbiologyevents).
  - medications       : ordered/administered drugs, dose, route (prescriptions).
  - vitals_exam       : vitals / anthropometrics (icu chartevents; outpatient omr).
                        NOTE: this demo has NO ED-triage vitals.
  - dx_history        : coded prior diagnoses / comorbidities (diagnoses_icd).
  - prior_procedures  : procedures performed before time-zero (procedures_icd).
  - fluids_output     : intake / urine & drain output (icu input/output events)."""

# --------------------------------------------------------------------------
# Golden set rule
# --------------------------------------------------------------------------
GOLDEN_SET_RULE = """\
GOLDEN SUPPLEMENTALS (the must-request set):
  - Define the MINIMAL set of supplemental items required to answer the question.
  - The set may span ANY of the supplemental categories above (golden supplementals,
    not just labs).
  - NECESSARY: without the full golden set the question must be UNSOLVABLE — no option
    can be justified from the stem alone or from a strict subset of the golden set.
  - SUFFICIENT: with the full golden set (plus general clinical reasoning) the correct
    option(s) must be determinable.
  - Each golden item records: category, item_name, patient_value, why_required."""

# --------------------------------------------------------------------------
# Multiple-choice formatting rules
# --------------------------------------------------------------------------
MC_RULES = """\
MULTIPLE-CHOICE FORMAT (strict):
  - MULTI-SELECT: zero or more options may be correct; the answer key is a set.
  - The FINAL option must always be exactly "None of the above".
  - NO BUZZWORDS: the stem and options must not name the diagnosis, the target
    procedure, or telltale terms that leak the answer. Describe findings neutrally;
    force the agent to reason, not pattern-match on a keyword.
  - DISTRACTORS: wrong options must be plausible for a clinician but incorrect for
    THIS patient given the evidence. No obviously-absurd options.
  - Provide 4-6 options total, including "None of the above"."""

# --------------------------------------------------------------------------
# PubMed grounding rule
# --------------------------------------------------------------------------
PUBMED_RULE = """\
PUBMED GROUNDING:
  - REQUIRED for next_procedure and mortality_1y: attach >=1 real, verified PubMed
    citation (PMID + claim) that grounds the causal chain. Use the PubMed tools.
  - OPTIONAL for readmission_30d and deterioration: include a citation if helpful,
    but absence is not a defect for these types."""

# --------------------------------------------------------------------------
# The per-request scoring rubric (used by the Scorer; applied to answering agents)
# --------------------------------------------------------------------------
REQUEST_RUBRIC = """\
REQUEST-SCORING RUBRIC (how each supplemental REQUEST an answering agent makes is
later scored — the Scorer encodes this into the answer key). Each request earns
TWO independent components that are ADDED together:

  (A) Justification quality (0 / 0.5 / 1):
    - 0.0 : nonsensical, irrelevant, or clinically inaccurate justification.
    - 0.5 : accurate but generic/textbook — not tied to THIS patient's values.
    - 1.0 : justification is patient-specific (cites this patient's value/finding)
            AND reasons about how multiple items combine.

  (B) Golden-item bonus (+1 PER ITEM):
    - +1.0 for EACH requested item that belongs to the golden set.
    - Non-golden (irrelevant) requests earn no bonus and typically score 0 on (A).

  Per-request score = justification_quality + golden_bonus
    -> a requested golden item can score up to 2.0 (1.0 justification + 1.0 golden).
    -> a requested non-golden item scores at most 1.0 (justification only).

The answer is also graded on multiple-choice correctness and on the quality of the
final CAUSAL chain."""

# --------------------------------------------------------------------------
# Hard anti-leakage rules (all agents enforce)
# --------------------------------------------------------------------------
LEAKAGE_RULES = """\
ANTI-LEAKAGE RULES (violation = reject):
  - The stem states only demographics + neutral presentation known AT time-zero.
  - No value, event, order, or outcome dated at/after time-zero may appear in the
    stem or options.
  - Golden items must all pre-date time-zero.
  - The stem must not reveal the answer via a buzzword (see MC_RULES)."""


def full_spec() -> str:
    """The complete shared spec block, in canonical order, for a system prompt."""
    return "\n\n".join([
        BENCHMARK_SPEC, TARGET_DEFS, SUPPLEMENTAL_CATEGORIES,
        GOLDEN_SET_RULE, MC_RULES, PUBMED_RULE, LEAKAGE_RULES,
    ])
