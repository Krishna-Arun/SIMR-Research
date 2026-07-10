#!/usr/bin/env python3
"""
cate_cad.py — individual treatment-effect prediction (the "predict for the edge patient"
goal), for PCI vs medical therapy, with honest validation.

Method: DR-learner (Kennedy 2020). Using the cross-fitted nuisances from effect_cad, form
the doubly-robust pseudo-outcome per patient
    ψ_i = μ1(X_i) − μ0(X_i) + a_i(y_i−μ1)/e_i − (1−a_i)(y_i−μ0)/(1−e_i)
(E[ψ|X]=CATE), then regress ψ on X (cross-fitted) to get τ̂(x) = predicted PCI-vs-medical
1-yr mortality effect for THIS patient.

Validation without individual ground truth (you never see both outcomes for one patient):
  1. CALIBRATION to the RCT anchors — mean τ̂ in stable CAD ≈ ISCHEMIA null, in NSTEMI/ACS
     ≈ the early-invasive benefit.
  2. SORTED-GROUP test (Chernozhukov et al. GATES) — rank patients by τ̂, then check the
     *unbiased* DR-score ψ per τ̂-quintile increases monotonically: patients predicted to
     benefit more actually do (on held-out folds). This is how you show the model captures
     REAL heterogeneity, not noise.
  3. Clinical profile of the highest- vs lowest-benefit patients (face validity).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import KFold

from effect_cad import COH, LABS, CONF, SPARSE_LABS, crossfit

OUT = Path(__file__).resolve().parent / "cad_cate.parquet"


def load():
    coh = pd.read_parquet(COH)
    conf = list(CONF)
    if LABS.exists():
        labs = pd.read_parquet(LABS)
        for s in SPARSE_LABS:
            if s in labs.columns:
                labs[s + "_msng"] = labs[s].isna().astype(int)
        coh = coh.merge(labs, left_on="hadm_id", right_index=True, how="left")
        conf += list(labs.columns)
    ns = coh[(~coh.stemi) & (coh.modality.isin(["medical", "pci"]))].copy()
    # presentation type is a legitimate BASELINE effect-modifier (known at decision time,
    # not a mediator) — give the model the strongest modifier it was previously blind to
    ns["pres_nstemi"] = (ns.presentation == "nstemi").astype(int)
    ns["pres_ua"] = (ns.presentation == "unstable_angina").astype(int)
    conf = conf + ["pres_nstemi", "pres_ua"]
    for c in conf:
        ns[c] = pd.to_numeric(ns[c], errors="coerce")
    ns = ns.dropna(subset=["death_1y"])
    ns[conf] = ns[conf].fillna(ns[conf].median())
    return ns, conf


def main():
    ns, conf = load()
    X = ns[conf].to_numpy("float64")
    a = (ns.modality.values == "pci").astype(int)
    y = ns.death_1y.values.astype(int)
    pres = ns.presentation.values
    print(f"[cate] non-STEMI CAD medical-vs-PCI | n={len(y):,}, {len(conf)} confounders")

    # 1) cross-fitted nuisances -> DR pseudo-outcome
    e, mu0, mu1 = crossfit(X, a, y)
    psi = (mu1 - mu0) + a * (y - mu1) / e - (1 - a) * (y - mu0) / (1 - e)

    # 2) cross-fitted second stage: out-of-fold τ̂(x)
    tau = np.zeros(len(y))
    for tr, te in KFold(5, shuffle=True, random_state=1).split(X):
        m = HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=400).fit(X[tr], psi[tr])
        tau[te] = m.predict(X[te])
    ns["cate"] = tau
    pp = lambda x: f"{100*x:+.1f} pp"

    # ---- validation 1: calibration to RCT anchors
    print("\n[cate] CALIBRATION — mean predicted τ̂ vs the validated (RCT-anchored) ATEs:")
    for lab, m, tgt in [("STABLE CAD", pres == "stable_chronic", "≈ null (ISCHEMIA)"),
                        ("NSTEMI/ACS", np.isin(pres, ["nstemi", "unstable_angina"]), "benefit (FRISC/TIMACS)")]:
        print(f"  {lab:<12} mean τ̂ {pp(tau[m].mean()):>8}   (unbiased DR-score {pp(psi[m].mean()):>8})   RCT: {tgt}")

    # ---- validation 2: sorted-group test (does predicted benefit track real benefit?)
    print("\n[cate] SORTED-GROUP test — τ̂ quintile vs unbiased DR-score ψ (held-out):")
    q = pd.qcut(tau, 5, labels=False, duplicates="drop")
    print(f"  {'quintile':<10}{'mean τ̂':>10}{'mean ψ (real)':>16}{'n':>8}")
    for k in range(5):
        mk = q == k
        print(f"  Q{k+1:<9}{pp(tau[mk].mean()):>10}{pp(psi[mk].mean()):>16}{int(mk.sum()):>8}")
    top, bot = q == 4, q == 0
    diff = psi[bot].mean() - psi[top].mean()             # benefit gap (more negative = bigger benefit in Q5)
    se = np.sqrt(psi[top].var(ddof=1)/top.sum() + psi[bot].var(ddof=1)/bot.sum())
    print(f"  Q1−Q5 DR-score gap {pp(diff)}  ({diff/se:+.1f} σ) — heterogeneity is real if |σ| ≳ 2")

    # ---- validation 3: clinical profile of high- vs low-benefit
    hi, lo = tau <= np.quantile(tau, 0.2), tau >= np.quantile(tau, 0.8)  # most vs least benefit
    prof = ["anchor_age", "diabetes", "ckd", "hf", "priormi"]
    print("\n[cate] profile — most-benefit (Q1) vs least-benefit (Q5):")
    print(f"  {'feature':<12}{'most-benefit':>14}{'least-benefit':>15}")
    for f in prof:
        print(f"  {f:<12}{ns[f][hi].mean():>14.2f}{ns[f][lo].mean():>15.2f}")
    acs = np.isin(pres, ["nstemi", "unstable_angina"])
    print(f"  {'%ACS':<12}{100*acs[hi].mean():>13.0f}%{100*acs[lo].mean():>14.0f}%")

    ns[["hadm_id", "subject_id", "modality", "presentation", "death_1y", "cate"]].to_parquet(OUT)
    print(f"\n[cate] saved per-patient CATE -> {OUT.name} ({len(ns):,} patients)")


if __name__ == "__main__":
    main()
