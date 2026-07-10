"""
build_cohort_meds.py — cohort-scoped MEDS builder (path B) for the CLMBR encoder.

Instead of running meds_etl_mimic on all 364K MIMIC patients, we build MEDS for ONLY the ~1,431
cohort admissions' patients, emitting codes in the exact namespace femr/CLMBR's Athena ontology
recognizes (mirrors meds_etl/mimic conventions), with ONE change: labs are relabeled from the
MIMIC-native `MIMIC_IV_LABITEM/<itemid>` (which Athena can't map) to `LOINC/<code>` via our
crosswalk — otherwise labs are invisible to CLMBR.

Code namespaces (must match Athena concept_code formats so femr resolves them):
  birth/death   SNOMED/184099003, SNOMED/419620001              (meds.birth_code / death_code)
  gender        MIMIC_IV_Gender/<M|F>                            (structural; femr handles)
  diagnoses     ICD9CM/<dotted> | ICD10CM/<dotted>               (dotted via add_dot, like meds_etl)
  procedures    ICD9Proc/<dotted> | ICD10PCS/<code>
  labs          LOINC/<code>   + numeric_value                   (OUR relabel; the whole point)
  meds          NDC/<11-digit>                                   (femr maps NDC->RxNorm natively)

Full patient history (all admissions for each cohort subject) is included so CLMBR gets a rich
longitudinal timeline; the trajectory/label file restricts embedding times to the index admission.

Run in clmbr311:  python build_cohort_meds.py [--limit N]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

CA = "/scratch/users/karun09/Version_1/Counterfactual_Algorithm"
sys.path.insert(0, CA)
# action groups must be mapped from RAW icd/drug (not the namespaced MEDS codes), so use the
# group mappers directly at extraction time rather than event_to_action on a namespaced code.
from preprocessing.actions import ActionVocab, procedure_to_group, drug_to_group  # noqa: E402
from utils.common import save_pickle  # noqa: E402

MIMIC = Path("/scratch/users/karun09/physionet.org/files/mimiciv/3.1")
BASE = Path("/scratch/users/karun09/Version_2/counterfactual_simulation")
COHORT = BASE / "cohort/cohort_v1.parquet"
LABMAP = BASE / "cohort/lab_loinc_final.json"
OUT_DIR = BASE / "data"
MEDS_DATA = OUT_DIR / "mimic_meds" / "data"

BIRTH_CODE, DEATH_CODE = "SNOMED/184099003", "SNOMED/419620001"


def add_dot(code: str, pos: int) -> str:
    return code[:pos] + "." + code[pos:] if len(code) > pos else code


def icd_dx(ver, code):
    code = str(code)
    if str(ver) == "9":
        return "ICD9CM/" + (add_dot(code, 4) if code.startswith("E") else add_dot(code, 3))
    return "ICD10CM/" + add_dot(code, 3)


def icd_proc(ver, code):
    code = str(code)
    return ("ICD9Proc/" + add_dot(code, 2)) if str(ver) == "9" else ("ICD10PCS/" + code)


def norm_ndc(x) -> str:
    if not isinstance(x, str):
        x = "" if pd.isna(x) else str(x)
    d = "".join(ch for ch in x if ch.isdigit())
    return "" if (not d or int(d or 0) == 0) else d.zfill(11)[-11:]


def load_lab_map() -> dict:
    rows = json.loads(LABMAP.read_text())
    return {int(r["itemid"]): r["loinc_code"] for r in rows if r.get("loinc_code")}


def _t(x):
    """parse MIMIC timestamp -> python datetime (None if missing)."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    ts = pd.to_datetime(x, errors="coerce")
    return None if pd.isna(ts) else ts.to_pydatetime()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="only first N cohort subjects (for testing)")
    args = ap.parse_args()

    lab_map = load_lab_map()
    print(f"lab->LOINC map: {len(lab_map)} itemids")
    vocab = ActionVocab()
    NOOP = 0   # action id 0 = NO_OP (non-intervention events)

    cohort = pd.read_parquet(COHORT)
    cohort_hadm = set(int(h) for h in cohort["hadm_id"])

    adm = pd.read_csv(MIMIC / "hosp/admissions.csv.gz",
                      usecols=["subject_id", "hadm_id", "admittime", "dischtime"],
                      dtype={"subject_id": "int64", "hadm_id": "int64"})
    idx_adm = adm[adm["hadm_id"].isin(cohort_hadm)]
    subjects = sorted(idx_adm["subject_id"].unique().tolist())
    if args.limit:
        subjects = subjects[:args.limit]
    subj_set = set(subjects)
    print(f"cohort: {len(cohort_hadm)} admissions -> {len(subjects)} subjects"
          + (f" (limited to {args.limit})" if args.limit else ""))
    # index-admission window per subject (for label restriction later)
    idx_win = {int(r.subject_id): (_t(r.admittime), _t(r.dischtime))
               for r in idx_adm.itertuples() if int(r.subject_id) in subj_set}

    events = {s: [] for s in subjects}   # subject_id -> list[(time, code, numeric_value, action_id)]

    # ---- patients: birth, gender, death ----
    pat = pd.read_csv(MIMIC / "hosp/patients.csv.gz",
                      usecols=["subject_id", "gender", "anchor_age", "anchor_year", "dod"], dtype=str)
    pat = pat[pat["subject_id"].astype("int64").isin(subj_set)]
    for r in pat.itertuples():
        s = int(r.subject_id)
        try:
            birth = dt.datetime(int(r.anchor_year) - int(float(r.anchor_age)), 1, 1)
        except Exception:
            continue
        events[s].append((birth, BIRTH_CODE, None, NOOP))
        events[s].append((birth, f"MIMIC_IV_Gender/{r.gender}", None, NOOP))
        d = _t(r.dod)
        if d:
            events[s].append((d, DEATH_CODE, None, NOOP))
    print(f"  patients: {len(pat)} birth/gender/death sets")

    # ---- diagnoses (all admissions for these subjects), dotted ICD, at dischtime ----
    disch = adm.set_index("hadm_id")["dischtime"].to_dict()
    dx = pd.read_csv(MIMIC / "hosp/diagnoses_icd.csv.gz",
                     usecols=["subject_id", "hadm_id", "icd_code", "icd_version"], dtype=str)
    dx = dx[dx["subject_id"].astype("int64").isin(subj_set)]
    for r in dx.itertuples():
        t = _t(disch.get(int(r.hadm_id)))
        if t:
            events[int(r.subject_id)].append((t, icd_dx(r.icd_version, r.icd_code), None, NOOP))
    print(f"  diagnoses: {len(dx)}")

    # ---- procedures, dotted ICD, at chartdate ----
    pr = pd.read_csv(MIMIC / "hosp/procedures_icd.csv.gz",
                     usecols=["subject_id", "chartdate", "icd_code", "icd_version"], dtype=str)
    pr = pr[pr["subject_id"].astype("int64").isin(subj_set)]
    for r in pr.itertuples():
        t = _t(r.chartdate)
        if t:
            aid = vocab.to_id(procedure_to_group(r.icd_code))   # raw icd -> action group
            events[int(r.subject_id)].append((t, icd_proc(r.icd_version, r.icd_code), None, aid))
    print(f"  procedures: {len(pr)}")

    # ---- prescriptions (chunked), NDC/<11-digit>, at starttime ----
    n_rx = 0
    for ch in pd.read_csv(MIMIC / "hosp/prescriptions.csv.gz",
                          usecols=["subject_id", "starttime", "ndc", "drug"], dtype=str, chunksize=2_000_000):
        ch = ch[ch["subject_id"].astype("int64").isin(subj_set)]
        for r in ch.itertuples():
            ndc = norm_ndc(r.ndc)
            t = _t(r.starttime)
            if ndc and t:
                aid = vocab.to_id(drug_to_group(r.drug))        # raw drug name -> action group
                events[int(r.subject_id)].append((t, f"NDC/{ndc}", None, aid))
                n_rx += 1
    print(f"  prescriptions (with NDC): {n_rx}")

    # ---- labs (chunked), LOINC/<code> + numeric value, at charttime ----
    n_lab = 0
    for ch in pd.read_csv(MIMIC / "hosp/labevents.csv.gz",
                          usecols=["subject_id", "charttime", "itemid", "valuenum"],
                          dtype={"subject_id": "float64", "itemid": "float64"}, chunksize=5_000_000):
        ch = ch.dropna(subset=["subject_id", "itemid"])
        ch = ch[ch["subject_id"].astype("int64").isin(subj_set)]
        if not len(ch):
            continue
        for r in ch.itertuples():
            loinc = lab_map.get(int(r.itemid))
            if not loinc:
                continue
            t = _t(r.charttime)
            if not t:
                continue
            val = float(r.valuenum) if pd.notna(r.valuenum) else None
            events[int(r.subject_id)].append((t, f"LOINC/{loinc}", val, NOOP))
            n_lab += 1
    print(f"  labs (mapped, chunked): {n_lab}")

    # ---- assemble MEDS (patient-grouped, time-sorted) + trajectories (index-window labels) ----
    meds_rows, trajectories = [], []
    cohort_by_hadm = cohort.set_index("hadm_id")
    subj_to_idxhadm = {int(r.subject_id): int(r.hadm_id) for r in idx_adm.itertuples()
                       if int(r.subject_id) in subj_set}

    for s in subjects:
        evs = sorted(events[s], key=lambda e: e[0])
        if len(evs) < 2:
            continue
        meds_rows.append({"patient_id": s,
                          "events": [{"time": t, "code": c, "numeric_value": v} for t, c, v, _ in evs]})

        # trajectory: events within the index admission window (label times + precomputed actions)
        lo, hi = idx_win.get(s, (None, None))
        traj_events = []
        for t, c, v, aid in evs:
            if lo and hi and not (lo <= t <= hi):
                continue
            traj_events.append({"t": t, "code": c, "value": v, "action_id": int(aid)})
        if len(traj_events) < 2:
            continue
        hadm = subj_to_idxhadm.get(s)
        crow = cohort_by_hadm.loc[hadm] if hadm in cohort_by_hadm.index else None
        outcomes = {} if crow is None else {
            "mortality": int(crow["in_hospital_mortality"]) if pd.notna(crow["in_hospital_mortality"]) else 0,
            "mortality_30d": int(crow["mortality_30d"]) if pd.notna(crow["mortality_30d"]) else 0,
            "readmission_30d": int(crow["readmission_30d"]) if pd.notna(crow["readmission_30d"]) else 0,
            "icu_los_days": float(crow["icu_los_days"]) if pd.notna(crow["icu_los_days"]) else 0.0,
            "arm": str(crow["arm"]),
        }
        trajectories.append({"patient_id": s, "static": {}, "events": traj_events, "outcomes": outcomes})

    print(f"\nassembled {len(meds_rows)} patients with >=2 events; {len(trajectories)} trajectories")

    # ---- write MEDS parquet via datasets (guaranteed compatible with encode_clmbr load) ----
    import datasets
    MEDS_DATA.mkdir(parents=True, exist_ok=True)
    ds = datasets.Dataset.from_list(meds_rows)
    shard = MEDS_DATA / "cohort_000.parquet"
    ds.to_parquet(str(shard))
    print(f"wrote MEDS -> {shard}  ({len(ds)} patients)")

    save_pickle(trajectories, str(OUT_DIR / "trajectories.pkl"))
    print(f"wrote trajectories -> {OUT_DIR / 'trajectories.pkl'}  ({len(trajectories)} patients)")
    (OUT_DIR / "action_vocab.json").write_text(json.dumps(vocab.groups, indent=2))
    print(f"action vocab ({len(vocab.groups)}): {vocab.groups}")


if __name__ == "__main__":
    main()
