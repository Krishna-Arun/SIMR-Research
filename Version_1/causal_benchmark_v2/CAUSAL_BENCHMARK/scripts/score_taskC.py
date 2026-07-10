"""
score_taskC.py  —  score Task C counterfactual predictions.

Consumes:
  - data/taskC_matched.json  (proxy counterfactual labels, proxy ITE, factual values +
    directions, and the same-arm factual-validation estimates), and
  - answers/taskC_*.json      (LLM predictions: value+direction+confidence, factual & CF).

Reports two metric blocks, deliberately separated:

  HEADLINE (proxy-free, fully real): factual RMSE, factual direction accuracy,
    activation-confidence ECE, intervention-flip sensitivity.
  SECONDARY (vs the k-NN proxy = AGREEMENT-WITH-MATCHER, not true PEHE): proxy-PEHE,
    treatment-sign agreement, policy value (surrogate-target).

Baselines: matched-NN (the proxy itself — a ~0 proxy-PEHE ceiling, NOT a fair competitor),
and cross-fit T-learner / S-learner (independent of the proxy label). Also reports the
matched estimator's FACTUAL validation error (how much to trust the proxy at all).

Outputs: outputs/taskC_results.json + outputs/TASKC_RESULTS.md
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

BENCH = Path(__file__).parent.parent
sys.path.insert(0, str(BENCH / "scripts"))
sys.path.insert(0, str(BENCH / "metrics"))

import taskC_common as tc
import counterfactual_metrics as cm

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MATCHED = BENCH / "data" / "taskC_matched.json"
ANSWERS = BENCH / "answers"
OUTPUTS = BENCH / "outputs"
OUTPUTS.mkdir(exist_ok=True)


# ── learner baselines (cross-fit, independent of the proxy label) ───────────
def _cross_fit(X, T, y, mode, seed=0):
    """Return (ite_by_row, factual_pred_by_row) for a T- or S-learner via 2-fold cross-fit.
    Rows with non-finite y are excluded from TRAINING but still get predictions."""
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.model_selection import KFold

    n = len(y)
    ite = np.full(n, np.nan)
    fac = np.full(n, np.nan)
    idx = np.arange(n)
    kf = KFold(n_splits=2, shuffle=True, random_state=seed)
    for tr, te in kf.split(idx):
        ytr_ok = tr[np.isfinite(y[tr])]
        if len(ytr_ok) < 10:
            continue
        if mode == "t":
            tr1 = ytr_ok[T[ytr_ok] == 1]   # treated training rows with finite y
            tr0 = ytr_ok[T[ytr_ok] == 0]   # control training rows with finite y
            if len(tr1) < 5 or len(tr0) < 5:
                continue
            m1 = GradientBoostingRegressor(random_state=seed).fit(X[tr1], y[tr1])
            m0 = GradientBoostingRegressor(random_state=seed).fit(X[tr0], y[tr0])
            mu1, mu0 = m1.predict(X[te]), m0.predict(X[te])
        else:  # s-learner: augment with treatment column
            XT = np.column_stack([X, T])
            m = GradientBoostingRegressor(random_state=seed).fit(XT[ytr_ok], y[ytr_ok])
            x1 = np.column_stack([X[te], np.ones(len(te))])
            x0 = np.column_stack([X[te], np.zeros(len(te))])
            mu1, mu0 = m.predict(x1), m.predict(x0)
        ite[te] = mu1 - mu0
        fac[te] = np.where(T[te] == 1, mu1, mu0)
    return ite, fac


# ── load proxy labels ───────────────────────────────────────────────────────
def load_matched():
    m = json.loads(MATCHED.read_text())
    primary = m["primary_outcome"]
    secondary = m.get("secondary_outcome")
    rec = {}
    for r in m["episodes"]:
        rec[r["episode_id"]] = r
    return m, primary, secondary, rec


def proxy_block(rec, key):
    """Per-eid proxy fields for an outcome key."""
    out = {}
    for eid, r in rec.items():
        o = r["outcomes"].get(key, {})
        out[eid] = {
            "T": r["treatment"], "propensity": r["propensity"],
            "factual": o.get("factual"), "ite_proxy": o.get("ite_proxy"),
            "factual_dir": o.get("factual_direction"),
            "cf_dir_proxy": o.get("counterfactual_direction_proxy"),
            "factual_est_same_arm": o.get("factual_estimate_same_arm"),
        }
    return out


# ── assemble a method's predictions into aligned arrays ─────────────────────
def evaluate(eids, pred_ite, factual_pred, pb, factual_dir=None, cf_dir=None,
             conf=None, y_cf_pred=None, is_level=True):
    """Compute the metric blocks for one method over the given eids."""
    A = lambda d: np.array([d.get(e, np.nan) if d is not None else np.nan for e in eids], float)
    pite = A(pred_ite)
    fpred = A(factual_pred)
    proxy_ite = np.array([pb[e]["ite_proxy"] if pb[e]["ite_proxy"] is not None else np.nan
                          for e in eids], float)
    fobs = np.array([pb[e]["factual"] if pb[e]["factual"] is not None else np.nan
                     for e in eids], float)
    T = np.array([pb[e]["T"] for e in eids], float)
    prop = np.array([pb[e]["propensity"] for e in eids], float)

    res = {
        "n": len(eids),
        # HEADLINE causal quantity: does the model get the SIGN of the treatment effect right?
        "effect_sign_agreement": cm.sign_accuracy(pite, proxy_ite),
        # proxy-free reliability
        "factual_rmse": cm.rmse(fpred, fobs),
        "factual_rmse_log10": cm.rmse(fpred, fobs, log=True) if is_level else None,
        # magnitude vs proxy (secondary)
        "proxy_pehe": cm.pehe(pite, proxy_ite),
        "policy_value": cm.policy_value(pite, fobs, T, prop, lower_is_better=tc.LOWER_IS_BETTER),
    }
    if factual_dir is not None:
        obs_dir = [pb[e]["factual_dir"] for e in eids]
        res["factual_direction_acc"] = cm.direction_accuracy([factual_dir.get(e) for e in eids], obs_dir)
        if conf is not None:
            correct = [int(factual_dir.get(e) == pb[e]["factual_dir"])
                       if factual_dir.get(e) and pb[e]["factual_dir"] else None for e in eids]
            cvals = [conf.get(e) for e in eids]
            pairs = [(c, k) for c, k in zip(cvals, correct) if c is not None and k is not None]
            res["confidence_ece"] = cm.ece([c for c, _ in pairs], [k for _, k in pairs])
    if cf_dir is not None:
        res["cf_direction_acc_vs_proxy"] = cm.direction_accuracy(
            [cf_dir.get(e) for e in eids], [pb[e]["cf_dir_proxy"] for e in eids])
    if y_cf_pred is not None and factual_dir is not None and cf_dir is not None:
        res["intervention_sensitivity"] = cm.intervention_sensitivity(
            fpred, A(y_cf_pred), [factual_dir.get(e) for e in eids], [cf_dir.get(e) for e in eids])
    return res


def llm_arrays(preds, pid):
    """From a model's predictions, build per-eid pred_ITE, factual/cf value & direction & conf."""
    pred_ite, fpred, ycf, fdir, cdir, conf = {}, {}, {}, {}, {}, {}
    for eid, p in preds.items():
        arm = p.get("arm")
        f = p.get("factual", {}).get(pid, {})
        c = p.get("counterfactual", {}).get(pid, {})
        yf, yc = f.get("value"), c.get("value")
        fpred[eid] = yf if yf is not None else np.nan
        ycf[eid] = yc if yc is not None else np.nan
        fdir[eid] = f.get("direction")
        cdir[eid] = c.get("direction")
        cf_conf = (f.get("confidence") or {}).get("p")
        conf[eid] = cf_conf
        if yf is not None and yc is not None:
            y1, y0 = (yf, yc) if arm == "pci" else (yc, yf)
            pred_ite[eid] = y1 - y0
    return pred_ite, fpred, ycf, fdir, cdir, conf


