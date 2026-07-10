#!/usr/bin/env python3
"""
build_cad_cohort_full.py — the REAL CAD multi-modality cohort from full MIMIC-IV v3.1.

Now that the full hosp module is available (2physionet.org/files/mimiciv/3.1), we can
build the cohort at scale WITH outcomes and demographics — the pieces the cardiac
extension lacked.

Per CAD admission we attach:
  - modality       : CABG (021/36.1x) / PCI (0066/3606/3607/027) / medical (neither)
  - STEMI flag     : ICD-10 I21.0-3 / ICD-9 410.0-6,8  (exclude for equipoise)
  - outcomes       : in-hospital death (hospital_expire_flag); 1-year death (dod within
                     365d of admittime); length of stay
  - confounders    : age, gender, comorbidity flags (diabetes/CKD/HF/priorMI/…), n_dx
Then: overlap check (medical vs PCI, non-STEMI) with these confounders, the raw
(confounded) outcome rates per modality, and save cad_cohort_full.parquet for the
effect model.

labevents (2.4G) and prescriptions (578M) are intentionally NOT loaded here — this pass
uses diagnosis/demographic confounders; labs/GDMT get chunk-filtered in a later step.
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

MIMIC = Path("/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/2physionet.org/files/mimiciv/3.1/hosp")
OUT = Path(__file__).resolve().parent / "cad_cohort_full.parquet"

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


def norm(s):
    return str(s).replace(".", "").strip().upper()


def is_cad(c):
    return c[:3] in {"410", "411", "412", "413", "414", "I20", "I21", "I22", "I23", "I24", "I25"}


def is_cabg(c):
    return c[:3] == "361" or c[:3] == "021"


def is_pci(c):
    return c in {"0066", "3606", "3607"} or c[:3] == "027"


def is_stemi(c):
    if c[:4] in {"I210", "I211", "I212", "I213"}:
        return True
    if c[:3] == "410" and len(c) >= 4 and c[3] != "7":
        return True
    return False


def is_angio(c):
    """Coronary angiography / cardiac cath — the 'evaluated for revascularization' gate.
    Restricting to these patients makes 'medical' mean CHOSE medical management, not
    'had a CAD code but was never a revascularization candidate'."""
    return (c in {"3722", "3723", "8853", "8854", "8855", "8856", "8857"}
            or c[:3] == "B21" or c[:4] == "4A02")


def main():
    print("[build] loading full MIMIC-IV hosp tables …")
    pat = pd.read_csv(MIMIC / "patients.csv.gz", usecols=["subject_id", "gender", "anchor_age", "dod"])
    adm = pd.read_csv(MIMIC / "admissions.csv.gz",
                      usecols=["subject_id", "hadm_id", "admittime", "dischtime",
                               "deathtime", "hospital_expire_flag"])
    dxi = pd.read_csv(MIMIC / "diagnoses_icd.csv.gz", dtype={"icd_code": str},
                      usecols=["hadm_id", "icd_code"])
    pri = pd.read_csv(MIMIC / "procedures_icd.csv.gz", dtype={"icd_code": str},
                      usecols=["hadm_id", "icd_code"])
    dxi["c"] = dxi.icd_code.map(norm); pri["c"] = pri.icd_code.map(norm)
    print(f"[build] diagnoses {len(dxi):,} rows | procedures {len(pri):,} | admissions {len(adm):,}")

    cad_hadm = set(dxi.loc[dxi.c.map(is_cad), "hadm_id"])
    cabg_hadm = set(pri.loc[pri.c.map(is_cabg), "hadm_id"])
    pci_hadm = set(pri.loc[pri.c.map(is_pci), "hadm_id"])
    stemi_hadm = set(dxi.loc[dxi.c.map(is_stemi), "hadm_id"])
    angio_hadm = set(pri.loc[pri.c.map(is_angio), "hadm_id"])
    # KEY refinement: restrict to CAD admissions that were angiographically evaluated
    # (reached the treat-decision node). PCI/CABG imply a cath; this rescues the medical arm.
    cad_eval = (cad_hadm & angio_hadm) | (cad_hadm & pci_hadm) | (cad_hadm & cabg_hadm)
    print(f"[build] CAD admissions: {len(cad_hadm):,} | angiographically evaluated: {len(cad_eval):,}")

    # presentation typing (for the RCT-matched validation): STEMI / NSTEMI / unstable
    # angina / stable-chronic. Stable = the ISCHEMIA/COURAGE population.
    nstemi_hadm = set(dxi.loc[dxi.c.map(lambda c: c[:4] == "I214" or c[:4] == "4107"), "hadm_id"])
    ua_hadm = set(dxi.loc[dxi.c.map(lambda c: c[:4] == "I200" or c[:4] == "4111"), "hadm_id"])

    def presentation(h):
        if h in stemi_hadm:
            return "stemi"
        if h in nstemi_hadm:
            return "nstemi"
        if h in ua_hadm:
            return "unstable_angina"
        return "stable_chronic"

    coh = adm[adm.hadm_id.isin(cad_eval)].copy()
    coh["modality"] = np.where(coh.hadm_id.isin(cabg_hadm), "cabg",
                        np.where(coh.hadm_id.isin(pci_hadm), "pci", "medical"))
    coh["stemi"] = coh.hadm_id.isin(stemi_hadm)
    coh["presentation"] = coh.hadm_id.map(presentation)

    # outcomes
    coh["admittime"] = pd.to_datetime(coh.admittime); coh["dischtime"] = pd.to_datetime(coh.dischtime)
    coh["in_hosp_death"] = coh.hospital_expire_flag.astype(int)
    coh["los_days"] = (coh.dischtime - coh.admittime).dt.total_seconds() / 86400.0
    coh = coh.merge(pat, on="subject_id", how="left")
    coh["dod"] = pd.to_datetime(coh.dod)
    days_to_death = (coh.dod - coh.admittime).dt.total_seconds() / 86400.0
    coh["death_1y"] = ((days_to_death >= 0) & (days_to_death <= 365)).astype(int)
    coh["female"] = (coh.gender == "F").astype(int)

    # comorbidity confounders over CAD admissions only
    dcad = dxi[dxi.hadm_id.isin(cad_hadm)]
    rows = {}
    for h, g in dcad.groupby("hadm_id"):
        codes = g.c.tolist()
        r = {k: int(any(fn(c) for c in codes)) for k, fn in COMORB.items()}
        r["n_dx"] = len(codes)
        rows[h] = r
    com = pd.DataFrame.from_dict(rows, orient="index")
    coh = coh.merge(com, left_on="hadm_id", right_index=True, how="left")

    print(f"\n[build] cohort: {len(coh):,} CAD admissions "
          f"({int((~coh.stemi).sum()):,} non-STEMI)")
    print("[build] modality x STEMI:\n" + pd.crosstab(coh.modality, coh.stemi).to_string())

    # raw (confounded) outcome rates per modality — non-STEMI
    ns = coh[~coh.stemi]
    print("\n[build] RAW outcome rates (non-STEMI, CONFOUNDED — not causal):")
    print(ns.groupby("modality")[["in_hosp_death", "death_1y", "los_days"]].mean().round(3).to_string())
    print("        counts:", ns.modality.value_counts().to_dict())

    # overlap check: medical vs PCI, non-STEMI, on age+gender+comorbidity
    mp = ns[ns.modality.isin(["medical", "pci"])].copy()
    feat_cols = ["anchor_age", "female", "n_dx"] + list(COMORB.keys())
    Xdf = mp[feat_cols].apply(pd.to_numeric, errors="coerce")
    keep = Xdf.notna().mean(axis=1) >= 0.8
    mp, Xdf = mp[keep.values], Xdf[keep.values].fillna(Xdf.median())
    X = Xdf.to_numpy("float64"); y = (mp.modality.values == "pci").astype("int64")
    k = min(15, X.shape[1])
    pipe = make_pipeline(StandardScaler(), PCA(n_components=k), LogisticRegression(C=0.5, max_iter=2000))
    e = cross_val_predict(pipe, X, y, cv=StratifiedKFold(5, shuffle=True, random_state=0),
                          method="predict_proba")[:, 1]

    def auc(s):
        pos, neg = s[y == 1], s[y == 0]
        a = np.concatenate([pos, neg]); r = np.empty(len(a)); r[a.argsort()] = np.arange(1, len(a) + 1)
        return (r[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))

    edge = (e >= 0.25) & (e <= 0.75); w = e * (1 - e)
    ess = w.sum() ** 2 / (w ** 2).sum()
    print(f"\n[build] OVERLAP medical-vs-PCI (non-STEMI, age+sex+comorbidity, honest cross-fit):")
    print(f"        n={len(y):,} (med {int((y==0).sum())}/PCI {int((y==1).sum())})  "
          f"AUC {auc(e):.3f}  edge {int(edge.sum()):,}  ESS {ess:.0f}  on-supp {100*((e>=.1)&(e<=.9)).mean():.0f}%")

    coh.to_parquet(OUT)
    print(f"\n[build] saved {OUT.name}  ({len(coh):,} admissions, outcomes+confounders attached)")


if __name__ == "__main__":
    main()
