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
MIMIC-IV patient, frozen at a moment called TIME-ZERO. The stem reads like a real
clinical VIGNETTE — a short patient introduction (age, sex, chief complaint,
relevant history/comorbidities, and the hospital course up to time-zero, described
qualitatively). What is HELD BACK are the DECISIVE data — the specific golden lab /
microbiology VALUES needed to choose the answer — and the answer itself. To answer,
the agent must:
  1. discover what supplemental data exists (Access_All_supplementals_no_values),
  2. REQUEST each decisive item it needs (Request_a_supplemental / Request_values)
     WITH a patient-specific justification, and avoid requesting irrelevant items,
  3. answer the multiple-choice question and defend it with an explicit CAUSAL chain.
The vignette gives the clinical STORY; the decisive numbers stay behind the tools.
This tests causal, evidence-seeking reasoning that is DETAILED BUT DIFFICULT — not
recall, and not a guessing game from an artificially empty stem.

You (Optimizer / Evaluator / Scorer) are BUILDING this benchmark. You see the FULL
patient record. The answering agent that will later be tested does NOT — it sees the
vignette stem and whatever it successfully requests through the tools."""

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
  - Define the MINIMAL set of DECISIVE supplemental items required to answer.
  - The set may span ANY of the supplemental categories above (not just labs).
  - NECESSARY (the core property): without the full golden set the question is
    UNSOLVABLE — the vignette narrative alone must NOT be enough to pick the answer, and
    removing ANY golden item must leave the answer undeterminable. This necessity is what
    the benchmark tests.
  - "Sufficient" means: WITH the golden values + the vignette, a competent clinician can
    reach the answer. It does NOT mean the golden set captures every factor a clinician
    might ever consider. Real decisions are multifactorial; the golden set is the DECISIVE
    crux, not an exhaustive workup.
  - DO NOT expand the golden set to add merely-supportive or confirmatory labs. Minimal +
    decisive beats comprehensive.
  - Each golden item records: category, item_name, patient_value (a REAL value you
    retrieved for this patient before time-zero), why_required.
  - IMPORTANT (for the Evaluator): the golden_supplementals field is part of the ANSWER
    KEY. It is NOT shown to the solver — the solver only sees the stem and must retrieve
    values through the tools. Its patient_value entries are REQUIRED and their presence is
    NOT leakage. Judge golden_set_necessary_and_sufficient purely on whether those values
    are the ones truly needed to decide the answer — never penalize the field for
    containing values."""

# --------------------------------------------------------------------------
# Multiple-choice formatting rules
# --------------------------------------------------------------------------
MC_RULES = """\
MULTIPLE-CHOICE FORMAT (strict):
  - MULTI-SELECT: zero or more options may be correct; the answer key is a set.
  - The FINAL option must always be exactly "None of the above".
  - NO ANSWER GIVEAWAY: the stem must not name the target procedure/outcome or state
    the golden VALUES. A clinical vignette (history, comorbidities, qualitative course)
    IS expected and encouraged — it is not leakage. What is forbidden is stating the
    decisive numbers or naming the answer.
  - DISTRACTORS: wrong options must be plausible for a clinician but incorrect for
    THIS patient given the evidence. No obviously-absurd options.
  - Provide 4-6 options total, including "None of the above"."""

# --------------------------------------------------------------------------
# PubMed grounding rule
# --------------------------------------------------------------------------
PUBMED_RULE = """\
PUBMED GROUNDING (best-effort):
  - Attach a citation when you can find a RELEVANT real article: call search_articles and
    use a pmid FROM THE RESULTS (never invent a PMID). Prefer an article whose claim
    supports the causal chain.
  - A missing or imperfectly-matched citation does NOT fail the question. Never fabricate."""

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
  - QUALITATIVE in the stem, QUANTITATIVE behind the tools. The stem is a rich qualitative
    vignette (demographics, chief complaint, history/comorbidities, exam findings and course
    described in WORDS). It must contain NO numbers at all — no lab values, vital-sign numbers,
    doses, or thresholds. Every quantitative value lives in the tool-served table.
  - NON-DECISIVE stem: the narrative alone must not determine the answer. A clinician reading
    only the stem should find 2-3 options still plausible; the answer hinges on the retrieved
    numbers. A stem that telegraphs the answer is a defect.
  - The stem must NOT name the answer/target outcome.
  - Nothing dated AT/AFTER time-zero may appear in the stem or options.
  - Golden items must all pre-date time-zero and use REAL retrieved values."""


def canonical_rubric() -> dict:
    """The FIXED grading rubric attached to every accepted question (no LLM 'scorer').

    Consistent grading across the whole benchmark: how an answering agent's run is scored.
    """
    return {
        "request_scoring": {
            "per_request": {"0.0": "irrelevant / inaccurate justification",
                            "0.5": "accurate but generic/textbook, not patient-specific",
                            "1.0": "patient-specific justification + multi-item reasoning"},
            "golden_item_bonus": "+1.0 for EACH requested item that is in the golden set",
            "note": "per-request score = justification(0/0.5/1) + golden_bonus(0/1)",
        },
        "mc_correctness": "multi-select vs correct_options; credit correct 'None of the above'",
        "causal_answer": [
            {"criterion": "cites the retrieved golden values", "weight": 0.5},
            {"criterion": ">=2-step causal chain to the chosen answer", "weight": 0.5},
        ],
        "confidence": "recorded for calibration, not scored",
    }


def full_spec() -> str:
    """The complete shared spec block, in canonical order, for a system prompt."""
    return "\n\n".join([
        BENCHMARK_SPEC, TARGET_DEFS, SUPPLEMENTAL_CATEGORIES,
        GOLDEN_SET_RULE, MC_RULES, PUBMED_RULE, LEAKAGE_RULES,
    ])
