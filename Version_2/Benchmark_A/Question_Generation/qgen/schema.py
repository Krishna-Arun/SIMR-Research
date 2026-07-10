"""Per-question record schema + JSON contracts for the Evaluator-Optimizer exchange.

The optimizer emits a CANDIDATE; the evaluator emits a VERDICT; on accept we assemble a RECORD
(one line in questions.jsonl). Keeping the contracts here means optimizer/evaluator/orchestrator all
agree on field names without re-deriving them.
"""
from __future__ import annotations

import hashlib
from typing import Any

PIPELINE_VERSION = "qgen-0.1.0"

EVAL_DIMS = (
    "answerable_with_labs_micro",   # answerable ONLY with labs/micro (not vitals/imaging/notes)
    "patient_specific",             # grounded in THIS patient's chart, not a textbook question
    "requires_causal_reasoning",    # needs a >=2-step causal chain, not a single lookup
    "guideline_grounded",           # supported by a real PubMed guideline/citation
)

# JSON the optimizer must return (its agentic `final.result`)
CANDIDATE_KEYS = ("question_text", "type", "gold_labs", "gold_micro",
                  "reference_answer", "causal_chain", "pubmed_citations")

# A minimal example shown to the optimizer to anchor the output shape.
CANDIDATE_TEMPLATE = {
    "question_text": "string — the clinical question about THIS patient",
    "type": "diagnosis | intervention",
    "gold_labs": [{"label": "Lactate", "proposed_reason": "why this lab matters for THIS patient",
                   "guideline_citation": {"pmid": "########", "claim": "what the cite supports"}}],
    "gold_micro": [{"specimen": "Blood Culture", "organism": "MRSA",
                    "guideline_citation": {"pmid": "########", "claim": "..."}}],
    "reference_answer": "string — the correct answer (diagnosis or intervention)",
    "causal_chain": ["finding -> mechanism -> finding -> conclusion (>=2 linked steps)"],
    "pubmed_citations": [{"pmid": "########", "title": "..."}],
}

VERDICT_TEMPLATE = {
    "dims": {d: {"pass": True, "reason": "..."} for d in EVAL_DIMS},
    "gold_lab_verdicts": [{"label": "Lactate", "in_chart": True, "abnormal": True,
                           "guideline_supported": True, "pmid": "########",
                           "verdict": "keep | drop: <reason>"}],
    "accept": False,
    "actionable_feedback": "concrete edits for the next draft",
}


def intent_fingerprint(candidate: dict) -> str:
    """Stable fingerprint of (type, primary concept, gold lab/micro signature) for cross-Q dedup."""
    qtype = str(candidate.get("type", "")).lower()
    labs = sorted({str(g.get("label", "")).lower() for g in candidate.get("gold_labs", []) if g})
    orgs = sorted({str(g.get("organism", "")).lower() for g in candidate.get("gold_micro", []) if g})
    sig = f"{qtype}|{'+'.join(labs)}|{'+'.join(orgs)}"
    return hashlib.sha1(sig.encode()).hexdigest()[:16]


def build_record(qid: str, context: dict, candidate: dict, verdict: dict,
                 n_iterations: int, provenance: dict) -> dict:
    """Assemble the final persisted record from an accepted candidate."""
    return {
        "question_id": qid,
        "pipeline_version": PIPELINE_VERSION,
        "question_text": candidate.get("question_text", ""),
        "type": candidate.get("type", ""),
        "subject_id": context["subject_id"],
        "hadm_id": context["hadm_id"],
        "time_zero": context["time_zero"],
        "time_zero_policy": context["time_zero_policy"],
        "gold_labs": candidate.get("gold_labs", []),
        "gold_micro": candidate.get("gold_micro", []),
        "reference_answer": candidate.get("reference_answer", ""),
        "causal_chain": candidate.get("causal_chain", []),
        "pubmed_citations": candidate.get("pubmed_citations", []),
        "evaluator_scores": verdict.get("dims", {}),
        "accepted": True,
        "n_iterations": n_iterations,
        "demographics": context.get("demographics", {}),
        "comorbidities": context.get("comorbidities", {}),
        "provenance": provenance,
    }


def is_valid_candidate(c: Any) -> bool:
    return isinstance(c, dict) and bool(c.get("question_text")) and c.get("type") in ("diagnosis", "intervention") \
        and isinstance(c.get("gold_labs"), list)


# ── deterministic leak guard (replaces the evaluator's leak check; no LLM) ───────────────────
# A's stem must NOT name labs/values or the diagnosis — the test-taker must REQUEST the labs.
_A_LAB_TOKENS = ("troponin", "creatinine", "creatine kinase", "ck-mb", "ck mb", "ckmb", "lactate",
                 "bnp", "nt-probnp", "probnp", "potassium", "magnesium", "sodium", "chloride",
                 "bicarbonate", "anion gap", "hemoglobin", "hematocrit", "platelet", "white blood",
                 "wbc", "urea", "bun", "inr", "ptt", "d-dimer", "glucose", "albumin", "bilirubin")
_A_DX_BUZZ = ("stemi", "nstemi", "myocardial infarction", "cardiogenic shock", "septic shock",
              "sepsis", "aki", "acute kidney injury", "dialysis", "tamponade", "dka",
              "pulmonary edema", "endocarditis")


def stem_leaks(candidate, context=None) -> list:
    """Return list of leaked terms in question_text (empty = clean). Catches gold-lab names (>=4 chars,
    avoids single-letter false positives), common cardiac lab tokens, and diagnosis buzzwords."""
    q = str(candidate.get("question_text", "")).lower()
    leaked = []
    for g in candidate.get("gold_labs", []) or []:
        lbl = str(g.get("label", "")).strip().lower()
        if len(lbl) >= 4 and lbl in q:
            leaked.append(lbl)
    leaked += [t for t in _A_LAB_TOKENS if t in q]
    leaked += [d for d in _A_DX_BUZZ if d in q]
    return sorted(set(leaked))