def main():
    if not MATCHED.exists():
        log.error(f"missing {MATCHED} — run build_propensity_matches.py first")
        return 1
    matched, primary, secondary, rec = load_matched()
    pid = tc.OUTCOME_ID[primary]
    is_level = primary.startswith("peak_")     # level outcome (log-scale value error) vs delta
    pb = proxy_block(rec, primary)
    log.info(f"Primary outcome={primary} (id={pid}); {len(rec)} matched episodes")

    # Matcher factual-validation (proxy trust): same-arm estimate vs observed factual.
    fe = np.array([pb[e]["factual_est_same_arm"] if pb[e]["factual_est_same_arm"] is not None else np.nan
                   for e in pb], float)
    fo = np.array([pb[e]["factual"] if pb[e]["factual"] is not None else np.nan for e in pb], float)
    matcher_validation = cm.rmse(fe, fo)
    log.info(f"Matched-estimator FACTUAL validation RMSE (proxy trust): {matcher_validation}")

    results = {"primary_outcome": primary, "secondary_outcome": secondary,
               "matched_estimator_factual_validation": matcher_validation,
               "n_matched_episodes": len(rec), "methods": {}}

    # ── baselines ────────────────────────────────────────────────────────────
    _, episodes = tc.load_episodes()
    X, names, ids, T = tc.build_covariate_matrix(episodes)
    y_primary = np.array([tc.outcome_value(e, primary) if tc.outcome_value(e, primary) is not None
                          else np.nan for e in tc.taskC_cohort(episodes)], float)
    id_index = {e: i for i, e in enumerate(ids)}
    base_eids = [e for e in ids if e in pb]

    # matched-NN baseline = the proxy itself (ceiling; pred_ITE == proxy_ITE by construction).
    nn_ite = {e: pb[e]["ite_proxy"] for e in base_eids}
    nn_fac = {e: pb[e]["factual_est_same_arm"] for e in base_eids}
    results["methods"]["baseline_matched_nn (proxy ceiling)"] = evaluate(
        [e for e in base_eids if pb[e]["ite_proxy"] is not None], nn_ite, nn_fac, pb, is_level=is_level)

    for mode, label in [("t", "baseline_T_learner"), ("s", "baseline_S_learner")]:
        try:
            ite, fac = _cross_fit(X, T, y_primary, mode)
            ite_d = {ids[i]: (ite[i] if np.isfinite(ite[i]) else None) for i in range(len(ids))}
            fac_d = {ids[i]: (fac[i] if np.isfinite(fac[i]) else None) for i in range(len(ids))}
            results["methods"][label] = evaluate(base_eids, ite_d, fac_d, pb, is_level=is_level)
        except Exception as e:
            log.warning(f"{label} failed: {e}")

    # ── LLM prediction files ───────────────────────────────────────────────────
    for f in sorted(ANSWERS.glob("taskC_*.json")):
        if f.suffix == ".tmp":
            continue
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        preds = d.get("predictions", {})
        if not preds:
            continue
        name = f"{d.get('model','?')} [{d.get('prompt_style','?')}]"
        pred_ite, fpred, ycf, fdir, cdir, conf = llm_arrays(preds, pid)
        eids = [e for e in preds if e in pb]
        results["methods"][name] = evaluate(
            eids, pred_ite, fpred, pb, factual_dir=fdir, cf_dir=cdir, conf=conf,
            y_cf_pred=ycf, is_level=is_level)
        log.info(f"scored {name}: n={len(eids)}")

    (OUTPUTS / "taskC_results.json").write_text(json.dumps(results, indent=2))
    write_report(results, matched)
    log.info(f"Wrote {OUTPUTS/'taskC_results.json'} and {OUTPUTS/'TASKC_RESULTS.md'}")
    return 0


