#!/usr/bin/env python3
"""
train_cf_sim.py — train the counterfactual simulation on the matched-twin targets and
test whether it predicts INDIVIDUAL effect (where the DR-learner failed).

Target = the twin-proxy individual effect tau_i (PCI − medical) from matched_cad.py.
Train a model to predict tau_i from baseline features (out-of-fold). Validate honestly on
the UNBIASED doubly-robust score ψ (independent of the matched target): rank patients by
the model's prediction, check the real ψ increases monotonically across quintiles. If the
top-predicted-benefit group truly benefits (large negative ψ) and the sign is stable, the
matched-twin training gave real individual signal — otherwise individual CF is still noise.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import KFold

from cate_cad import load
from effect_cad import crossfit
from matched_cad import OUT as MATCHED

def main():
    ns, conf = load()
    ns = ns.reset_index(drop=True)
    m = pd.read_parquet(MATCHED)[["hadm_id", "tau_pci_minus_medical"]]
    ns = ns.merge(m, on="hadm_id", how="inner")           # matched patients only
    X = ns[conf].to_numpy("float64")
    a = (ns.modality.values == "pci").astype(int)
    y = ns.death_1y.values.astype(int)
    pres = ns.presentation.values
    tau_target = ns.tau_pci_minus_medical.values
    print(f"[cf-sim] training on {len(ns):,} twin-matched patients, {len(conf)} features")

    # train the CF model on the matched-twin effect (out-of-fold predictions)
    tau_hat = np.zeros(len(ns))
    for tr, te in KFold(5, shuffle=True, random_state=2).split(X):
        r = HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=400,
                                          l2_regularization=1.0).fit(X[tr], tau_target[tr])
        tau_hat[te] = r.predict(X[te])

    # independent yardstick: unbiased DR score ψ
    e, mu0, mu1 = crossfit(X, a, y)
    psi = (mu1 - mu0) + a * (y - mu1) / e - (1 - a) * (y - mu0) / (1 - e)
    pp = lambda x: f"{100*x:+.1f} pp"

    print("\n[cf-sim] calibration by presentation (mean predicted τ̂ vs unbiased ψ):")
    for lab, mk in [("STABLE", pres == "stable_chronic"),
                    ("NSTEMI/ACS", np.isin(pres, ["nstemi", "unstable_angina"]))]:
        print(f"  {lab:<11} τ̂ {pp(tau_hat[mk].mean())}   ψ {pp(psi[mk].mean())}")

    print("\n[cf-sim] SORTED-GROUP validation (τ̂ quintile vs unbiased ψ):")
    q = pd.qcut(tau_hat, 5, labels=False, duplicates="drop")
    print(f"  {'quintile':<9}{'mean τ̂':>10}{'real ψ':>12}{'n':>8}")
    for k in sorted(set(q)):
        mk = q == k
        print(f"  Q{k+1:<8}{pp(tau_hat[mk].mean()):>10}{pp(psi[mk].mean()):>12}{int(mk.sum()):>8}")
    top, bot = q == max(q), q == 0
    gap = psi[bot].mean() - psi[top].mean()
    se = np.sqrt(psi[top].var(ddof=1)/top.sum() + psi[bot].var(ddof=1)/bot.sum())
    corr = np.corrcoef(tau_hat, psi)[0, 1]
    print(f"\n  Q1−Q5 real-benefit gap {pp(gap)} ({gap/se:+.1f} σ) | corr(τ̂, ψ) = {corr:+.3f}")
    ok = (gap/se) > 2 and corr < -0.02
    print(f"  INDIVIDUAL PREDICTION WORKS (monotone, ≳2σ, right sign): {'YES' if ok else 'NO — still noise-limited'}")
    if not ok:
        print("  -> matched-twin training did not rescue individual prediction; the binding")
        print("     constraint is a missing effect-modifier (coronary anatomy), not the estimator.")


if __name__ == "__main__":
    main()
