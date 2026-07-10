"""
multiarm_metrics.py  —  scoring for the 3-arm (PCI / CABG / medical) counterfactual task.

The model predicts an outcome under EACH arm. From that we score:

PROXY-FREE / decision metrics:
  - best_arm_accuracy     does the model pick the same best arm as the reference?
  - ranking_agreement     fraction of arm-pairs ordered the same way as the reference
  - policy_value_ips      expected outcome if we followed the model's arm choice (IPS, uses
                          the generalized propensity; lower = better for our outcomes)

VS reference effects (the answer-key per pairwise contrast):
  - pairwise_sign_agreement   sign(pred effect) == sign(reference effect) for a contrast
  - pairwise_pehe             RMSE(pred effect, reference effect) for a contrast

All functions take plain lists/arrays and ignore entries with missing (None/NaN) values.
"""

import numpy as np

ARMS = ["pci", "cabg", "medical"]


def _clean(*cols):
    arr = [np.asarray(c, float) for c in cols]
    m = np.ones(len(arr[0]), bool)
    for a in arr:
        m &= np.isfinite(a)
    return [a[m] for a in arr] + [int(m.sum())]


def best_arm_accuracy(pred_best, ref_best):
    """Fraction of patients where the model's recommended arm == the reference's best arm."""
    pairs = [(p, r) for p, r in zip(pred_best, ref_best) if p and r]
    if not pairs:
        return {"acc": None, "n": 0}
    return {"acc": round(float(np.mean([p == r for p, r in pairs])), 4), "n": len(pairs)}


def ranking_agreement(pred_outcomes, ref_outcomes):
    """Mean fraction of arm-pairs ordered the same way (lower outcome = preferred).
    pred_outcomes / ref_outcomes: list of dicts {arm: value} per patient."""
    fracs = []
    for pred, ref in zip(pred_outcomes, ref_outcomes):
        arms = [a for a in ARMS if a in pred and a in ref
                and pred[a] is not None and ref[a] is not None]
        if len(arms) < 2:
            continue
        agree = tot = 0
        for i in range(len(arms)):
            for j in range(i + 1, len(arms)):
                a, b = arms[i], arms[j]
                tot += 1
                agree += int(np.sign(pred[a] - pred[b]) == np.sign(ref[a] - ref[b]))
        if tot:
            fracs.append(agree / tot)
    if not fracs:
        return {"ranking_agreement": None, "n": 0}
    return {"ranking_agreement": round(float(np.mean(fracs)), 4), "n": len(fracs)}


def pairwise_sign_agreement(pred_effect, ref_effect):
    p, r, n = _clean(pred_effect, ref_effect)
    if n == 0:
        return {"sign_agree": None, "n": 0}
    return {"sign_agree": round(float(np.mean(np.sign(p) == np.sign(r))), 4), "n": n}


def pairwise_pehe(pred_effect, ref_effect):
    p, r, n = _clean(pred_effect, ref_effect)
    if n == 0:
        return {"pehe": None, "n": 0}
    return {"pehe": round(float(np.sqrt(np.mean((p - r) ** 2))), 4), "n": n}


def policy_value_ips(rec_arm, factual_arm, factual_y, gps, lower_is_better=True):
    """Self-normalized inverse-propensity value of the model's arm recommendation.

    Only patients whose ACTUAL arm matched the model's recommendation contribute, reweighted by
    1/P(actual arm | x) (the generalized propensity), which estimates the average outcome we'd
    get under the model's policy. rec_arm/factual_arm: lists of arm strings; factual_y: observed
    outcome; gps: list of {arm: prob}. Lower returned value = better (for our outcomes).
    """
    num = den = 0.0
    n = 0
    for rec, fac, y, g in zip(rec_arm, factual_arm, factual_y, gps):
        if not rec or not fac or y is None or not g:
            continue
        if rec == fac:
            p = max(float(g.get(fac, 0.0)), 1e-3)
            w = 1.0 / p
            num += w * float(y)
            den += w
            n += 1
    if den == 0:
        return {"policy_value": None, "n": 0}
    V = num / den
    return {"policy_value": round(float(V), 4), "n": n, "lower_is_better": lower_is_better}


def best_arm(outcomes, lower_is_better=True):
    """Pick the optimal arm from a {arm: value} dict (skips missing)."""
    cand = {a: v for a, v in outcomes.items() if a in ARMS and v is not None}
    if not cand:
        return None
    return (min if lower_is_better else max)(cand, key=cand.get)
