"""Benchmark B schema + Evaluator-Optimizer JSON contracts (post-procedure trajectory prediction).

The optimizer drafts a CANDIDATE (question + per-lab causal justification of the EXPECTED direction);
the directions themselves are DATA-DERIVED ground truth (qgen.trajectory). The record stores both the
optimizer's expected_direction and the authoritative true_direction, plus run-harness placeholders for
the agent's stated confidence and the activation-function softmax over {Rising,Falling,Stable}.
"""
from __future__ import annotations

import hashlib

PIPELINE_VERSION = "qgenB-0.1.0"

EVAL_DIMS = (
    "answerable_from_pre_state",   # answerable from pre-procedure state + the procedure (not post-hoc)
    "patient_specific",            # justification uses THIS patient's actual pre-values/comorbidities
    "requires_causal_reasoning",   # procedure -> physiology -> lab chain (>=2 steps)
    "guideline_grounded",          # a real PubMed cite supports the procedure's effect on the lab
)

DIRECTIONS = ("Rising", "Falling", "Stable")

CANDIDATE_TEMPLATE = {
    "question_text": "string — ask the test-taker to predict each target lab's post-procedure direction; "
                     "do NOT reveal the directions or name the diagnosis (no buzzword bingo)",
    "target_labs": ["Creatinine", "Potassium"],
    "per_lab": [{"label": "Creatinine", "expected_direction": "Rising|Falling|Stable",
                 "causal_justification": "why THIS procedure drives THIS lab that way for THIS patient",
                 "guideline_citation": {"pmid": "########", "claim": "..."}}],
    "pubmed_citations": [{"pmid": "########", "title": "..."}],
}

VERDICT_TEMPLATE = {
    "dims": {d: {"pass": True, "reason": "..."} for d in EVAL_DIMS},
    "accept": False,
    "actionable_feedback": "concrete edits for the next draft",
}


def intent_fingerprint(rec: dict) -> str:
    proc = str((rec.get("procedure") or {}).get("label", "")).lower()
    labs = sorted({str(l.get("label", "")).lower() for l in rec.get("target_labs_detail", rec.get("per_lab", []))})
    return hashlib.sha1(f"{proc}|{'+'.join(labs)}".encode()).hexdigest()[:16]


def build_record(qid: str, context: dict, candidate: dict, verdict: dict, n_iterations: int,
                 provenance: dict) -> dict:
    """Merge optimizer candidate with the authoritative ground-truth trajectories into a record."""
    truth = context.get("trajectories", {})
    opt_by_lab = {str(l.get("label")): l for l in candidate.get("per_lab", [])}
    target = candidate.get("target_labs") or list(truth.keys())
    detail = []
    for lab in target:
        if lab not in truth:
            continue
        t = truth[lab]; o = opt_by_lab.get(lab, {})
        exp = str(o.get("expected_direction", "")).capitalize()
        detail.append({
            "label": lab,
            "true_direction": t["direction"],            # authoritative (data-derived)
            "expected_direction": exp or None,           # optimizer's claim
            "direction_match": (exp == t["direction"]) if exp else None,
            "basis": t["basis"], "ref_lower": t["ref_lower"], "ref_upper": t["ref_upper"],
            "baseline": t["baseline"], "post_rep": t["post_rep"], "unit": t["unit"],
            "n_pre": t["n_pre"], "n_post": t["n_post"],
            "causal_justification": o.get("causal_justification", ""),
            "guideline_citation": o.get("guideline_citation", {}),
            # run-harness fills these at evaluation time:
            "run_prediction": {"direction": None, "stated_confidence": None,
                               "activation_probs": {"Rising": None, "Falling": None, "Stable": None}},
        })
    return {
        "question_id": qid, "pipeline_version": PIPELINE_VERSION,
        "proc_uid": context.get("proc_uid"),
        "question_text": candidate.get("question_text", ""),
        "hadm_id": context["hadm_id"], "subject_id": context["subject_id"],
        "time_zero": context["time_zero"], "time_zero_policy": context["time_zero_policy"],
        "procedure": context["procedure"], "prior_procedures": context.get("prior_procedures", []),
        "target_labs_detail": detail,
        "pubmed_citations": candidate.get("pubmed_citations", []),
        "evaluator_scores": verdict.get("dims", {}), "accepted": True, "n_iterations": n_iterations,
        "demographics": context.get("demographics", {}), "comorbidities": context.get("comorbidities", {}),
        "provenance": provenance,
    }


def is_valid_candidate(c) -> bool:
    return (isinstance(c, dict) and bool(c.get("question_text"))
            and isinstance(c.get("target_labs"), list) and len(c.get("target_labs")) >= 1
            and isinstance(c.get("per_lab"), list) and len(c.get("per_lab")) >= 1)


# ── deterministic leak guard (no LLM): B's stem must NOT ASSERT a direction ──────────────────
# NOTE: the stem legitimately lists the option set (rising/falling/stable) and names the target labs —
# that is NOT a leak. A leak is the stem ASSERTING the answer ("will rise", "expected to fall", ...).
_B_ASSERT = ("will rise", "will fall", "will increase", "will decrease", "will drop", "will climb",
             "will remain", "will stay", "will normalize", "will worsen", "will improve",
             "expected to rise", "expected to fall", "expected to increase", "expected to decrease",
             "likely to rise", "likely to fall", "likely to increase", "likely to decrease",
             "trend upward", "trend downward", "trending up", "trending down")


def stem_leaks(candidate, context=None) -> list:
    """Return direction ASSERTIONS leaked in question_text (empty = clean). Option-set listing is allowed."""
    q = str(candidate.get("question_text", "")).lower()
    return sorted({p for p in _B_ASSERT if p in q})
