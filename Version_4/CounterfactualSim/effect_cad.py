#!/usr/bin/env python3
"""
effect_cad.py — real treatment-effect estimate for PCI vs medical therapy on 1-year
mortality, validated against ISCHEMIA / COURAGE (P3, on real data at last).

The money experiment. In the angiographically-evaluated non-STEMI CAD cohort:
  - the NAIVE difference says PCI patients die far less (≈9.6% vs 16.0%) — a huge apparent
    "PCI saves lives" that is CONFOUNDING (medical patients are older/sicker/non-candidates).
  - the landmark RCTs (COURAGE 2007, ISCHEMIA 2020) found NO significant mortality benefit
    of PCI over optimal medical therapy in stable CAD.
So the test is: does deconfounding (cross-fitted IPW / G-computation / doubly-robust AIPW /
overlap-weighted ATO) pull the naive −6-point "benefit" toward the RCT's ~null? If yes, the
pipeline recovers a known randomized truth from observational data — the validation the
synthetic test could not provide.

Estimand: risk difference RD = P(death_1y | do(PCI)) − P(death_1y | do(medical)), in pp.
All nuisances are 5-fold CROSS-FITTED (Neyman-orthogonal); AIPW reports an influence-function CI.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler

COH = Path(__file__).resolve().parent / "cad_cohort_full.parquet"
LABS = Path(__file__).resolve().parent / "cad_labs.parquet"
CONF = ["anchor_age", "female", "n_dx", "diabetes", "ckd", "hf", "htn",
        "priormi", "pvd", "copd", "stroke", "lipid", "afib", "anemia"]
SPARSE_LABS = ["lab_troponin_t", "lab_hba1c", "lab_ldl", "lab_ntprobnp"]  # add missingness flag
CLIP = 0.05


def crossfit(X, a, y, seed=0):
    """5-fold cross-fitted nuisances: propensity e(X), outcome μ0(X), μ1(X)."""
    n = len(y)
    e = np.zeros(n); mu0 = np.zeros(n); mu1 = np.zeros(n)
    kf = StratifiedKFold(5, shuffle=True, random_state=seed)
    for tr, te in kf.split(X, a):
        sc = StandardScaler().fit(X[tr])
        Xtr, Xte = sc.transform(X[tr]), sc.transform(X[te])
        ps = LogisticRegression(C=1.0, max_iter=2000).fit(Xtr, a[tr])
        e[te] = ps.predict_proba(Xte)[:, 1]
        c0 = a[tr] == 0; c1 = a[tr] == 1
        m0 = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05,
                                            max_iter=300).fit(X[tr][c0], y[tr][c0])
        m1 = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05,
                                            max_iter=300).fit(X[tr][c1], y[tr][c1])
        mu0[te] = m0.predict_proba(X[te])[:, 1]
        mu1[te] = m1.predict_proba(X[te])[:, 1]
    return np.clip(e, CLIP, 1 - CLIP), mu0, mu1


def estimators(a, y, e, mu0, mu1):
    n = len(y)
    naive = y[a == 1].mean() - y[a == 0].mean()
    # G-computation (outcome regression)
    gcomp = (mu1 - mu0).mean()
    # stabilized IPW (Hajek)
    w1 = a / e; w0 = (1 - a) / (1 - e)
    ipw = (w1 * y).sum() / w1.sum() - (w0 * y).sum() / w0.sum()
    # doubly-robust AIPW + influence-function CI
    psi = (mu1 - mu0) + a * (y - mu1) / e - (1 - a) * (y - mu0) / (1 - e)
    aipw = psi.mean(); se = psi.std(ddof=1) / np.sqrt(n)
    # overlap-weighted ATE (ATO): treated weight (1-e), control weight e — focuses on the edge
    tw = a * (1 - e); cw = (1 - a) * e
    ato = (tw * y).sum() / tw.sum() - (cw * y).sum() / cw.sum()
    return {"naive": naive, "gcomp": gcomp, "ipw": ipw,
            "aipw": aipw, "aipw_lo": aipw - 1.96 * se, "aipw_hi": aipw + 1.96 * se, "ato": ato}


def main():
    coh = pd.read_parquet(COH)
    conf = list(CONF)
    if LABS.exists():                                    # fold in the baseline lab panel
        labs = pd.read_parquet(LABS)
        for s in SPARSE_LABS:                            # "was it measured?" is itself informative
            if s in labs.columns:
                labs[s + "_msng"] = labs[s].isna().astype(int)
        coh = coh.merge(labs, left_on="hadm_id", right_index=True, how="left")
        conf += [c for c in labs.columns]
        print(f"[effect] confounders enriched with {labs.shape[1]} lab columns")
    ns = coh[(~coh.stemi) & (coh.modality.isin(["medical", "pci"]))].copy()
    for c in conf:
        ns[c] = pd.to_numeric(ns[c], errors="coerce")
    ns = ns.dropna(subset=["death_1y"])
    ns[conf] = ns[conf].fillna(ns[conf].median())
    X = ns[conf].to_numpy("float64")
    a = (ns.modality.values == "pci").astype(int)       # PCI=1, medical=0
    y = ns.death_1y.values.astype(int)
    print(f"[effect] non-STEMI CAD, medical vs PCI | n={len(y):,} "
          f"(PCI {a.sum():,} / medical {(1-a).sum():,})")
    print(f"[effect] raw 1-yr mortality: PCI {y[a==1].mean()*100:.1f}%  medical {y[a==0].mean()*100:.1f}%")

    pp = lambda x: f"{100*x:+.1f} pp"

    def run(mask, label, target):
        Xm, am, ym = X[mask], a[mask], y[mask]
        if am.sum() < 50 or (1 - am).sum() < 50:
            print(f"  {label:<22} n={mask.sum():,} — too few per arm, skipped"); return
        e, mu0, mu1 = crossfit(Xm, am, ym)
        r = estimators(am, ym, e, mu0, mu1)
        incl0 = r["aipw_lo"] <= 0 <= r["aipw_hi"]
        print(f"  {label:<22} n={mask.sum():>6,} (PCI {am.sum():>4}/med {(1-am).sum():>4})  "
              f"raw {pp(r['naive']):>8} -> AIPW {pp(r['aipw']):>8} [{pp(r['aipw_lo'])},{pp(r['aipw_hi'])}]  "
              f"| RCT: {target}  {'✓' if (('null' in target)==incl0) else '≈'}")

    pres = ns.presentation.values
    print("\n[effect] risk difference (PCI − medical), 1-yr mortality, STRATIFIED by presentation:")
    print("         (each stratum vs its OWN trial evidence — stable≈null, ACS=benefit)")
    run(np.ones(len(y), bool), "ALL non-STEMI", "mixed")
    run(pres == "stable_chronic", "STABLE CAD", "null (ISCHEMIA/COURAGE)")
    run(np.isin(pres, ["nstemi", "unstable_angina"]), "NSTEMI/ACS", "benefit (FRISC-II/TIMACS)")
    print("\n[effect] the key test is DIRECTIONAL: does deconfounding make STABLE≈null while")
    print("         NSTEMI/ACS retains a benefit? Recovering BOTH matches the trial landscape.")


if __name__ == "__main__":
    main()
