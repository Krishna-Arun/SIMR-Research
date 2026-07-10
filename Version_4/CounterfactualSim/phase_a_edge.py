#!/usr/bin/env python3
"""
phase_a_edge.py — does a usable EDGE (equipoise / overlap) population exist?

The mission is to answer counterfactuals for patients ON THE EDGE — where
clinicians genuinely disagree, which is exactly where treatment assignment is
non-deterministic and the effect is identifiable. This script measures, per
arm-pair, how big that edge population actually is on the 471-patient cohort.

Method (honest, so overfitting can't fabricate "no overlap"):
  standardize → PCA(k) → L2-regularized logistic, CROSS-FITTED (out-of-fold
  propensities via 5-fold cross_val_predict). We also print the in-sample
  (overfit) propensity AUC to show how badly the naive fit exaggerates
  separability — the trap that made the earlier CE=0.004 look deterministic.

Edge metrics per pair:
  - honest cross-fitted AUC  (high  → arms separable → little overlap)
  - # patients with propensity ∈ [0.25, 0.75]  (the equipoise band = the edge)
  - Li–Morgan–Zaslavsky overlap weights w = e(1-e); their Kish ESS = the
    effective size of the overlap population you could actually estimate on.

Verdict gate: an arm-pair is "alive" if it has a non-trivial edge population
(say ≥ 30 patients in equipoise with ESS ≥ 20). Otherwise the treat-type
question is dead for that pair and Phase B (timing/dose reframe) is required.
"""
from __future__ import annotations

import pickle
from itertools import combinations
from pathlib import Path

import numpy as np
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
SEQ_PKL = HERE / "wm_sequences.pkl"
EDGE_LO, EDGE_HI = 0.25, 0.75
PCA_K = 20
C_REG = 0.5


def kish_ess(w: np.ndarray) -> float:
    """Effective sample size of a weight vector (Kish): (Σw)² / Σw²."""
    w = np.asarray(w, dtype=float)
    return float(w.sum() ** 2 / np.clip((w ** 2).sum(), 1e-12, None))


def pair_edge(Z, y):
    """Return honest & overfit AUC, propensities, edge count, overlap ESS for a pair."""
    n = len(y)
    k = min(PCA_K, n - 2, Z.shape[1])
    pipe = make_pipeline(StandardScaler(), PCA(n_components=k),
                         LogisticRegression(C=C_REG, max_iter=2000))
    cv = StratifiedKFold(5, shuffle=True, random_state=0)
    e_hon = cross_val_predict(pipe, Z, y, cv=cv, method="predict_proba")[:, 1]  # out-of-fold
    pipe.fit(Z, y)
    e_over = pipe.predict_proba(Z)[:, 1]                                        # in-sample (overfit)

    def auc(scores):
        pos, neg = scores[y == 1], scores[y == 0]
        if len(pos) == 0 or len(neg) == 0:
            return 0.5
        # Mann–Whitney U
        alls = np.concatenate([pos, neg]); order = alls.argsort()
        ranks = np.empty(len(alls)); ranks[order] = np.arange(1, len(alls) + 1)
        return (ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))

    edge = (e_hon >= EDGE_LO) & (e_hon <= EDGE_HI)
    w = e_hon * (1 - e_hon)                                                     # overlap weights
    return {"n": n, "auc_honest": auc(e_hon), "auc_overfit": auc(e_over),
            "edge_count": int(edge.sum()), "edge_ess": kish_ess(w),
            "on_support_frac": float(((e_hon >= 0.1) & (e_hon <= 0.9)).mean())}


if __name__ == "__main__":
    sub = pickle.load(open(SEQ_PKL, "rb"))
    PRE = sub["grid"]["PRE"]
    Z = sub["Z"][:, PRE].astype("float64")            # anchor latent per patient
    arm = sub["ARM"].astype("int64")
    names = sub["schema"]["arm_classes"]
    valid = arm >= 0
    Z, arm = Z[valid], arm[valid]
    counts = {k: int((arm == k).sum()) for k in range(len(names))}
    print(f"[phase A] {len(Z)} patients | arms " +
          ", ".join(f"{names[k]}={counts[k]}" for k in counts))
    print(f"[phase A] honest propensity = PCA({PCA_K}) + L2-logistic(C={C_REG}), 5-fold cross-fit")
    print(f"          edge band = propensity ∈ [{EDGE_LO}, {EDGE_HI}]\n")

    print(f"{'arm pair':<26} {'n':>4} {'AUC(honest)':>11} {'AUC(overfit)':>12} "
          f"{'edge n':>7} {'edge ESS':>9} {'on-supp%':>9}  verdict")
    print("-" * 100)
    alive = []
    for i, j in combinations(range(len(names)), 2):
        m = (arm == i) | (arm == j)
        y = (arm[m] == j).astype("int64")
        r = pair_edge(Z[m], y)
        ok = r["edge_count"] >= 30 and r["edge_ess"] >= 20
        alive.append(ok)
        print(f"{names[i]+' vs '+names[j]:<26} {r['n']:>4} {r['auc_honest']:>11.3f} "
              f"{r['auc_overfit']:>12.3f} {r['edge_count']:>7} {r['edge_ess']:>9.1f} "
              f"{100*r['on_support_frac']:>8.1f}%  {'ALIVE' if ok else 'dead'}")
    print("-" * 100)
    print(f"[phase A] VERDICT: {'≥1 arm-pair has a usable edge population' if any(alive) else 'NO arm-pair has a usable edge — treat-type CF is dead, Phase B (timing/dose) required'}")
    print("[phase A] note: AUC(overfit) >> AUC(honest) is the small-n/high-dim trap —")
    print("          the in-sample propensity fabricates separability (this is what CE=0.004 was).")
