#!/usr/bin/env python3
"""
matched_cad.py — build counterfactual TWINS by matching, and use them as the training
signal for the counterfactual simulation.

Idea (user's): for each patient, find a very similar patient who got the OTHER treatment;
that twin's observed outcome is the proxy for the road this patient didn't take. Averaged
over close matches, this gives each patient a proxy for BOTH potential outcomes -> a
per-patient counterfactual and a supervised target for the engine.

Done right:
  - match INSIDE the overlap/equipoise region (propensity ∈ [lo,hi]) — where similar
    patients genuinely diverged by clinician preference, not a hidden anatomical reason;
  - match on the propensity score (logit) with a CALIPER, k nearest opposite-arm neighbors;
  - report covariate balance (standardized mean differences) before vs after matching —
    the honest check that the twins really are similar;
  - VALIDATE the matched effect against the RCTs (stable≈null / NSTEMI-ACS=benefit), the
    same gold standard used for the doubly-robust estimate;
  - save the matched twin pairs + per-patient effect proxy as the CF training set.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from cate_cad import load
from effect_cad import crossfit

OUT = Path(__file__).resolve().parent / "cad_matched.parquet"
K = 5                    # nearest opposite-arm twins to average
PS_LO, PS_HI = 0.1, 0.9  # overlap region for matching


def smd(Xt, Xc):
    """Mean absolute standardized mean difference across covariates."""
    sd = np.sqrt((Xt.var(0) + Xc.var(0)) / 2) + 1e-8
    return np.mean(np.abs(Xt.mean(0) - Xc.mean(0)) / sd)


def main():
    ns, conf = load()
    X = ns[conf].to_numpy("float64")
    a = (ns.modality.values == "pci").astype(int)
    y = ns.death_1y.values.astype(int)
    pres = ns.presentation.values
    print(f"[match] non-STEMI CAD medical-vs-PCI | n={len(y):,}")

    e, _, _ = crossfit(X, a, y)
    logit = np.log(np.clip(e, 1e-4, 1 - 1e-4) / (1 - np.clip(e, 1e-4, 1 - 1e-4)))
    caliper = 0.2 * logit.std()

    ov = (e >= PS_LO) & (e <= PS_HI)                     # match only inside overlap
    print(f"[match] overlap region: {ov.sum():,}/{len(y):,} patients (propensity ∈ [{PS_LO},{PS_HI}])")
    idx = np.where(ov)[0]
    t_idx = idx[a[idx] == 1]; c_idx = idx[a[idx] == 0]

    # nearest opposite-arm twins on the propensity logit, with caliper
    nn_c = NearestNeighbors(n_neighbors=K).fit(logit[c_idx].reshape(-1, 1))
    nn_t = NearestNeighbors(n_neighbors=K).fit(logit[t_idx].reshape(-1, 1))

    tau = np.full(len(y), np.nan); ycf = np.full(len(y), np.nan); matched = np.zeros(len(y), bool)
    # treated -> nearest controls
    d, nb = nn_c.kneighbors(logit[t_idx].reshape(-1, 1))
    for r, i in enumerate(t_idx):
        if d[r, 0] <= caliper:
            ycf[i] = y[c_idx[nb[r]]].mean(); tau[i] = y[i] - ycf[i]; matched[i] = True   # PCI − medical
    # control -> nearest treated
    d, nb = nn_t.kneighbors(logit[c_idx].reshape(-1, 1))
    for r, i in enumerate(c_idx):
        if d[r, 0] <= caliper:
            ycf[i] = y[t_idx[nb[r]]].mean(); tau[i] = ycf[i] - y[i]; matched[i] = True   # PCI − medical
    print(f"[match] matched within caliper ({caliper:.3f}): {matched.sum():,} patients "
          f"(k={K} twins each)")

    # covariate balance before vs after matching
    before = smd(X[a == 1], X[a == 0])
    mt, mc = matched & (a == 1), matched & (a == 0)
    after = smd(X[mt], X[mc])
    print(f"[match] covariate balance (mean |SMD|): before {before:.3f} -> after {after:.3f}  "
          f"({'improved' if after < before else 'worse'}; <0.1 = well balanced)")

    # validation: matched effect vs the RCTs, stratified by presentation
    pp = lambda x: f"{100*x:+.1f} pp"
    print("\n[match] matched twin effect (PCI − medical, 1-yr mortality) vs RCT truth:")
    for lab, m, tgt in [("ALL matched", matched, "mixed"),
                        ("STABLE CAD", matched & (pres == "stable_chronic"), "≈ null (ISCHEMIA)"),
                        ("NSTEMI/ACS", matched & np.isin(pres, ["nstemi", "unstable_angina"]), "benefit (FRISC/TIMACS)")]:
        t = tau[m]
        se = t.std(ddof=1) / np.sqrt(len(t))
        print(f"  {lab:<12} n={int(m.sum()):>6,}  ATE {pp(t.mean())} [{pp(t.mean()-1.96*se)}, {pp(t.mean()+1.96*se)}]"
              f"   RCT: {tgt}")

    # save the counterfactual training set (factual + twin-proxy counterfactual)
    out = ns.loc[matched, ["hadm_id", "subject_id", "modality", "presentation", "death_1y"]].copy()
    out["y_factual"] = y[matched]
    out["y_counterfactual_proxy"] = ycf[matched]
    out["tau_pci_minus_medical"] = tau[matched]
    out.to_parquet(OUT)
    print(f"\n[match] saved counterfactual training set -> {OUT.name} ({matched.sum():,} twin-matched patients)")
    print("[match] each row has factual + twin-proxy counterfactual outcome = supervised CF target.")


if __name__ == "__main__":
    main()
