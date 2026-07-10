#!/usr/bin/env python3
"""
build_equipoise.py — select the patients who could HONESTLY have received any of the three
strategies (medical vs PCI vs CABG). Only these belong in the counterfactual training set,
because only for them is the multi-way "what-if" identifiable.

Method: cross-fitted 3-way propensity π(modality | baseline state); keep patients in the
common-support / equipoise region — those with a non-trivial probability of EACH arm
(min over the three arm-probs ≥ THRESH). Patients who were only ever going one way
(e.g. clear surgical or clear medical candidates) are excluded.

Output: cad_equipoise.parquet (hadm_id + arm probs + equipoise flag).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from effect_cad import COH, LABS, CONF, SPARSE_LABS

OUT = Path(__file__).resolve().parent / "cad_equipoise.parquet"
THRESH = 0.10          # min probability of EACH arm to count as "could have gotten it"


def main():
    coh = pd.read_parquet(COH)
    conf = list(CONF)
    if LABS.exists():
        labs = pd.read_parquet(LABS)
        for s in SPARSE_LABS:
            if s in labs.columns:
                labs[s + "_msng"] = labs[s].isna().astype(int)
        coh = coh.merge(labs, left_on="hadm_id", right_index=True, how="left")
        conf += list(labs.columns)
    # equipoise question is non-STEMI, all three modalities
    d = coh[(~coh.stemi) & (coh.modality.isin(["medical", "pci", "cabg"]))].copy()
    for c in conf:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d[conf] = d[conf].fillna(d[conf].median())
    X = d[conf].to_numpy("float64")
    arm = d.modality.map({"medical": 0, "pci": 1, "cabg": 2}).to_numpy()
    print(f"[equip] non-STEMI 3-arm cohort: {len(d):,}  "
          f"({dict(d.modality.value_counts())})")

    clf = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=300)
    proba = cross_val_predict(clf, X, arm, cv=StratifiedKFold(5, shuffle=True, random_state=0),
                              method="predict_proba")                 # honest out-of-fold [N,3]
    d["p_medical"], d["p_pci"], d["p_cabg"] = proba[:, 0], proba[:, 1], proba[:, 2]
    d["min_arm_prob"] = proba.min(1)
    d["equipoise"] = (d.min_arm_prob >= THRESH).astype(int)

    eq = d[d.equipoise == 1]
    print(f"[equip] EQUIPOISE (min arm-prob ≥ {THRESH}): {len(eq):,}/{len(d):,} "
          f"({100*len(eq)/len(d):.0f}%)")
    print(f"[equip]   by modality: {dict(eq.modality.value_counts())}")
    print(f"[equip]   excluded (only-ever-one-way): {len(d)-len(eq):,}")
    # how many are reachable in the hourly ICU substrate
    d[["hadm_id", "subject_id", "modality", "presentation", "p_medical", "p_pci", "p_cabg",
       "min_arm_prob", "equipoise"]].to_parquet(OUT)
    print(f"[equip] saved -> {OUT.name}")


if __name__ == "__main__":
    main()
