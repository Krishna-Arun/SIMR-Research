"""Benchmark C schema + Evaluator-Optimizer JSON contracts (counterfactual intervention identification).

Two overlap-matched patients with different procedures; one patient's post-state is shown. Ground truth
= which patient (A/B). The optimizer writes the framing + causal justification distinguishing the two
procedures; it must NOT reveal the owner in the stem. The record reserves run-harness placeholders for
the agent's choice, stated confidence, and the activation-function probability.
"""
from __future__ import annotations

import hashlib

PIPELINE_VERSION = "qgenC-0.1.0"

EVAL_DIMS = (
    "answerable_from_states",      # the post-state is distinguishable via the two procedures' causal effects
    "patient_specific",            # references the patients' actual baseline / post values
    "requires_causal_reasoning",   # a causal chain distinguishing procedure X vs Y (>=2 steps)
    "guideline_grounded",          # a real PubMed cite supports each procedure's physiologic effect
)

CANDIDATE_TEMPLATE = {
    "question_text": "string — present both patients + the unlabeled post-state; ask which patient/procedure "
                     "produced it. Do NOT reveal the answer (which patient) or name it in the stem.",
    "predicted_owner": "A|B",
    "causal_justification": "why the shown post-state matches that patient's procedure and not the other",
    "distinguishing_features": [{"procedure": "X", "expected_effect": "what X does to which labs (causal)"}],
    "pubmed_citations": [{"pmid": "########", "title": "..."}],
}

VERDICT_TEMPLATE = {
    "dims": {d: {"pass": True, "reason": "..."} for d in EVAL_DIMS},
    "accept": False,
    "actionable_feedback": "concrete edits for the next draft",
}


def intent_fingerprint(rec: dict) -> str:
    a = str(rec.get("procA", "")).lower(); b = str(rec.get("procB", "")).lower()
    pair = "|".join(sorted([a, b]))
    return hashlib.sha1(f"{pair}|{rec.get('pair_uid','')}".encode()).hexdigest()[:16]


def build_record(qid: str, context: dict, candidate: dict, verdict: dict, n_iterations: int,
                 provenance: dict) -> dict:
    pred = str(candidate.get("predicted_owner", "")).upper().strip()
    return {
        "question_id": qid, "pipeline_version": PIPELINE_VERSION,
        "pair_uid": context["pair_uid"],
        "question_text": candidate.get("question_text", ""),
        "patient_A": context["patient_A"], "patient_B": context["patient_B"],
        "procA": context["procA"], "procB": context["procB"],
        "shown_post_labs": context["shown_post_labs"],
        "shown_post_owner": context["shown_post_owner"],          # GROUND TRUTH
        "optimizer_predicted_owner": pred or None,
        "optimizer_correct": (pred == context["shown_post_owner"]) if pred else None,
        "causal_justification": candidate.get("causal_justification", ""),
        "distinguishing_features": candidate.get("distinguishing_features", []),
        "pubmed_citations": candidate.get("pubmed_citations", []),
        "match_quality": context.get("match_quality", {}),
        "evaluator_scores": verdict.get("dims", {}), "accepted": True, "n_iterations": n_iterations,
        # run-harness fills these at evaluation time:
        "run_prediction": {"owner": None, "stated_confidence": None,
                           "activation_probs": {"A": None, "B": None}},
        "provenance": provenance,
    }


def is_valid_candidate(c) -> bool:
    return (isinstance(c, dict) and bool(c.get("question_text"))
            and str(c.get("predicted_owner", "")).upper().strip() in ("A", "B")
            and bool(c.get("causal_justification")))


# ── deterministic leak guard (no LLM): C's stem must NOT tie the POST-STATE to a specific patient ─
# NOTE: describing each patient's own procedure ("patient A underwent dialysis") is legitimate context,
# NOT a leak. A leak EXPLICITLY assigns the shown post-state / answer to a specific patient (A or B).
_C_GIVEAWAY = ("belongs to patient a", "belongs to patient b", "produced by patient a",
               "produced by patient b", "post-state belongs to patient", "post-state is from patient a",
               "post-state is from patient b", "owner is patient", "answer is patient a",
               "answer is patient b", "correct answer is patient", "labs shown are from patient a",
               "labs shown are from patient b")


def stem_leaks(candidate, context=None) -> list:
    """Return explicit owner-reveal phrases leaked in question_text (empty = clean)."""
    q = str(candidate.get("question_text", "")).lower()
    return sorted({p for p in _C_GIVEAWAY if p in q})
