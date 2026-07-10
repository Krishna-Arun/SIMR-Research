#!/usr/bin/env python3
"""
Longitudinal ICU cohort builder — real MIMIC-IV v3.1 (2physionet.org).

Selects an ICU-only cohort where each stay supports the longitudinal chain
A -> C -> B -> A2, anchored on a LAB-DRIVEN intervention (dialysis / transfusion /
ventilation) that occurred during the ICU stay with dense surrounding labs.

Cohort-first (labevents is 2.4 GB, ~150M rows — never loaded whole):
  1. icustays + icu/procedureevents  -> candidate stays with a lab-driven procedure
  2. bound to the first N_CANDIDATES candidates, collect their hadm_ids
  3. ONE chunked pass over hosp/labevents, keeping only candidate hadm_ids
  4. confirm >=MIN_PRE labs before the procedure and >=MIN_POST within 72h after
  5. take the first COHORT_SIZE confirmed stays
  6. materialize per-cohort slices (labs, procedures, micro, dx, admissions, patients)
     to cohort_data/ as parquet + cohort_index.json

Run:  python cohort.py           (writes Longitudinal/cohort_data/)
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

MIMIC = (Path(__file__).resolve().parents[2]
         / "2physionet.org/files/mimiciv/3.1")
# CARDIAC restriction: cohort is limited to admissions in the MIMIC-IV-Ext cardiac-disease
# dataset (heart_*). We take the patient/admission IDs from there and pull full data from
# the real MIMIC-IV above.
CARDIAC_DIR = Path(__file__).resolve().parents[2] / "mimic-iv-ext-cardiac-disease-1.0.0"
CARDIAC_ID_FILES = ["heart_diagnoses_all.csv", "heart_procedures.csv", "heart_diagnoses.csv"]
OUT = Path(__file__).resolve().parent / "cohort_data"

# Build a LARGE eligible index (generation later runs on a bounded subset).
N_CANDIDATES = 4000         # candidate stays per family to scan
POST_H = 72
# reference inclusion filters (admission-level lab density) + anchor-window density
MIN_DISTINCT_LABS = 20      # >= 20 distinct lab itemids during the admission
MIN_LAB_MEAS = 50           # >= 50 total lab measurements during the admission
MIN_PRE, MIN_POST = 2, 2    # >=2 labs before / >=2 within 72h after the anchor (for the trajectory step)
LABEVENTS_CHUNK = 5_000_000
INPUTEVENTS_CHUNK = 3_000_000

# family-balanced target for the eligible index (large; any general-ICU patient qualifies).
FAMILY_CAP = {"dialysis": 500, "transfusion": 500, "ventilation": 500}
FAMILY_PRIORITY = ["dialysis", "transfusion", "ventilation"]
SPLIT_FRACS = (0.70, 0.10, 0.20)   # train / val / test, patient-level, stratified by family

# dialysis/ventilation come from icu/procedureevents (by label keyword);
# transfusion comes from icu/inputevents (RBC product itemids — NOT in procedureevents).
LAB_DRIVEN = {
    "dialysis": ("dialysis", "crrt", "hemodialysis", "renal replacement"),
    "ventilation": ("invasive ventilation", "intubation", "mechanical ventilation"),
}
TRANSFUSION_ITEMIDS = {225168, 220996}      # Packed Red Blood Cells / Packed Red Cells


def _dt(s):
    return pd.to_datetime(s, errors="coerce")


def _family(label: str):
    low = str(label).lower()
    for fam, keys in LAB_DRIVEN.items():
        if any(k in low for k in keys):
            return fam
    return None


def _load_cardiac_hadms():
    """Union of hadm_ids across the cardiac-ext ID files (the cardiac universe)."""
    hadms = set()
    for f in CARDIAC_ID_FILES:
        p = CARDIAC_DIR / f
        if p.exists():
            d = pd.read_csv(p, usecols=lambda c: c == "hadm_id")
            hadms |= set(d["hadm_id"].dropna().astype("int64"))
    return hadms


def main():
    OUT.mkdir(exist_ok=True)
    cardiac_hadms = _load_cardiac_hadms()
    print(f"cardiac universe: {len(cardiac_hadms)} admissions (cohort restricted to these)", flush=True)
    print("loading icustays + d_items ...", flush=True)
    icu = pd.read_csv(MIMIC / "icu/icustays.csv.gz",
                      usecols=["subject_id", "hadm_id", "stay_id", "intime", "outtime"])
    icu["intime"] = _dt(icu["intime"]); icu["outtime"] = _dt(icu["outtime"])
    ditems = pd.read_csv(MIMIC / "icu/d_items.csv.gz", usecols=["itemid", "label"])
    ilabel = dict(zip(ditems["itemid"], ditems["label"]))

    print("loading admissions/patients (for alive-at-time-zero) ...", flush=True)
    adm = pd.read_csv(MIMIC / "hosp/admissions.csv.gz",
                      usecols=["hadm_id", "deathtime", "hospital_expire_flag"])
    adm["deathtime"] = _dt(adm["deathtime"])
    deathtime_by_hadm = dict(zip(adm["hadm_id"], adm["deathtime"]))
    pats = pd.read_csv(MIMIC / "hosp/patients.csv.gz", usecols=["subject_id", "dod"])
    pats["dod"] = _dt(pats["dod"])
    dod_by_subject = dict(zip(pats["subject_id"], pats["dod"]))

    def alive_at(subject_id, hadm_id, t0):
        dt = deathtime_by_hadm.get(hadm_id)
        if pd.notna(dt) and dt <= t0:
            return False
        dod = dod_by_subject.get(subject_id)
        return not (pd.notna(dod) and dod <= t0)

    print("loading icu/procedureevents (dialysis/ventilation) ...", flush=True)
    pe = pd.read_csv(MIMIC / "icu/procedureevents.csv.gz",
                     usecols=["subject_id", "hadm_id", "stay_id", "starttime", "itemid"])
    pe["starttime"] = _dt(pe["starttime"])
    pe["label"] = pe["itemid"].map(ilabel).astype(str)
    pe["family"] = pe["label"].map(_family)
    pe = pe[pe["family"].notna()][["subject_id", "hadm_id", "stay_id", "starttime", "label", "family"]]

    print("chunked scan of icu/inputevents for transfusions ...", flush=True)
    tx = []
    for chunk in pd.read_csv(MIMIC / "icu/inputevents.csv.gz",
                             usecols=["subject_id", "hadm_id", "stay_id", "starttime", "itemid"],
                             chunksize=INPUTEVENTS_CHUNK, low_memory=False):
        sub = chunk[chunk["itemid"].isin(TRANSFUSION_ITEMIDS)]
        if len(sub):
            tx.append(sub)
    if tx:
        tx = pd.concat(tx, ignore_index=True)
        tx["starttime"] = _dt(tx["starttime"]); tx["label"] = "Packed Red Blood Cells"
        tx["family"] = "transfusion"
        pe = pd.concat([pe, tx[["subject_id", "hadm_id", "stay_id", "starttime", "label", "family"]]],
                       ignore_index=True)
    print(f"  transfusion events found: {len(tx) if len(tx) else 0}", flush=True)

    # one anchor per ICU stay, earliest; prefer dialysis > transfusion > ventilation
    prio = {"dialysis": 0, "transfusion": 1, "ventilation": 2}
    pe["prio"] = pe["family"].map(prio)
    pe = pe.sort_values(["stay_id", "starttime", "prio"]).groupby("stay_id", as_index=False).first()
    cand = pe.merge(icu, on=["subject_id", "hadm_id", "stay_id"], suffixes=("", "_icu"))
    cand = cand[(cand["starttime"] >= cand["intime"]) & (cand["starttime"] <= cand["outtime"])]
    # CARDIAC restriction — keep only cardiac-cohort admissions (also shrinks the labevents scan)
    if cardiac_hadms:
        cand = cand[cand["hadm_id"].astype("int64").isin(cardiac_hadms)]
    from collections import Counter as _C
    print(f"cardiac ICU candidate stays: {len(cand)}  by family: {dict(_C(cand['family']))}", flush=True)
    # keep a family-balanced candidate pool so dialysis/transfusion aren't crowded out
    cand = (cand.sort_values("stay_id").groupby("family", as_index=False)
            .head(N_CANDIDATES)).reset_index(drop=True)
    cand_hadm = set(cand["hadm_id"].astype("int64"))
    from collections import Counter
    print(f"candidate stays: {len(cand)}  by family: {dict(Counter(cand['family']))}", flush=True)

    print("chunked scan of hosp/labevents (2.4G) filtering to candidates ...", flush=True)
    keep = []
    cols = ["subject_id", "hadm_id", "itemid", "charttime", "value", "valuenum",
            "valueuom", "ref_range_lower", "ref_range_upper", "flag"]
    n = 0
    for chunk in pd.read_csv(MIMIC / "hosp/labevents.csv.gz", usecols=cols,
                             chunksize=LABEVENTS_CHUNK, low_memory=False):
        sub = chunk[chunk["hadm_id"].isin(cand_hadm)]
        if len(sub):
            keep.append(sub)
        n += len(chunk)
        print(f"  scanned {n:,} rows, kept {sum(len(k) for k in keep):,}", flush=True)
    labs = pd.concat(keep, ignore_index=True) if keep else pd.DataFrame(columns=cols)
    labs["charttime"] = _dt(labs["charttime"])
    labs_by_hadm = {h: g for h, g in labs.groupby("hadm_id")}

    print("applying reference inclusion filters "
          "(alive@t0, >=20 distinct labs & >=50 measurements, >=2 pre/>=2 post-72h) ...", flush=True)
    per_fam = {f: [] for f in FAMILY_CAP}
    density_stats = []
    for _, c in cand.iterrows():
        fam = c["family"]
        if len(per_fam.get(fam, [])) >= FAMILY_CAP.get(fam, 0):
            continue
        h, subj, t0 = int(c["hadm_id"]), int(c["subject_id"]), c["starttime"]
        if not alive_at(subj, h, t0):                       # eligible = alive at the decision point
            continue
        L = labs_by_hadm.get(h)
        if L is None:
            continue
        # admission-level density (the reference filter)
        n_distinct = L["itemid"].nunique()
        n_meas = len(L)
        if n_distinct < MIN_DISTINCT_LABS or n_meas < MIN_LAB_MEAS:
            continue
        # anchor-window density (needed for the B trajectory step)
        rr = L[L["ref_range_upper"].notna() & L["valuenum"].notna()]
        pre = rr[rr["charttime"] < t0]
        post = rr[(rr["charttime"] > t0) & (rr["charttime"] <= t0 + pd.Timedelta(hours=POST_H))]
        if len(pre) < MIN_PRE or len(post) < MIN_POST:
            continue
        c = c.copy(); c["n_distinct_labs"] = int(n_distinct); c["n_lab_meas"] = int(n_meas)
        per_fam[fam].append(c)
        density_stats.append(n_distinct)
        if sum(len(v) for v in per_fam.values()) >= sum(FAMILY_CAP.values()):
            break
    chosen = []
    for fam in FAMILY_PRIORITY:
        chosen += per_fam[fam]
    from collections import Counter
    print(f"eligible cohort: {len(chosen)}  by family: {dict(Counter(c['family'] for c in chosen))}", flush=True)
    if density_stats:
        s = pd.Series(density_stats)
        print(f"  distinct-lab density: min={s.min()} median={int(s.median())} max={s.max()}", flush=True)
    cohort = pd.DataFrame(chosen)
    cohort_hadm = set(cohort["hadm_id"].astype("int64"))

    # ── materialize slices for the cohort ──────────────────────────────────
    print("materializing cohort slices ...", flush=True)
    labs[labs["hadm_id"].isin(cohort_hadm)].to_parquet(OUT / "labs.parquet", index=False)

    peall = pd.read_csv(MIMIC / "icu/procedureevents.csv.gz",
                        usecols=["subject_id", "hadm_id", "stay_id", "starttime", "itemid",
                                 "value", "valueuom"])
    peall = peall[peall["hadm_id"].isin(cohort_hadm)].copy()
    peall["label"] = peall["itemid"].map(ilabel)
    peall.to_parquet(OUT / "procedureevents.parquet", index=False)

    for sub, tbl, key in [("hosp", "diagnoses_icd", "hadm_id"),
                           ("hosp", "microbiologyevents", "hadm_id"),
                           ("hosp", "admissions", "hadm_id"),
                           ("hosp", "patients", "subject_id"),
                           ("hosp", "procedures_icd", "hadm_id")]:
        df = pd.read_csv(MIMIC / f"{sub}/{tbl}.csv.gz", low_memory=False)
        keyset = cohort_hadm if key == "hadm_id" else set(cohort["subject_id"].astype("int64"))
        df[df[key].isin(keyset)].to_parquet(OUT / f"{tbl}.parquet", index=False)
        print(f"  {tbl}: sliced", flush=True)

    # dictionaries (small, copied whole)
    pd.read_csv(MIMIC / "hosp/d_labitems.csv.gz").to_parquet(OUT / "d_labitems.parquet", index=False)
    ditems.to_parquet(OUT / "d_items.parquet", index=False)
    pd.read_csv(MIMIC / "hosp/d_icd_procedures.csv.gz").to_parquet(OUT / "d_icd_procedures.parquet", index=False)
    pd.read_csv(MIMIC / "hosp/d_icd_diagnoses.csv.gz").to_parquet(OUT / "d_icd_diagnoses.parquet", index=False)

    index = [{"subject_id": int(c["subject_id"]), "hadm_id": int(c["hadm_id"]),
              "stay_id": int(c["stay_id"]), "anchor_procedure": str(c["label"]),
              "anchor_family": str(c["family"]), "anchor_time": str(c["starttime"]),
              "icu_intime": str(c["intime"]), "icu_outtime": str(c["outtime"]),
              "n_distinct_labs": int(c.get("n_distinct_labs", 0)),
              "n_lab_meas": int(c.get("n_lab_meas", 0))}
             for _, c in cohort.iterrows()]
    json.dump({"cohort_size": len(index), "post_window_h": POST_H,
               "inclusion": {"alive_at_t0": True, "icu_only": True,
                             "min_distinct_labs": MIN_DISTINCT_LABS, "min_lab_meas": MIN_LAB_MEAS},
               "patients": index}, open(OUT / "cohort_index.json", "w"), indent=2)

    # ── patient-level split, stratified by anchor family (anti-circularity) ──
    split = {"train": [], "val": [], "test": []}
    subj_first_fam = {}                       # each subject assigned once, by its first stay's family
    for p in sorted(index, key=lambda x: x["subject_id"]):
        subj_first_fam.setdefault(p["subject_id"], p["anchor_family"])
    from collections import defaultdict
    by_fam = defaultdict(list)
    for subj, fam in subj_first_fam.items():
        by_fam[fam].append(subj)
    for fam, subs in by_fam.items():
        subs = sorted(subs)                   # deterministic
        n = len(subs); ntr = int(n * SPLIT_FRACS[0]); nva = int(n * SPLIT_FRACS[1])
        split["train"] += subs[:ntr]; split["val"] += subs[ntr:ntr + nva]; split["test"] += subs[ntr + nva:]
    # sanity: no subject in two splits
    allsub = split["train"] + split["val"] + split["test"]
    assert len(allsub) == len(set(allsub)), "subject leaked across splits"
    json.dump({"fracs": SPLIT_FRACS, "by_subject": split,
               "sizes": {k: len(v) for k, v in split.items()}},
              open(OUT / "cohort_split.json", "w"), indent=2)

    print(f"\nDONE. cohort_index.json ({len(index)} ICU stays) + cohort_split.json + slices in {OUT}")
    from collections import Counter
    print("anchor families:", dict(Counter(p["anchor_family"] for p in index)))
    print("split sizes (subjects):", {k: len(v) for k, v in split.items()})


if __name__ == "__main__":
    main()