def _g(d, *path, default="—"):
    for k in path:
        d = d.get(k) if isinstance(d, dict) else None
        if d is None:
            return default
    return d


def write_report(results, matched):
    L = []
    L += [f"# Task C — Counterfactual Treatment-Effect Benchmark (PCI / ACS)", "",
          f"**Generated:** {datetime.now().isoformat()}",
          f"**Primary outcome (auto-selected):** `{results['primary_outcome']}`  ·  "
          f"**secondary:** `{results.get('secondary_outcome')}`",
          f"**Matched episodes:** {results['n_matched_episodes']}  ·  "
          f"**Propensity AUC:** {matched.get('propensity_auc')}  ·  "
          f"**Embedding:** {_g(matched,'matching','embedding')}  ·  "
          f"**Caliper:** {_g(matched,'matching','caliper')}", ""]

    bal = matched.get("balance", {})
    L += ["## Covariate balance / overlap", "",
          f"- mean|SMD| pre-match → post-match: **{_g(bal,'pre_match','mean_abs_smd')} → "
          f"{_g(bal,'post_match','mean_abs_smd')}** (post max {_g(bal,'post_match','max_abs_smd')}; target <0.1)",
          f"- propensity overlap: PCI {_g(matched,'overlap','propensity_pci')} vs "
          f"control {_g(matched,'overlap','propensity_control')}; "
          f"matched: PCI {_g(matched,'overlap','frac_pci_matched')}, "
          f"control {_g(matched,'overlap','frac_control_matched')}", ""]

    mv = results["matched_estimator_factual_validation"]
    L += ["## Proxy trust — matched-estimator factual validation", "",
          "How well the k-NN matcher reproduces *observed* outcomes from same-arm neighbors "
          "(a held-out factual check). Larger error ⇒ trust the proxy counterfactual less.",
          f"- factual RMSE = **{_g(mv,'rmse')}** (nRMSE {_g(mv,'nrmse')}, n={_g(mv,'n')})", ""]

    # HEADLINE: causal performance — does the model get WHO-BENEFITS (effect sign) right,
    # and does it actually condition on the treatment (flip probe)?
    L += ["## Headline — causal performance", "",
          "Treatment-effect **sign agreement** = does sign(predicted ITE) match sign(proxy ITE) "
          "(the core 'who benefits' quantity; vs the matched proxy). **Flip** = when the treatment "
          "is swapped, how often does the predicted direction change / by how much (proxy-free — "
          "high ⇒ the model genuinely conditions on the intervention).", "",
          "| Method | n | effect-sign agree | flip dir-rate | flip rel-Δ |",
          "|---|---|---|---|---|"]
    for name, r in results["methods"].items():
        L.append(f"| {name} | {r.get('n')} | **{_g(r,'effect_sign_agreement','sign_acc')}** | "
                 f"{_g(r,'intervention_sensitivity','direction_flip_rate')} | "
                 f"{_g(r,'intervention_sensitivity','mean_rel_change')} |")

    # Reliability — proxy-free
    L += ["", "## Reliability — proxy-free (fully real)", "",
          "| Method | factual RMSE | log10 RMSE | factual dir-acc | conf ECE |",
          "|---|---|---|---|---|"]
    for name, r in results["methods"].items():
        L.append(f"| {name} | {_g(r,'factual_rmse','rmse')} | "
                 f"{_g(r,'factual_rmse_log10','rmse_log10')} | "
                 f"{_g(r,'factual_direction_acc','acc')} | {_g(r,'confidence_ece','ece')} |")

    # Magnitude — vs proxy (secondary)
    L += ["", "## Magnitude — vs k-NN proxy (AGREEMENT-WITH-MATCHER, not true PEHE)", "",
          "| Method | proxy-PEHE | CF dir-acc | policy value | Δ vs observed | %treat |",
          "|---|---|---|---|---|---|"]
    for name, r in results["methods"].items():
        L.append(f"| {name} | {_g(r,'proxy_pehe','pehe')} | "
                 f"{_g(r,'cf_direction_acc_vs_proxy','acc')} | "
                 f"{_g(r,'policy_value','policy_value')} | "
                 f"{_g(r,'policy_value','improvement_vs_observed')} | "
                 f"{_g(r,'policy_value','frac_recommend_treat')} |")

    L += ["", "## Caveats (read before interpreting)", "",
          "1. **proxy-PEHE is agreement-with-a-matcher, not true-effect error.** Real data has "
          "no observed Y(1)−Y(0); the proxy is itself a k-NN matching estimator, so the "
          "`baseline_matched_nn` row scores ~0 *by construction* (it IS the label) and is a "
          "ceiling, not a competitor. The T-/S-learner rows are independent of the label.",
          "2. **Policy value is a surrogate-target metric, not clinical benefit.** PCI mechanically "
          "raises troponin and can raise creatinine, and mortality is unavailable in this data "
          "subset, so 'improving' the lab does not equal helping the patient.",
          "3. **Ignorability is conditional on available covariates.** Age and sex (classic PCI "
          "confounders) are absent from this dataset; the sodium negative control and post-match "
          "SMD are the residual-confounding diagnostics. A full-MIMIC-IV track (mortality + "
          "demographics + RCT anchor) is the planned follow-on that resolves this.", ""]
    (OUTPUTS / "TASKC_RESULTS.md").write_text("\n".join(L))


if __name__ == "__main__":
    sys.exit(main())
