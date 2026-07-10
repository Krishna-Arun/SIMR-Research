"""
build_enriched_actions.py — Task 1: the rich, per-agent action vector aligned to CLMBR timepoints.

Replaces the coarse 14-way discrete action with a fixed-layout vector:
  [ continuous drips: presence bit + Option-A normalized rate ]   (per agent)
  [ presence-only drips ]                                          (per agent)
  [ discrete procedures ]                                          (vent/dialysis/cath/IABP/Impella)
  [ discrete PCI / CABG ]                                          (reused from trajectory action_ids)

Alignment: action_matrix[i] describes treatment active during the interval (T_{i-1}, T_i], i.e. the
treatment DRIVING the transition into state i — matching train_world_model.build_triples (A = act[1:]).
action_matrix[0] is zeros (no preceding interval). Absolute timepoints T come from encoded_states'
abs_times (saved by the patched encode_clmbr.reassemble) — exact, not reconstructed from hours.

Option-A rate normalization: per drug, on TRAIN-split patients only, cap at 99.5th pct -> log1p ->
robust-scale (median/IQR). Params saved to action_schema.json so val/test reuse them (no leakage).

Sources: MIMIC-IV icu/inputevents (drips), icu/procedureevents (procedures). Scoped to cohort hadm_ids.
Run via jobs/build_enriched_actions.sbatch (scans a 400 MB table — not the login node).
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
TRAJ = BASE / "data/trajectories.pkl"
COHORT = BASE / "cohort/cohort_v1.parquet"
SPLITS = BASE / "data/splits.json"
OUT_PKL = BASE / "data/enriched_actions.pkl"
OUT_SCHEMA = BASE / "data/action_schema.json"

# ---- action groups -------------------------------------------------------------------------
# continuous drips: presence + normalized rate (dose is clinically decisive here)
CONT_GROUPS = {
    "norepinephrine": [221906],
    "epinephrine":    [221289, 229617],
    "dopamine":       [221662],
    "dobutamine":     [221653],
    "vasopressin":    [222315],
    "phenylephrine":  [221749, 229630, 229632],
    "milrinone":      [221986],
    "insulin":        [223257, 223258, 223259, 223260, 223261, 223262, 229299, 229619],
    "propofol":       [222168],
    "fentanyl":       [221744, 225942],
    "midazolam":      [221668],
}
# presence-only drips (rate less comparable / less decisive)
PRES_DRIP_GROUPS = {
    "heparin_iv":    [225152, 229597, 230044],
    "furosemide_iv": [221794, 228340],
    "amiodarone":    [221347, 228339, 229654, 230034],
    "nitroglycerin": [222056],
    "nicardipine":   [222042, 229624],
}
# discrete procedures (presence while active), from procedureevents
PROC_GROUPS = {
    "ventilation":  [225792, 225794, 224385],          # invasive / non-invasive / intubation
    "dialysis":     [225441, 225802, 225436],          # HD / CRRT / CRRT filter change
    "cardiac_cath": [225430],
    "iabp":         [224272],
    "impella":      [228169],
}
# discrete PCI/CABG come from the trajectory's coarse action_ids (1=pci, 2=cabg)
TRAJ_ACTION = {"pci": 1, "cabg": 2}

RATE_CAP_PCT = 99.5   # per-drug clinical-sanity cap before scaling


def build_columns():
    cols = []
    for g in CONT_GROUPS:
        cols += [f"{g}__on", f"{g}__rate"]
    for g in PRES_DRIP_GROUPS:
        cols += [f"{g}__on"]
    for g in PROC_GROUPS:
        cols += [f"{g}__on"]
    for g in TRAJ_ACTION:
        cols += [f"{g}__on"]
    return cols


def itemid_to_group():
    m = {}
    for g, ids in {**CONT_GROUPS, **PRES_DRIP_GROUPS}.items():
        for i in ids:
            m[i] = g
    return m


def proc_itemid_to_group():
    m = {}
    for g, ids in PROC_GROUPS.items():
        for i in ids:
            m[i] = g
    return m


def scan_inputevents(hadm_set, want_items):
    """Return long df: subject_id, group, start, end, rate (NaN for bolus)."""
    ig = itemid_to_group()
    keep = []
    cols = ["subject_id", "hadm_id", "itemid", "starttime", "endtime", "rate"]
    for ch in pd.read_csv(MIMIC / "icu/inputevents.csv.gz", usecols=cols,
                          parse_dates=["starttime", "endtime"], chunksize=2_000_000):
        ch = ch[ch["hadm_id"].isin(hadm_set) & ch["itemid"].isin(want_items)]
        if len(ch):
            ch = ch.copy()
            ch["group"] = ch["itemid"].map(ig)
            keep.append(ch[["subject_id", "group", "starttime", "endtime", "rate"]])
    df = pd.concat(keep, ignore_index=True) if keep else \
        pd.DataFrame(columns=["subject_id", "group", "starttime", "endtime", "rate"])
    print(f"  inputevents rows kept: {len(df):,}")
    return df


def scan_procedureevents(hadm_set, want_items):
    pg = proc_itemid_to_group()
    keep = []
    cols = ["subject_id", "hadm_id", "itemid", "starttime", "endtime"]
    df = pd.read_csv(MIMIC / "icu/procedureevents.csv.gz", usecols=cols,
                     parse_dates=["starttime", "endtime"])
    df = df[df["hadm_id"].isin(hadm_set) & df["itemid"].isin(want_items)].copy()
    df["group"] = df["itemid"].map(pg)
    print(f"  procedureevents rows kept: {len(df):,}")
    return df[["subject_id", "group", "starttime", "endtime"]]


def fit_rate_scalers(rate_rows, train_subjects):
    """Option A per-drug: cap@99.5pct -> log1p -> robust(median/IQR), fit on TRAIN nonzero rates."""
    params = {}
    tr = rate_rows[rate_rows["subject_id"].isin(train_subjects)]
    for g in CONT_GROUPS:
        r = tr.loc[tr["group"] == g, "rate"].dropna().to_numpy(dtype=float)
        r = r[r > 0]
        if len(r) < 20:
            params[g] = {"cap": None, "median": 0.0, "iqr": 1.0, "n_train": int(len(r))}
            continue
        cap = float(np.percentile(r, RATE_CAP_PCT))
        rc = np.log1p(np.clip(r, 0, cap))
        med = float(np.median(rc))
        q1, q3 = np.percentile(rc, [25, 75])
        iqr = float(q3 - q1) or 1.0
        params[g] = {"cap": cap, "median": med, "iqr": iqr, "n_train": int(len(r))}
    return params


def norm_rate(g, raw, params):
    p = params[g]
    if raw is None or not np.isfinite(raw) or raw <= 0:
        return 0.0
    cap = p["cap"] if p["cap"] is not None else raw
    v = np.log1p(min(raw, cap))
    return float(np.clip((v - p["median"]) / p["iqr"], -5.0, 5.0))


def main():
    enc = pickle.load(open(ENC, "rb"))
    assert "abs_times" in enc[0], (
        "encoded_states has no abs_times — re-run the patched encode_clmbr.py first "
        "(jobs/reencode_clmbr.sbatch).")
    traj = {int(t["patient_id"]): t for t in pickle.load(open(TRAJ, "rb"))}
    cohort = pd.read_parquet(COHORT)
    hadm_set = set(int(h) for h in cohort["hadm_id"])
    splits = json.loads(SPLITS.read_text())
    train_subjects = set(splits["splits"]["train"])

    cols = build_columns()
    ci = {c: k for k, c in enumerate(cols)}
    D = len(cols)
    print(f"action dim D={D}\n  {cols}")

    want_drip = set().union(*CONT_GROUPS.values(), *PRES_DRIP_GROUPS.values())
    want_proc = set().union(*PROC_GROUPS.values())

    print("scanning inputevents (cohort-scoped)...")
    drips = scan_inputevents(hadm_set, want_drip)
    print("scanning procedureevents (cohort-scoped)...")
    procs = scan_procedureevents(hadm_set, want_proc)

    print("fitting Option-A rate scalers on TRAIN split...")
    scalers = fit_rate_scalers(drips, train_subjects)

    # index administrations by subject for fast per-patient access
    drips_by_s = {s: g for s, g in drips.groupby("subject_id")}
    procs_by_s = {s: g for s, g in procs.groupby("subject_id")}

    out = []
    n_with_action = 0
    for e in enc:
        pid = int(e["patient_id"])
        T_abs = pd.to_datetime(np.asarray(e["abs_times"]))
        T = len(T_abs)
        A = np.zeros((T, D), dtype=np.float32)

        d = drips_by_s.get(pid)
        p = procs_by_s.get(pid)
        tr = traj.get(pid)
        # PCI/CABG point-event times from trajectory coarse action_ids
        pcicabg = {g: [] for g in TRAJ_ACTION}
        if tr is not None:
            for ev in tr["events"]:
                for g, aid in TRAJ_ACTION.items():
                    if int(ev.get("action_id", 0)) == aid:
                        pcicabg[g].append(pd.Timestamp(ev["t"]))

        for i in range(1, T):
            lo, hi = T_abs[i - 1], T_abs[i]
            # drips overlapping (lo, hi]
            if d is not None:
                ov = d[(d["starttime"] <= hi) & (d["endtime"] > lo)]
                for g, sub in ov.groupby("group"):
                    A[i, ci[f"{g}__on"]] = 1.0
                    if g in CONT_GROUPS:
                        raw = sub["rate"].dropna()
                        rmax = float(raw.max()) if len(raw) else None
                        A[i, ci[f"{g}__rate"]] = norm_rate(g, rmax, scalers)
            # procedures overlapping (lo, hi]
            if p is not None:
                ov = p[(p["starttime"] <= hi) & (p["endtime"] > lo)]
                for g in ov["group"].unique():
                    A[i, ci[f"{g}__on"]] = 1.0
            # PCI/CABG point events in (lo, hi]
            for g, times in pcicabg.items():
                if any(lo < t <= hi for t in times):
                    A[i, ci[f"{g}__on"]] = 1.0

        if A[:, [ci[c] for c in cols if c.endswith("__on")]].any():
            n_with_action += 1
        out.append({"patient_id": pid, "abs_times": e["abs_times"], "action_matrix": A})

    pickle.dump(out, open(OUT_PKL, "wb"))
    schema = {"columns": cols, "dim": D,
              "cont_groups": CONT_GROUPS, "pres_drip_groups": PRES_DRIP_GROUPS,
              "proc_groups": PROC_GROUPS, "traj_action": TRAJ_ACTION,
              "rate_cap_pct": RATE_CAP_PCT, "rate_scalers": scalers,
              "n_patients": len(out), "n_with_any_action": n_with_action}
    OUT_SCHEMA.write_text(json.dumps(schema, indent=2, default=float))

    # quick coverage report
    stacked = np.concatenate([o["action_matrix"] for o in out], axis=0)
    print(f"\nwrote {OUT_PKL}  ({len(out)} patients, {stacked.shape[0]:,} timepoints)")
    print(f"patients with >=1 active intervention: {n_with_action}/{len(out)}")
    print("per-column activation rate (fraction of timepoints > 0):")
    for c in cols:
        frac = float((stacked[:, ci[c]] != 0).mean())
        print(f"    {c:24s} {frac*100:5.2f}%")
    print(f"\nwrote {OUT_SCHEMA}")


if __name__ == "__main__":
    main()
