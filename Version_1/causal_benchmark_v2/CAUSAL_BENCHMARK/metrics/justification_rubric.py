"""
justification_rubric.py  —  score the LLM's worded justification (0 / 0.5 / 1).

  0   nonsense   : empty, incoherent, self-contradictory, or hallucinated facts
  0.5 general    : coherent + correct general reasoning, but NOT patient-specific, OR specific
                   but the causal direction isn't verified / is inconsistent / is mere parroting
  1   specific+verified : cites THIS patient's real chart facts AND states a causal link whose
                          direction is verified against the answer-key, with a real mechanism

HYBRID design: grounding (#1) and causal-direction verification (#2) are AUTOMATIC and anchored
to ground truth (chart facts + answer-key effect sign) — hard to game. Coherence/parroting (#3)
uses a pluggable judge (`judge` callable); a heuristic default runs with no model, an LLM judge
slots in for the GPU scoring pass.

NOTE: score 1.0 requires a reference direction (answer-key). Until that exists, "verified" is
unknown, so the ceiling is 0.5 — by design (we don't award "causally verified" without a check).
"""

import re

POS = ["lower", "reduce", "decreas", "less", "prevent", "benefit", "improv", "protect", "fewer"]
NEG = ["raise", "increas", "higher", "worsen", "more ", "harm", "elevat", "induce", "risk of"]
MECHANISM = ["because", "due to", "via", "mechanism", "leads to", "causes", "results in",
             "by ", "so ", "therefore", "contrast", "occlu", "perfus", "ischem", "reperfus"]

COMORBID_SYN = {
    "diabetes": ["diabet"], "hypertension": ["hypertens", "htn"], "ckd": ["kidney", "renal", "ckd"],
    "heart_failure": ["heart failure", "chf", " hf "], "afib": ["fibrillation", "afib"],
    "prior_mi": ["prior mi", "previous infarct", "old infarct", "prior infarct"],
    "hyperlipidemia": ["lipid", "cholesterol"], "copd": ["copd", "pulmonary disease"],
    "cad": ["coronary", "cad", "atheroscler"], "valve": ["valve", "valvular"],
}
OUTCOME_TERMS = {
    "readmit30": ["readmit", "readmission", "discharge", "return"],
    "aki": ["kidney", "renal", "creatinine", "aki", "nephropathy", "nephrotox"],
}
ARM_TERMS = ["pci", "stent", "angioplasty", "cabg", "bypass", "surg", "medical", "revascular", "conservativ"]


def _chart_numbers(context):
    nums = set()
    cc = context.get("clinical_context", {})
    for series in cc.get("labs_full", {}).values():
        for p in series:
            try:
                nums.add(round(float(p["value"]), 2))
            except Exception:
                pass
    for s in cc.get("labs_all", {}).values():
        for k in ("latest", "first", "min", "max"):
            if s.get(k) is not None:
                nums.add(round(float(s[k]), 2))
    return nums


def grounding(text, context):
    """Patient-specificity via grounding against the actual chart (numbers + comorbidities)."""
    t = text.lower()
    cnums = _chart_numbers(context)
    text_nums = [float(x) for x in re.findall(r"-?\d+\.?\d+", t)]   # require a decimal -> lab-like
    grounded = sum(1 for v in text_nums if any(abs(v - c) <= max(0.05, 0.02 * abs(c)) for c in cnums))
    # a decimal lab-like number that matches NOTHING in the chart and isn't a window/prob -> fabricated
    halluc = sum(1 for v in text_nums
                 if v not in (0.3, 1.5, 7.0, 24.0, 48.0, 72.0) and not (0 <= v <= 1)
                 and not any(abs(v - c) <= max(0.05, 0.02 * abs(c)) for c in cnums))
    present = [k for k, v in context.get("comorbidities", {}).items() if v]
    com_hits = sum(1 for k in present if any(syn in t for syn in COMORBID_SYN.get(k, [k])))
    return {"grounded_numbers": grounded, "comorbid_hits": com_hits,
            "hallucinated_numbers": halluc, "specific": (grounded >= 1 or com_hits >= 1)}


def _polarity(text):
    t = text.lower()
    p = sum(t.count(w) for w in POS)
    n = sum(t.count(w) for w in NEG)
    return "lower" if p > n else ("higher" if n > p else "neutral")


def _norm_dir(d):
    if d in ("falling", "lower", "-", "decrease"):
        return "lower"
    if d in ("rising", "higher", "+", "increase"):
        return "higher"
    return "neutral"


def causal_consistent(text, model_direction):
    """Does the prose's polarity agree with the model's own predicted direction (not contradict)?"""
    tp = _polarity(text)
    md = _norm_dir(model_direction)
    return tp == "neutral" or md == "neutral" or tp == md


def causal_verified(model_direction, ref_direction):
    """Is the model's claimed effect direction confirmed by the reference (answer-key)?
    None if no reference available yet."""
    if ref_direction is None:
        return None
    return _norm_dir(model_direction) == _norm_dir(ref_direction)


def coherence_heuristic(text, outcome_id):
    t = text.lower().strip()
    if len(t) < 15 or len(set(t.split())) < 5:
        return False
    on_topic = any(a in t for a in ARM_TERMS) and any(o in t for o in OUTCOME_TERMS.get(outcome_id, []))
    contradictory = (("lower" in t or "decreas" in t) and ("higher" in t or "increas" in t))
    return on_topic and not contradictory


def is_parroting(text):
    """Specific numbers but no causal/mechanism language -> fact-parroting, not reasoning."""
    t = text.lower()
    has_polarity = any(w in t for w in POS + NEG)
    has_mech = any(w in t for w in MECHANISM)
    return not (has_polarity or has_mech)


def score_justification(text, context, model_direction, ref_direction=None, outcome_id="", judge=None):
    """Return {score: 0/0.5/1, reason, subscores...}. judge(text, context, outcome_id) ->
    {coherent: bool, parroting: bool} overrides the heuristics when provided (hybrid mode)."""
    if not text or not str(text).strip():
        return {"score": 0.0, "reason": "empty"}
    g = grounding(text, context)
    if g["hallucinated_numbers"] >= 1 and g["grounded_numbers"] == 0:
        return {"score": 0.0, "reason": "hallucinated_facts", **g}
    if judge is not None:
        v = judge(text, context, outcome_id)
        coherent, parroting = v.get("coherent", True), v.get("parroting", is_parroting(text))
    else:
        coherent, parroting = coherence_heuristic(text, outcome_id), is_parroting(text)
    if not coherent:
        return {"score": 0.0, "reason": "incoherent", **g}
    verified = causal_verified(model_direction, ref_direction)
    consistent = causal_consistent(text, model_direction)
    if g["specific"] and verified is True and consistent and not parroting:
        score, reason = 1.0, "patient_specific_causal_verified"
    else:
        score, reason = 0.5, "general_or_unverified"
    return {"score": score, "reason": reason, "verified": verified,
            "consistent": consistent, "parroting": parroting, **g}
