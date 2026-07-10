"""
build_train_substrate.py — the FINAL, cleaned training substrate (fixes two data-quality bugs).

The encoded_states timepoints span a patient's whole record for some patients (index-admission
window fell through -> multi-YEAR spans) and are hugely skewed (one patient = 29% of all timepoints).
Training transitions are weighted by timepoint count, so uncorrected this fits the world model to ~10
patients. Two principled fixes, applied jointly to embeddings + enriched actions (they share abs_times):

  1. WINDOW  — keep only timepoints inside the patient's cohort (index) admission window
               [admittime, dischtime]. Kills the multi-year contamination. CLMBR still encoded full
               history as CONTEXT; we only restrict which transitions we train on.
  2. CAP     — after windowing, uniformly subsample to <= CAP timepoints per patient so no single
               (dense-charting) patient dominates. Δt is a model input, so wider gaps are fine.

Output: data/train_substrate.pkl — list of {patient_id, s, abs_times, hours, action_matrix,
action_cols, outcomes}. Everything downstream (model, probe, eval) reads THIS, not the raw files.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path("/scratch/users/karun09/Version_2/counterfactual_simulation")
MIMIC = Path("/scratch/users/karun09/physionet.org/files/mimiciv/3.1")
ENC = BASE / "data/encoded_states_clmbr.pkl"
ACT = BASE / "data/enriched_actions.pkl"
SCHEMA = BASE / "data/action_schema.json"
COHORT = BASE / "cohort/cohort_v1.parquet"
OUT = BASE / "data/train_substrate.pkl"
CAP = 150   # max timepoints/patient after windowing


def subject_windows():
    """subject_id -> list of (admit, disch) for that subject's COHORT admissions."""
    cohort = pd.read_parquet(COHORT)
    hadm_set = set(int(h) for h in cohort["hadm_id"])
    adm = pd.read_csv(MIMIC / "hosp/admissions.csv.gz",
                      usecols=["subject_id", "hadm_id", "admittime", "dischtime"],
                      parse_dates=["admittime", "dischtime"])
    adm = adm[adm["hadm_id"].isin(hadm_set)]
    wins = {}
    for r in adm.itertuples():
        wins.setdefault(int(r.subject_id), []).append((r.admittime, r.dischtime))
    return wins


def main():
    enc = pickle.load(open(ENC, "rb"))
    acts = {int(a["patient_id"]): a for a in pickle.load(open(ACT, "rb"))}
    schema = json.loads(SCHEMA.read_text())
    cols = schema["columns"]
    wins = subject_windows()

    out = []
    dropped_no_win = 0
    T_before, T_after = [], []
    for e in enc:
        pid = int(e["patient_id"])
        a = acts.get(pid)
        if a is None:
            continue
        t = pd.to_datetime(np.asarray(e["abs_times"]))
        T_before.append(len(t))
        # 1. window: keep timepoints inside ANY cohort admission window (+/- small pad)
        w = wins.get(pid, [])
        if not w:
            dropped_no_win += 1
            continue
        keep = np.zeros(len(t), dtype=bool)
        for (lo, hi) in w:
            keep |= (t >= lo - pd.Timedelta(hours=6)) & (t <= hi + pd.Timedelta(hours=6))
        idx = np.where(keep)[0]
        if len(idx) < 2:
            continue
        # 2. cap: uniform subsample to <= CAP, preserving order + endpoints
        if len(idx) > CAP:
            sel = np.linspace(0, len(idx) - 1, CAP).round().astype(int)
            idx = idx[np.unique(sel)]
        T_after.append(len(idx))

        s = np.asarray(e["s"], dtype=np.float32)[idx]
        abs_t = np.asarray(e["abs_times"])[idx]
        hrs = ((pd.to_datetime(abs_t) - pd.to_datetime(abs_t)[0]).total_seconds() / 3600.0
               ).to_numpy(dtype=np.float32)
        A = a["action_matrix"][idx]
        out.append({"patient_id": pid, "s": s, "abs_times": abs_t, "hours": hrs,
                    "action_matrix": A.astype(np.float32), "action_cols": cols,
                    "outcomes": e["outcomes"]})

    pickle.dump(out, open(OUT, "wb"))
    Tb, Ta = np.array(T_before), np.array(T_after)
    tot_b, tot_a = int(Tb.sum()), int(Ta.sum())
    print(f"patients: {len(out)} kept  ({dropped_no_win} dropped: no cohort window)")
    print(f"timepoints: {tot_b:,} -> {tot_a:,}")
    print(f"  per-patient T after: median={int(np.median(Ta))} p95={int(np.percentile(Ta,95))} max={int(Ta.max())}")
    order = np.argsort(-Ta)
    top_share = 100 * Ta[order[:10]].sum() / tot_a
    print(f"  top-10 patients now hold {top_share:.1f}% of timepoints (was 60.6%)")
    # activation after cleaning
    ci = {c: i for i, c in enumerate(cols)}
    stacked = np.concatenate([o["action_matrix"] for o in out], axis=0)
    print("\nactivation after cleaning (%timepoints > 0):")
    for c in cols:
        if c.endswith("__on"):
            print(f"    {c[:-4]:20s} {100*(stacked[:,ci[c]]>0).mean():6.2f}%")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
