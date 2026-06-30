"""Benchmark B cohort: ICU-procedure-anchored admissions with repeated core labs pre+post.

Time-zero = an ICU procedure's start. A procedure is eligible if >= min_labs_with_traj core labs each
have >= min_pre measurements before and >= min_post within post_window_h after the procedure.

Memory-safe (mirrors A's pool approach): restrict the labevents scan to (a) the core-lab itemids and
(b) admissions that actually have an ICU procedure, so we never hold the full 2.5 GB table.

Outputs:
  core_labs.parquet        all core-lab rows for candidate admissions (label, ref ranges, value, time)
  procedures.parquet       all ICU procedures (hadm_id, stay_id, itemid, label, starttime)
  eligible_index.parquet   one row per eligible procedure (+ n_traj_labs)
  pool.parquet             seeded pool of eligible procedures to materialize/sample

Run: python -m qgen.cohort
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

from qgen.config import load_config, mimic_root, out_dir


def _gz(root: Path, subdir: str, table: str) -> Path:
    p = root / subdir / f"{table}.csv.gz"
    return p if p.exists() else root / subdir / f"{table}.csv"


def core_lab_itemids(root: Path, core_labs: list[str]) -> pd.DataFrame:
    """Map the configured core-lab label names to labevents itemids via d_labitems (blood/chem only)."""
    dlab = pd.read_csv(_gz(root, "hosp", "d_labitems"), usecols=["itemid", "label", "fluid", "category"])
    want = {c.lower() for c in core_labs}
    sel = dlab[dlab["label"].str.lower().isin(want)].copy()
    # prefer Blood fluid where duplicate labels exist
    sel["_blood"] = (sel["fluid"].str.lower() == "blood").astype(int)
    sel = sel.sort_values("_blood", ascending=False).drop_duplicates("label")
    return sel[["itemid", "label", "fluid", "category"]]


def _procedures(root: Path, categories: list[str] | None = None) -> pd.DataFrame:
    proc = pd.read_csv(_gz(root, "icu", "procedureevents"),
                       usecols=["subject_id", "hadm_id", "stay_id", "starttime", "itemid"],
                       parse_dates=["starttime"], low_memory=False)
    proc = proc.dropna(subset=["hadm_id", "starttime"])
    proc["hadm_id"] = proc["hadm_id"].astype("int64")
    ditems = pd.read_csv(_gz(root, "icu", "d_items"), usecols=["itemid", "label", "category"])
    proc = proc.merge(ditems, on="itemid", how="left").rename(columns={"label": "proc_label",
                                                                       "category": "proc_category"})
    if categories:                                   # keep only therapeutic, lab-moving procedures
        proc = proc[proc["proc_category"].isin(categories)].reset_index(drop=True)
    return proc


def _core_lab_rows(root: Path, itemids: set[int], candidate_hadm: set[int], chunksize: int) -> pd.DataFrame:
    cols = ["hadm_id", "itemid", "charttime", "valuenum", "valueuom", "flag",
            "ref_range_lower", "ref_range_upper"]
    parts = []
    for i, chunk in enumerate(pd.read_csv(_gz(root, "hosp", "labevents"), usecols=cols,
                                          chunksize=chunksize, parse_dates=["charttime"], low_memory=False)):
        chunk = chunk[chunk["itemid"].isin(itemids)].dropna(subset=["hadm_id"])
        if chunk.empty:
            print(f"  labevents chunk {i}", flush=True); continue
        chunk["hadm_id"] = chunk["hadm_id"].astype("int64")
        chunk = chunk[chunk["hadm_id"].isin(candidate_hadm)]
        if not chunk.empty:
            parts.append(chunk)
        print(f"  labevents chunk {i}", flush=True)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=cols)


def build_eligible_index(cfg: dict) -> pd.DataFrame:
    import numpy as np
    root, od = mimic_root(cfg), out_dir(cfg)
    cc = cfg["cohort"]
    win = float(cc["post_window_h"]); mn_pre = int(cc["min_pre"]); mn_post = int(cc["min_post"])

    cats = cc.get("procedure_categories")
    # Always (re)build the filtered procedure list (cheap). Reuse the expensive core-lab scan if present.
    print("[1/3] ICU procedures (therapeutic categories) ...", flush=True)
    proc = _procedures(root, cats)
    print(f"      {len(proc):,} therapeutic procedures across {proc['hadm_id'].nunique():,} admissions")
    if cc.get("diagnosis_filter") == "cardiovascular_primary":
        from qgen.mimic_features import cardiovascular_hadms
        cv = cardiovascular_hadms(_gz(root, "hosp", "diagnoses_icd"), primary_only=True)
        proc = proc[proc["hadm_id"].isin(cv)].reset_index(drop=True)
        print(f"      CV-filtered -> {len(proc):,} procedures across {proc['hadm_id'].nunique():,} cardiovascular admissions")
    proc.to_parquet(od / "procedures.parquet", index=False)
    if (od / "core_labs.parquet").exists():
        print("[2-3] reusing existing core_labs.parquet", flush=True)
        labs = pd.read_parquet(od / "core_labs.parquet")
        labs["charttime"] = pd.to_datetime(labs["charttime"])
    else:
        print("[2/3] core-lab itemids ...", flush=True)
        items = core_lab_itemids(root, cc["core_labs"])
        itemid_set = set(items["itemid"]); id2label = dict(zip(items["itemid"], items["label"]))
        print("[3/3] core-lab rows (restricted scan) ...", flush=True)
        labs = _core_lab_rows(root, itemid_set, set(proc["hadm_id"]), int(cc["chunksize"]))
        labs["label"] = labs["itemid"].map(id2label)
        labs.to_parquet(od / "core_labs.parquet", index=False)

    # Pre-index per-hadm (charttime, label) arrays once → fast numpy eligibility per procedure.
    # Group by hadm ONLY (restricted to therapeutic admissions) to keep it to ~33k groups.
    print("[4] indexing core labs by hadm ...", flush=True)
    labs = labs.dropna(subset=["charttime", "valuenum"])
    labs = labs[labs["hadm_id"].isin(set(proc["hadm_id"]))]
    arr_by = {h: (sub["charttime"].values.astype("datetime64[ns]"), sub["label"].to_numpy())
              for h, sub in labs.groupby("hadm_id")}
    print(f"      indexed {len(arr_by):,} admissions", flush=True)

    icu = pd.read_csv(_gz(root, "icu", "icustays"), usecols=["stay_id", "intime"], parse_dates=["intime"])
    intime = dict(zip(icu["stay_id"], icu["intime"]))
    gap = float(cc["min_procedure_gap_h"]); min_traj = int(cc["min_labs_with_traj"])
    target = int(cc.get("pool_size", 5000)) * 2          # collect 2x buffer, then sample the pool

    # shuffle procedures (seeded) and early-stop once we have enough eligible
    order = np.random.default_rng(int(cfg.get("seed", 0))).permutation(len(proc))
    win_ns = np.timedelta64(int(win * 3600), "s")
    rows = []
    print(f"[5] eligibility (shuffled, early-stop at {target}) ...", flush=True)
    core_set = list(cc["core_labs"])
    for k, ridx in enumerate(order):
        r = proc.iloc[ridx]
        entry = arr_by.get(r["hadm_id"])
        if entry is None:
            continue
        ct, labels = entry
        it = intime.get(r["stay_id"])
        start = np.datetime64(r["starttime"])
        if it is not None and (start - np.datetime64(it)) < np.timedelta64(int(gap * 3600), "s"):
            continue
        n_traj = 0
        for lab in core_set:
            m = labels == lab
            if not m.any():
                continue
            t = ct[m]
            pre = int((t <= start).sum())
            post = int(((t > start) & (t <= start + win_ns)).sum())
            if pre >= mn_pre and post >= mn_post:
                n_traj += 1
        if n_traj >= min_traj:
            rows.append({"hadm_id": int(r["hadm_id"]), "stay_id": int(r["stay_id"]),
                         "subject_id": int(r["subject_id"]), "proc_itemid": int(r["itemid"]),
                         "proc_label": str(r["proc_label"]), "starttime": r["starttime"],
                         "n_traj_labs": n_traj})
            if len(rows) >= target:
                print(f"   reached {target} eligible after scanning {k+1} procedures"); break

    elig = pd.DataFrame(rows).sort_values(["hadm_id", "starttime"]).reset_index(drop=True)
    elig["proc_uid"] = [f"p{i:06d}" for i in range(len(elig))]
    elig.to_parquet(od / "eligible_index.parquet", index=False)
    print(f"\neligible procedures: {len(elig):,}")
    if len(elig):
        print(elig["n_traj_labs"].describe().round(2).to_string())
        print("top procedures:\n" + elig["proc_label"].value_counts().head(12).to_string())
    return elig


def sample_pool(cfg: dict, elig: pd.DataFrame) -> pd.DataFrame:
    import numpy as np
    n = min(int(cfg["cohort"].get("pool_size", 5000)), len(elig))
    rng = np.random.default_rng(int(cfg.get("seed", 0)))
    idx = rng.choice(len(elig), size=n, replace=False)
    pool = elig.iloc[sorted(idx)].reset_index(drop=True)
    pool.to_parquet(out_dir(cfg) / "pool.parquet", index=False)
    print(f"sampled pool of {len(pool):,} procedures")
    return pool


if __name__ == "__main__":
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else None)
    elig = build_eligible_index(cfg)
    if len(elig):
        sample_pool(cfg, elig)
