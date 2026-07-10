#!/usr/bin/env python3
"""Encode the 494 cardiac-ICU cohort patients with Stanford CLMBR-t-base.

Pipeline (all local, real data):
  MIMIC-IV cohort parquet  ->  in-memory MEDS patient dicts (OMOP standard codes)
  ->  femr FEMRTokenizer + FEMRBatchProcessor  ->  FEMRModel forward (CPU)
  ->  per-event state embeddings [T, 768]  ->  embeddings/<subject_id>.npy + index.json

Code mapping to CLMBR's OMOP vocabulary:
  - demographics: Gender/M | Gender/F  (+ birth event SNOMED/184099003 for age)
  - diagnoses  : ICD9CM/ICD10CM  --Athena 'Maps to'-->  standard (SNOMED...)  [icd_to_clmbr.json]
  - procedures : ICD9Proc/ICD10PCS --Athena 'Maps to'--> standard              [icd_to_clmbr.json]
  - labs       : MIMIC itemid  --curated-->  LOINC (numeric, femr value-binned) [lab_to_loinc.json]
Codes not present in the CLMBR token vocabulary are dropped (reported in index.json).
"""
import argparse, datetime, json, sys, warnings
from pathlib import Path
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import torch

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
COHORT = REPO / "Version_3/Longitudinal/cohort_data"
MODEL = REPO / "Version_3/loaded_models/clmbr-t-base"
BUILD = HERE / "meds_build"
EMB = HERE / "embeddings"
EMB.mkdir(exist_ok=True)

BIRTH_CODE = "SNOMED/184099003"


