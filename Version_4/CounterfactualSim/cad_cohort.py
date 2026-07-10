#!/usr/bin/env python3
"""
cad_cohort.py — build the CAD multi-modality cohort and run the honest overlap check.

Target question: medical therapy vs PCI (the ISCHEMIA/COURAGE equipoise), on the
cardiac-disease extension. Key filter: EXCLUDE STEMI — an acute ST-elevation MI is a
near-mandatory primary-PCI indication (deterministic assignment, no equipoise), exactly
the trap that killed the ventilation arm. The equipoise lives in chronic IHD + NSTEMI +
unstable/stable angina, where the heart team genuinely deliberates.

Steps:
  1. CAD admissions (ICD-9 410-414 / ICD-10 I20-I25).
  2. Modality per admission: CABG (36.1x/021), PCI (0066/3606/3607/027), else medical.
  3. STEMI flag; equipoise cohort = CAD \ STEMI.
  4. Baseline covariates = first-lab panel (top-N labels) per admission.
  5. Honest cross-fitted propensity (PCA+L2-logistic) medical-vs-PCI; report AUC
     (honest vs overfit), equipoise-band count, and Li overlap-weight ESS.
  Contrast the FULL CAD cohort vs the STEMI-excluded cohort to show the filter's effect.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

EXT = Path("/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/mimic-iv-ext-cardiac-disease-1.0.0")
N_LABS = 25
EDGE_LO, EDGE_HI = 0.25, 0.75


def norm(s):
    return str(s).replace(".", "").strip().upper()


def hnorm(h):
    """Normalize hadm_id: labs store it as float ('28273060.0'), dx/pr as clean strings."""
    return str(h).split(".")[0].strip()


def is_cad(c):
    return c[:3] in {"410", "411", "412", "413", "414", "I20", "I21", "I22", "I23", "I24", "I25"}


def is_cabg(c):
    return c[:3] == "361" or c[:3] == "021"


def is_pci(c):
    return c in {"0066", "3606", "3607"} or c[:3] == "027"


def is_stemi(c):
    # ICD-10 I21.0-I21.3 = STEMI (I21.4 = NSTEMI); ICD-9 410.0-410.6/410.8 = transmural (410.7 = subendocardial/NSTEMI)
    if c[:4] in {"I210", "I211", "I212", "I213"}:
        return True
    if c[:3] == "410" and len(c) >= 4 and c[3] in set("0123456 8"):
        return c[3] != "7"
    return False


def kish_ess(w):
    w = np.asarray(w, float)
    return float(w.sum() ** 2 / np.clip((w ** 2).sum(), 1e-12, None))


# comorbidity confounders (ICD-10 primary, ICD-9 fallback) — clinically the drivers of
# the medical-vs-PCI decision, so they belong in the propensity
COMORB = {
    "diabetes": lambda c: c[:3] in {"E10", "E11", "E12", "E13", "E14"} or c[:3] == "250",
    "ckd":      lambda c: c[:3] == "N18" or c[:3] == "585",
    "hf":       lambda c: c[:3] == "I50" or c[:3] == "428",
    "htn":      lambda c: c[:3] in {"I10", "I11", "I12", "I13", "I15"} or c[:3] in {"401", "402", "403", "404", "405"},
    "priormi":  lambda c: c[:4] == "I252" or c[:3] == "412",
    "pvd":      lambda c: c[:3] == "I73" or c[:3] == "443",
    "copd":     lambda c: c[:3] == "J44" or c[:3] == "496",
    "stroke":   lambda c: c[:3] in {"I63", "I64"} or c[:3] == "434",
    "lipid":    lambda c: c[:3] == "E78" or c[:3] == "272",
    "afib":     lambda c: c[:3] == "I48" or c[:5] == "42731",
    "anemia":   lambda c: c[:3] == "D64" or c[:3] == "285",
}


def build_comorbid(dxt):
    """Per-hadm comorbidity flags + burden + presentation, from the full-code diagnoses."""
    rows = {}
    for h, g in dxt.groupby("hadm_id"):
        codes = g.c.tolist()
        r = {k: int(any(fn(c) for c in codes)) for k, fn in COMORB.items()}
        r["n_dx"] = len(codes)
        r["pres_nstemi"] = int(any(c[:4] == "I214" for c in codes))
        r["pres_chronic_ihd"] = int(any(c[:3] in {"I25", "414"} for c in codes))
        rows[h] = r
    return pd.DataFrame.from_dict(rows, orient="index")


def overlap_report(X, y, label):
    k = min(20, X.shape[0] // 6, X.shape[1])
    pipe = make_pipeline(StandardScaler(), PCA(n_components=k),
                         LogisticRegression(C=0.5, max_iter=2000))
    cv = StratifiedKFold(5, shuffle=True, random_state=0)
    e = cross_val_predict(pipe, X, y, cv=cv, method="predict_proba")[:, 1]
    pipe.fit(X, y)
    e_over = pipe.predict_proba(X)[:, 1]

    def auc(s):
        pos, neg = s[y == 1], s[y == 0]
        a = np.concatenate([pos, neg]); r = np.empty(len(a)); r[a.argsort()] = np.arange(1, len(a) + 1)
        return (r[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))

    edge = int(((e >= EDGE_LO) & (e <= EDGE_HI)).sum())
    w = e * (1 - e)
    print(f"  {label:<28} n={len(y):>4} (med {int((y==0).sum())}/PCI {int((y==1).sum())})  "
          f"AUC hon {auc(e):.3f} / overfit {auc(e_over):.3f}  edge {edge}  ESS {kish_ess(w):.0f}  "
          f"on-supp {100*((e>=0.1)&(e<=0.9)).mean():.0f}%")


def main():
    dx = pd.read_csv(EXT / "heart_diagnoses_all.csv", dtype=str)
    pr = pd.read_csv(EXT / "heart_procedures.csv", dtype=str)
    dxt = pd.read_csv(EXT / "heart_diagnoses_all_true.csv", dtype=str)  # FULL ICD-10 codes
    dx["c"] = dx.icd_code.map(norm); pr["c"] = pr.icd_code.map(norm); dxt["c"] = dxt.icd_code.map(norm)
    for d in (dx, pr, dxt):
        d["hadm_id"] = d.hadm_id.map(hnorm)

    cad_hadm = set(dx[dx.c.map(is_cad)].hadm_id)
    cabg_hadm = set(pr[pr.c.map(is_cabg)].hadm_id)
    pci_hadm = set(pr[pr.c.map(is_pci)].hadm_id)
    stemi_hadm = set(dxt[dxt.c.map(is_stemi)].hadm_id)          # STEMI from full codes

    def modality(h):
        if h in cabg_hadm:
            return "cabg"
        if h in pci_hadm:
            return "pci"
        return "medical"

    cad = pd.DataFrame({"hadm_id": sorted(cad_hadm)})
    cad["modality"] = cad.hadm_id.map(modality)
    cad["stemi"] = cad.hadm_id.isin(stemi_hadm)
    print(f"[cad] {len(cad)} CAD admissions | STEMI {int(cad.stemi.sum())} / non-STEMI {int((~cad.stemi).sum())}")
    print("[cad] modality x STEMI:\n" +
          pd.crosstab(cad.modality, cad.stemi).to_string())

    # baseline covariates: first-lab panel, top-N most frequent labels
    lab = pd.read_csv(EXT / "heart_labevents_first_lab.csv", dtype={"hadm_id": str},
                      usecols=["hadm_id", "label", "valuenum"]).dropna(subset=["valuenum"])
    lab["hadm_id"] = lab.hadm_id.map(hnorm)                     # strip float '.0'
    top = lab.label.value_counts().head(N_LABS).index
    lab = lab[lab.label.isin(top)]
    feat = lab.pivot_table(index="hadm_id", columns="label", values="valuenum", aggfunc="first")
    print(f"[cad] lab-feature matrix: {feat.shape[0]} admissions x {feat.shape[1]} labs")

    def build_xy(sub):
        sub = sub[sub.modality.isin(["medical", "pci"])].copy()
        m = feat.reindex(sub.hadm_id.values)
        keep = m.notna().mean(axis=1) >= 0.5                       # need >=50% labs observed
        m = m[keep.values]; sub = sub[keep.values]
        X = m.fillna(m.median()).to_numpy("float64")
        y = (sub.modality.values == "pci").astype("int64")
        return X, y

    # richer confounders: comorbidities + presentation from full-code diagnoses
    com = build_comorbid(dxt)
    print(f"[cad] comorbidity features: {com.shape[1]} cols over {com.shape[0]} admissions")

    def build_xy_rich(sub):
        sub = sub[sub.modality.isin(["medical", "pci"])].copy()
        m = feat.reindex(sub.hadm_id.values)
        keep = m.notna().mean(axis=1) >= 0.5
        m = m[keep.values]; sub = sub[keep.values]
        lab_x = m.fillna(m.median())
        cm = com.reindex(sub.hadm_id.values).fillna(0)
        X = np.hstack([lab_x.to_numpy("float64"), cm.to_numpy("float64")])
        y = (sub.modality.values == "pci").astype("int64")
        return X, y

    print("\n[cad] OVERLAP CHECK — medical vs PCI (honest 5-fold cross-fit):")
    X, y = build_xy(cad)
    overlap_report(X, y, "FULL CAD, labs only")
    Xs, ys = build_xy(cad[~cad.stemi])
    overlap_report(Xs, ys, "EQUIPOISE (non-STEMI), labs")
    Xr, yr = build_xy_rich(cad[~cad.stemi])
    overlap_report(Xr, yr, "EQUIPOISE + comorbidity")
    print("\n[cad] reading: if AUC stays ~0.7 and the edge population stays large even with")
    print("      richer confounders, the overlap is real (not an artifact of weak covariates).")


if __name__ == "__main__":
    main()
