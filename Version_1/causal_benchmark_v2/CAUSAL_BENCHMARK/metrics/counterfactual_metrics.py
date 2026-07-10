"""
counterfactual_metrics.py  —  Task C individual-treatment-effect metrics.

Pure functions over aligned arrays. Two families:

PROXY-FREE (no counterfactual label needed — the most defensible signals):
  - rmse / nrmse            factual outcome prediction vs the OBSERVED outcome
  - direction_accuracy      predicted vs observed rising/falling/stable
  - ece                     calibration of the activation-confidence vs correctness
  - intervention_sensitivity how much the prediction moves when the treatment flips

PROXY-BASED (vs the k-NN matched proxy — interpret as AGREEMENT-WITH-MATCHER, not
true-effect recovery; see TASKC_RESULTS.md caveats):
  - pehe                    sqrt(mean((pred_ITE - proxy_ITE)^2))
  - sign_accuracy           sign(pred_ITE) == sign(proxy_ITE)
  - policy_value            IPS off-policy value of the model's treat/don't-treat rule
"""

import numpy as np


def _arr(*xs):
    return [np.asarray(x, dtype=float) for x in xs]


def _finite(*xs):
    xs = _arr(*xs)
    m = np.ones(len(xs[0]), bool)
    for x in xs:
        m &= np.isfinite(x)
    return [x[m] for x in xs] + [int(m.sum())]


def pehe(pred_ite, proxy_ite):
    p, q, n = _finite(pred_ite, proxy_ite)
    if n == 0:
        return {"pehe": None, "n": 0}
    return {"pehe": round(float(np.sqrt(np.mean((p - q) ** 2))), 4), "n": n}


def sign_accuracy(pred_ite, proxy_ite):
    p, q, n = _finite(pred_ite, proxy_ite)
    if n == 0:
        return {"sign_acc": None, "n": 0}
    return {"sign_acc": round(float(np.mean(np.sign(p) == np.sign(q))), 4), "n": n}


def rmse(pred, obs, log=False):
    """RMSE of predictions vs observed. log=True scores on log10 scale (positive level
    outcomes like troponin span orders of magnitude, so raw RMSE is dominated by outliers)."""
    p, o, n = _finite(pred, obs)
    if n == 0:
        return {"rmse": None, "n": 0}
    if log:
        m = (p > 0) & (o > 0)
        if m.sum() == 0:
            return {"rmse_log10": None, "n": 0}
        r = float(np.sqrt(np.mean((np.log10(p[m]) - np.log10(o[m])) ** 2)))
        return {"rmse_log10": round(r, 4), "n": int(m.sum())}
    r = float(np.sqrt(np.mean((p - o) ** 2)))
    return {"rmse": round(r, 4), "nrmse": round(r / (float(np.std(o)) + 1e-9), 4), "n": n}


def direction_accuracy(pred_dirs, true_dirs):
    pairs = [(a, b) for a, b in zip(pred_dirs, true_dirs) if a and b]
    if not pairs:
        return {"acc": None, "n": 0}
    return {"acc": round(float(np.mean([a == b for a, b in pairs])), 4), "n": len(pairs)}


def ece(confidences, correct, n_bins=5):
    """Expected calibration error of activation-confidence vs correctness (both 1-D)."""
    items = [(float(c), int(k)) for c, k in zip(confidences, correct) if c is not None]
    if not items:
        return {"ece": None, "n": 0}
    conf = np.array([c for c, _ in items])
    corr = np.array([k for _, k in items])
    bins = np.linspace(0, 1, n_bins + 1)
    e = 0.0
    for i in range(n_bins):
        hi = conf <= bins[i + 1] if i == n_bins - 1 else conf < bins[i + 1]
        m = (conf >= bins[i]) & hi
        if m.sum():
            e += m.mean() * abs(corr[m].mean() - conf[m].mean())
    return {"ece": round(float(e), 4), "overall_acc": round(float(corr.mean()), 4),
            "overall_conf": round(float(conf.mean()), 4), "n": len(items)}


def intervention_sensitivity(y_factual, y_counterfactual, dir_factual, dir_counterfactual):
    """Proxy-free causal probe: when the treatment flips, does the prediction move?
    A causal model moves a lot; a pattern-matcher barely moves."""
    yf, yc, n = _finite(y_factual, y_counterfactual)
    rel = float(np.mean(np.abs(yf - yc) / (np.abs(yf) + np.abs(yc) + 1e-6))) if n else None
    dpairs = [(a, b) for a, b in zip(dir_factual, dir_counterfactual) if a and b]
    flip = float(np.mean([a != b for a, b in dpairs])) if dpairs else None
    return {"mean_rel_change": round(rel, 4) if rel is not None else None,
            "direction_flip_rate": round(flip, 4) if flip is not None else None,
            "n": n}


def policy_value(pred_ite, factual_y, T, propensity, lower_is_better=True):
    """Self-normalized IPS value of the model's treat/don't-treat rule.

    The model recommends treatment when it predicts treatment IMPROVES the outcome
    (lowers the marker, if lower_is_better). Value = IPS-weighted mean factual outcome over
    patients whose actual treatment matched the recommendation. SURROGATE-TARGET ONLY:
    PCI mechanically perturbs these labs and mortality is unavailable, so a lower value does
    NOT equal clinical benefit. Reported with that caveat.
    """
    p, y, t, e, n = _finite(pred_ite, factual_y, T, propensity)
    if n == 0:
        return {"policy_value": None, "n": 0}
    t = t.astype(int)
    rec = ((p < 0) if lower_is_better else (p > 0)).astype(int)
    ps = np.where(t == 1, e, 1 - e)
    w = (t == rec).astype(float) / np.clip(ps, 1e-3, 1.0)
    if w.sum() == 0:
        return {"policy_value": None, "n": n}
    V = float(np.sum(w * y) / np.sum(w))
    obs = float(np.mean(y))
    improvement = (obs - V) if lower_is_better else (V - obs)
    return {"policy_value": round(V, 4), "observed_mean": round(obs, 4),
            "improvement_vs_observed": round(improvement, 4),
            "frac_recommend_treat": round(float(np.mean(rec)), 3), "n": n}
