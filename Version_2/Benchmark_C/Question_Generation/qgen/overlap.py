"""Benchmark C overlap / matching — generate baseline-overlapping patient pairs with DIFFERENT
ICU procedures, so identifying which procedure produced a shown post-state is non-trivial.

Method (reuses the CARDIAC overlap_diagnostic + matched_pairs patterns):
  covariates  = standardized latest pre-procedure core labs (median-imputed) + comorbidity flags + age
  propensity  = LogisticRegression P(procedure = X | covariates) for a procedure pair (X, Y)
  match       = 1:1 nearest-neighbour on propensity within a caliper, with a control-reuse cap
  support     = keep pairs in the common-support region
  quality     = standardized mean difference (SMD) per covariate (small = good overlap) + assignability AUC (~0.5 = good)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler


def _standardize(X: np.ndarray) -> np.ndarray:
    return np.nan_to_num(StandardScaler().fit_transform(np.nan_to_num(X, nan=0.0)))


def smd(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Standardized mean difference per column between two groups."""
    ma, mb = a.mean(0), b.mean(0)
    sd = np.sqrt((a.var(0) + b.var(0)) / 2) + 1e-9
    return np.abs(ma - mb) / sd


def match_pair(df: pd.DataFrame, cov_cols: list[str], procA: str, procB: str, cfg: dict):
    """Match X(procA) patients to Y(procB) patients on propensity. Returns (pairs_df, diag)."""
    sub = df[df["proc_label"].isin([procA, procB])].copy()
    if sub["proc_label"].nunique() < 2:
        return None, None
    y = (sub["proc_label"] == procA).astype(int).to_numpy()
    if y.sum() < 20 or (len(y) - y.sum()) < 20:
        return None, None
    X = _standardize(sub[cov_cols].to_numpy())
    lr = LogisticRegression(max_iter=200, C=1.0)
    lr.fit(X, y)
    p = lr.predict_proba(X)[:, 1]
    try:
        auc = float(roc_auc_score(y, p))
    except Exception:
        auc = float("nan")

    sub = sub.assign(prop=p, treat=y)
    cal = float(cfg["cohort"]["caliper"]) * np.std(p)
    treated = sub[sub["treat"] == 1].sort_values("prop")
    controls = sub[sub["treat"] == 0].copy()
    reuse_cap = int(cfg["cohort"].get("max_control_reuse", 2))
    used = {}
    pairs = []
    cvals = controls["prop"].to_numpy()
    cidx = controls.index.to_numpy()
    for t in treated.itertuples():
        d = np.abs(cvals - t.prop)
        order = np.argsort(d)
        for j in order:
            if d[j] > cal:
                break
            ci = cidx[j]
            if used.get(ci, 0) >= reuse_cap:
                continue
            used[ci] = used.get(ci, 0) + 1
            c = controls.loc[ci]
            pairs.append({"procA": procA, "procB": procB,
                          "hadmA": int(t.hadm_id), "proc_uidA": t.proc_uid, "pA": float(t.prop),
                          "hadmB": int(c["hadm_id"]), "proc_uidB": c["proc_uid"], "pB": float(c["prop"])})
            break
    if not pairs:
        return None, {"procA": procA, "procB": procB, "auc_prematch": round(auc, 3), "n_pairs": 0}

    pdf = pd.DataFrame(pairs)
    a = sub.loc[sub["proc_uid"].isin(pdf["proc_uidA"]), cov_cols].to_numpy()
    b = sub.loc[sub["proc_uid"].isin(pdf["proc_uidB"]), cov_cols].to_numpy()
    smds = smd(a, b)
    # POST-match assignability AUC: refit propensity on the matched subset; ~0.5 == well balanced
    post_auc = float("nan")
    try:
        Xm = _standardize(np.vstack([a, b]))
        ym = np.r_[np.ones(len(a)), np.zeros(len(b))]
        post_auc = float(roc_auc_score(ym, LogisticRegression(max_iter=200).fit(Xm, ym).predict_proba(Xm)[:, 1]))
    except Exception:
        pass
    diag = {"procA": procA, "procB": procB, "auc_prematch": round(auc, 3),
            "auc_postmatch": round(post_auc, 3), "n_pairs": len(pdf),
            "max_smd": round(float(np.nanmax(smds)), 3), "mean_smd": round(float(np.nanmean(smds)), 3)}
    return pdf, diag


# Map each procedure to a physiologic SYSTEM. C only pairs ACROSS systems (e.g. renal dialysis vs a
# respiratory procedure) so the two interventions have DISTINCT lab signatures and the "which procedure
# produced this post-state" task is well-posed — not e.g. Extubation vs Ventilation (same system).
_SYSTEM = {"dialysis": "renal", "crrt": "renal", "cvvhd": "renal", "cvvhdf": "renal", "scuf": "renal",
           "peritoneal": "renal", "ultrafiltration": "renal",
           "ventilation": "respiratory", "intubation": "respiratory", "extubation": "respiratory",
           "tracheostomy": "respiratory"}


def _system(label: str) -> str:
    l = str(label).lower()
    for k, v in _SYSTEM.items():
        if k in l:
            return v
    return "other"


def build_pairs(df: pd.DataFrame, cov_cols: list[str], cfg: dict):
    """Match CROSS-SYSTEM procedure pairs (distinct lab signatures); keep sets passing the overlap gate."""
    counts = df["proc_label"].value_counts()
    top = counts[counts >= int(cfg["cohort"]["min_procedure_count"])].head(int(cfg["cohort"]["top_k_procedures"]))
    procs = list(top.index)
    print(f"top procedures eligible for pairing ({len(procs)}):")
    print(top.to_string())
    max_smd = float(cfg["cohort"]["max_smd"])
    all_pairs, diags = [], []
    for i in range(len(procs)):
        for j in range(i + 1, len(procs)):
            sa, sb = _system(procs[i]), _system(procs[j])
            if sa == "other" or sb == "other" or sa == sb:
                continue                          # only cross-system, distinguishable pairs
            pdf, diag = match_pair(df, cov_cols, procs[i], procs[j], cfg)
            if diag:
                diag["systems"] = f"{sa} vs {sb}"
                diags.append(diag)
            if pdf is not None and diag and diag["max_smd"] <= max_smd:
                all_pairs.append(pdf)
                print(f"  PAIR {procs[i][:22]}({sa}) vs {procs[j][:22]}({sb}): n={diag['n_pairs']} "
                      f"AUC_pre={diag['auc_prematch']} AUC_post={diag['auc_postmatch']} maxSMD={diag['max_smd']}")
    pairs = pd.concat(all_pairs, ignore_index=True) if all_pairs else pd.DataFrame()
    return pairs, diags