def to_dt(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return pd.Timestamp(x).to_pydatetime()


def build_patient(subject_id, pat_row, adm_df, diag_df, proc_df, lab_df, icd_map, lab_map, stats):
    """Return (meds_patient_dict, birthdate) using only CLMBR-in-vocab codes."""
    # birthdate: MIMIC only reveals year (anchor_year - anchor_age)
    birth_year = int(pat_row["anchor_year"]) - int(pat_row["anchor_age"])
    birth = datetime.datetime(birth_year, 1, 1)
    events = []
    # --- birth event: birth code + gender ---
    m0 = [{"code": BIRTH_CODE, "numeric_value": None, "text_value": None}]
    g = str(pat_row.get("gender") or "").strip().upper()
    if g in ("M", "F"):
        m0.append({"code": f"Gender/{g}", "numeric_value": None, "text_value": None})
        stats["gender"] += 1
    events.append({"time": birth, "measurements": m0})

    # --- diagnoses at discharge time ---
    for _, r in diag_df.iterrows():
        key = f"{int(r.icd_version)}|{str(r.icd_code).replace('.', '').strip().upper()}"
        codes = icd_map.get(key)
        if not codes:
            stats["diag_miss"] += 1
            continue
        t = to_dt(r.get("_time"))
        if t is None or t < birth:
            continue
        for cs in codes:
            events.append({"time": t, "measurements": [{"code": cs, "numeric_value": None, "text_value": None}]})
            stats["diag_ok"] += 1

    # --- procedures at chartdate ---
    for _, r in proc_df.iterrows():
        key = f"{int(r.icd_version)}|{str(r.icd_code).replace('.', '').strip().upper()}"
        codes = icd_map.get(key)
        if not codes:
            stats["proc_miss"] += 1
            continue
        t = to_dt(r.get("chartdate"))
        if t is None or t < birth:
            continue
        for cs in codes:
            events.append({"time": t, "measurements": [{"code": cs, "numeric_value": None, "text_value": None}]})
            stats["proc_ok"] += 1

    # --- labs at charttime (numeric) ---
    for _, r in lab_df.iterrows():
        cs = lab_map.get(int(r.itemid))
        if cs is None:
            stats["lab_miss"] += 1
            continue
        val = r.valuenum
        if val is None or (isinstance(val, float) and np.isnan(val)):
            continue
        t = to_dt(r.charttime)
        if t is None or t < birth:
            continue
        events.append({"time": t, "measurements": [{"code": cs, "numeric_value": float(val), "text_value": None}]})
        stats["lab_ok"] += 1

    # sort chronologically, birth first (stable)
    events.sort(key=lambda e: e["time"])
    return {"patient_id": int(subject_id), "events": events}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="only encode first N patients (0=all)")
    ap.add_argument("--subjects", type=str, default="", help="comma list of subject_ids")
    args = ap.parse_args()

    import femr.models.tokenizer, femr.models.processor, femr.models.transformer

    icd_map = json.loads((BUILD / "icd_to_clmbr.json").read_text())
    lab_map = {int(k): v for k, v in json.loads((BUILD / "lab_to_loinc.json").read_text()).items()}

    index = json.loads((COHORT / "cohort_index.json").read_text())
    patients_meta = index["patients"]
    if args.subjects:
        want = {int(x) for x in args.subjects.split(",")}
        patients_meta = [p for p in patients_meta if p["subject_id"] in want]
    if args.limit:
        patients_meta = patients_meta[: args.limit]
    sids = [p["subject_id"] for p in patients_meta]
    print(f"encoding {len(sids)} patients", file=sys.stderr)

    # load tables once, index by subject
    patients = pd.read_parquet(COHORT / "patients.parquet").set_index("subject_id")
    adm = pd.read_parquet(COHORT / "admissions.parquet")
    diag = pd.read_parquet(COHORT / "diagnoses_icd.parquet")
    proc = pd.read_parquet(COHORT / "procedures_icd.parquet")
    labs = pd.read_parquet(COHORT / "labs.parquet")
    # attach discharge time to diagnoses (recorded at discharge)
    disch = adm.set_index("hadm_id")["dischtime"].to_dict()
    diag["_time"] = diag["hadm_id"].map(disch)
    diag_by = dict(tuple(diag.groupby("subject_id")))
    proc_by = dict(tuple(proc.groupby("subject_id")))
    lab_by = dict(tuple(labs.groupby("subject_id")))

    print("loading CLMBR-t-base...", file=sys.stderr)
    tok = femr.models.tokenizer.FEMRTokenizer.from_pretrained(str(MODEL))
    bp = femr.models.processor.FEMRBatchProcessor(tok)
    model = femr.models.transformer.FEMRModel.from_pretrained(str(MODEL))
    model.eval()

    empty = pd.DataFrame()
    stats = {k: 0 for k in ["gender", "diag_ok", "diag_miss", "proc_ok", "proc_miss", "lab_ok", "lab_miss"]}
    out_index = {"model": "clmbr-t-base", "dim": 768, "patients": {}}
    n_ok = 0
    for meta in patients_meta:
        sid = meta["subject_id"]
        if sid not in patients.index:
            out_index["patients"][str(sid)] = {"error": "no patients row"}
            continue
        prow = patients.loc[sid]
        if isinstance(prow, pd.DataFrame):
            prow = prow.iloc[0]
        p = build_patient(sid, prow, adm, diag_by.get(sid, empty), proc_by.get(sid, empty),
                          lab_by.get(sid, empty), icd_map, lab_map, stats)
        if len(p["events"]) < 2:
            out_index["patients"][str(sid)] = {"error": "too few in-vocab events", "n_events": len(p["events"])}
            continue
        try:
            raw = bp.convert_patient(p, tensor_type="pt")
            batch = bp.collate([raw])
            with torch.no_grad():
                _, res = model(**batch)
            reps = res["representations"].cpu().numpy().astype(np.float32)
            ts = res["timestamps"].cpu().numpy().astype("datetime64[s]").astype(str).tolist()
        except Exception as e:
            out_index["patients"][str(sid)] = {"error": f"{type(e).__name__}: {e}"}
            print(f"  ! {sid}: {e}", file=sys.stderr)
            continue
        path = EMB / f"{sid}.npy"
        np.save(path, reps)
        out_index["patients"][str(sid)] = {
            "path": str(path), "T": int(reps.shape[0]), "D": int(reps.shape[1]),
            "event_times": ts, "anchor_time": meta.get("anchor_time"),
            "n_meds_events": len(p["events"]),
        }
        n_ok += 1
        if n_ok <= 5 or n_ok % 50 == 0:
            print(f"  [{n_ok}] subject {sid}: {reps.shape}", file=sys.stderr)

    out_index["mapping_stats"] = stats
    out_index["n_encoded"] = n_ok
    (EMB / "index.json").write_text(json.dumps(out_index, indent=1))
    print(f"\nENCODED {n_ok}/{len(sids)} patients", file=sys.stderr)
    print("mapping stats:", stats, file=sys.stderr)
    print("index ->", EMB / "index.json", file=sys.stderr)


if __name__ == "__main__":
    main()
