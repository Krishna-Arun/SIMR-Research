"""Eligible-admission cohort index for Benchmark A.

Selects MIMIC-IV ICU admissions that have BOTH dense labs AND >=1 microbiology event — the
admissions on which a question can genuinely *require* labs + micro to answer.

Strategy (scan the 2.5 GB labevents at most twice, never per-question):
  1. micro set      — admissions with >= require_micro_events microbiology events   (cheap, 117 MB)
  2. ICU set        — admissions with an ICU stay (+ intime/outtime for time-zero)   (cheap, 3 MB)
  3. candidate      — micro ∩ ICU                                                    (small)
  4. lab density    — ONE chunked pass over labevents restricted to `candidate`:
                      per-admission n_labs, n_distinct_itemids, n_abnormal
  5. threshold      — apply cohort.min_* → eligible_index.parquet
  6. (optional)     — SECOND chunked pass collecting only eligible rows → per-admission
                      lab/micro parquet slices for fast context reads.

Run:  python -m qgen.cohort            (or)   python qgen/cohort.py [config.yaml]
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

from qgen.config import load_config, mimic_root, out_dir


def _gz(root: Path, subdir: str, table: str) -> Path:
    p = root / subdir / f"{table}.csv.gz"
    if not p.exists():
        alt = root / subdir / f"{table}.csv"
        if alt.exists():
            return alt
        raise FileNotFoundError(f"missing MIMIC table: {p}")
    return p


# ── steps 1-2: cheap sets ────────────────────────────────────────────────────
def _micro_admissions(root: Path, min_events: int) -> pd.Series:
    """hadm_id -> micro event count, filtered to >= min_events."""
    micro = pd.read_csv(_gz(root, "hosp", "microbiologyevents"), usecols=["hadm_id"], low_memory=False)
    counts = micro["hadm_id"].dropna().astype("int64").value_counts()
    return counts[counts >= min_events]


def _icu_admissions(root: Path) -> pd.DataFrame:
    """One row per hadm_id with first ICU intime / last outtime / subject_id."""
    icu = pd.read_csv(_gz(root, "icu", "icustays"),
                      usecols=["subject_id", "hadm_id", "stay_id", "intime", "outtime", "los"],
                      parse_dates=["intime", "outtime"], low_memory=False)
    icu = icu.dropna(subset=["hadm_id"])
    icu["hadm_id"] = icu["hadm_id"].astype("int64")
    agg = (icu.sort_values("intime")
              .groupby("hadm_id")
              .agg(subject_id=("subject_id", "first"),
                   icu_intime=("intime", "first"),
                   icu_outtime=("outtime", "last"),
                   n_icu_stays=("stay_id", "nunique"),
                   icu_los_days=("los", "sum")))
    return agg.reset_index()


# ── step 4: chunked labevents density over the candidate set ──────────────────
def _lab_density(root: Path, candidate: set[int], chunksize: int) -> pd.DataFrame:
    n_labs: dict[int, int] = defaultdict(int)
    itemids: dict[int, set] = defaultdict(set)
    n_abn: dict[int, int] = defaultdict(int)

    cols = ["hadm_id", "itemid", "valuenum", "flag"]
    reader = pd.read_csv(_gz(root, "hosp", "labevents"), usecols=cols,
                         chunksize=chunksize, low_memory=False)
    for i, chunk in enumerate(reader):
        chunk = chunk.dropna(subset=["hadm_id"])
        chunk["hadm_id"] = chunk["hadm_id"].astype("int64")
        chunk = chunk[chunk["hadm_id"].isin(candidate)]
        if chunk.empty:
            continue
        has_val = chunk["valuenum"].notna()
        abn = chunk["flag"].notna() & (chunk["flag"].astype(str).str.strip() != "")
        for hid, iid, hv, ab in zip(chunk["hadm_id"], chunk["itemid"], has_val, abn):
            if hv:
                n_labs[hid] += 1
            itemids[hid].add(iid)
            if ab:
                n_abn[hid] += 1
        print(f"  labevents chunk {i} processed ({len(candidate)} candidates tracked)", flush=True)

    rows = [{"hadm_id": h, "n_labs": n_labs[h], "n_distinct_itemids": len(itemids[h]),
             "n_abnormal": n_abn[h]} for h in itemids]
    return pd.DataFrame(rows)


def build_eligible_index(cfg: dict) -> pd.DataFrame:
    root, od = mimic_root(cfg), out_dir(cfg)
    cc = cfg["cohort"]

    print("[1/5] microbiology admissions ...", flush=True)
    micro = _micro_admissions(root, int(cc["require_micro_events"]))
    print(f"      {len(micro):,} admissions with >= {cc['require_micro_events']} micro event(s)")

    print("[2/5] ICU admissions ...", flush=True)
    icu = _icu_admissions(root)
    print(f"      {len(icu):,} admissions with an ICU stay")

    print("[3/5] candidate = micro ∩ ICU ...", flush=True)
    candidate = set(micro.index) & set(icu["hadm_id"])
    if cc.get("diagnosis_filter") == "cardiovascular_primary":
        from qgen.mimic_features import cardiovascular_hadms
        cv = cardiovascular_hadms(_gz(root, "hosp", "diagnoses_icd"), primary_only=True)
        candidate &= cv
        print(f"      CV-filtered candidate = micro ∩ ICU ∩ cardiovascular")
    print(f"      {len(candidate):,} candidate admissions")

    print("[4/5] labevents density (one chunked pass) ...", flush=True)
    dens = _lab_density(root, candidate, int(cc["chunksize"]))

    print("[5/5] apply thresholds + join ...", flush=True)
    df = dens.merge(icu, on="hadm_id", how="inner")
    df["n_micro"] = df["hadm_id"].map(micro)
    elig = df[(df["n_distinct_itemids"] >= int(cc["min_distinct_labs"])) &
              (df["n_labs"] >= int(cc["min_lab_measurements"]))].copy()
    elig = elig.sort_values("hadm_id").reset_index(drop=True)

    out_path = od / "eligible_index.parquet"
    elig.to_parquet(out_path, index=False)
    print(f"\nEligible admissions: {len(elig):,}  ->  {out_path}")
    if len(elig):
        print(elig[["n_labs", "n_distinct_itemids", "n_abnormal", "n_micro", "icu_los_days"]]
              .describe().round(1).to_string())
    return elig


# ── step 6: consolidated lab/micro slices for a pre-sampled POOL ──────────────
# Memory-safe: we materialize rows only for a seeded pool of `pool_size` eligible admissions (NOT all
# 64k — concatenating ~19M lab rows OOMs). Two consolidated, hadm-sorted parquet files (not 60k tiny
# files). The orchestrator samples from this same pool, so it stays a uniform random sample.
def sample_pool(cfg: dict, eligible: pd.DataFrame) -> list[int]:
    import numpy as np
    n = min(int(cfg["cohort"].get("pool_size", 5000)), len(eligible))
    rng = np.random.default_rng(int(cfg.get("seed", 0)))
    idx = rng.choice(len(eligible), size=n, replace=False)
    return sorted(int(h) for h in eligible["hadm_id"].to_numpy()[idx])


def materialize_slices(cfg: dict, eligible: pd.DataFrame | None = None) -> None:
    root, od = mimic_root(cfg), out_dir(cfg)
    if eligible is None:
        eligible = pd.read_parquet(od / "eligible_index.parquet")
    pool = sample_pool(cfg, eligible)
    pool_set = set(pool)
    pd.DataFrame({"hadm_id": pool}).to_parquet(od / "pool.parquet", index=False)
    print(f"materializing slices for a pool of {len(pool):,} admissions", flush=True)

    dlab = pd.read_csv(_gz(root, "hosp", "d_labitems"), usecols=["itemid", "label", "fluid", "category"])

    print("collecting pool lab rows (second chunked pass) ...", flush=True)
    parts = []
    cols = ["hadm_id", "itemid", "charttime", "valuenum", "valueuom", "flag", "ref_range_lower", "ref_range_upper"]
    for i, chunk in enumerate(pd.read_csv(_gz(root, "hosp", "labevents"), usecols=cols,
                                          chunksize=int(cfg["cohort"]["chunksize"]),
                                          parse_dates=["charttime"], low_memory=False)):
        chunk = chunk.dropna(subset=["hadm_id"])
        chunk["hadm_id"] = chunk["hadm_id"].astype("int64")
        chunk = chunk[chunk["hadm_id"].isin(pool_set)]
        if not chunk.empty:
            parts.append(chunk.merge(dlab, on="itemid", how="left"))
        print(f"  labevents chunk {i}", flush=True)
    labs = pd.concat(parts, ignore_index=True).sort_values("hadm_id").reset_index(drop=True)
    labs.to_parquet(od / "eligible_labs.parquet", index=False)
    print(f"  wrote eligible_labs.parquet ({len(labs):,} rows, {labs.hadm_id.nunique()} admissions)")

    print("collecting pool micro rows ...", flush=True)
    mcols = ["hadm_id", "charttime", "chartdate", "spec_type_desc", "test_name", "org_name",
             "ab_name", "interpretation"]
    micro = pd.read_csv(_gz(root, "hosp", "microbiologyevents"), usecols=mcols, low_memory=False)
    micro = micro.dropna(subset=["hadm_id"])
    micro["hadm_id"] = micro["hadm_id"].astype("int64")
    micro = micro[micro["hadm_id"].isin(pool_set)]
    micro["charttime"] = pd.to_datetime(micro["charttime"].fillna(micro["chartdate"]), errors="coerce")
    micro = micro.sort_values("hadm_id").reset_index(drop=True)
    micro.to_parquet(od / "eligible_micro.parquet", index=False)
    print(f"  wrote eligible_micro.parquet ({len(micro):,} rows)")


def load_index(cfg: dict) -> pd.DataFrame:
    return pd.read_parquet(out_dir(cfg) / "eligible_index.parquet")


if __name__ == "__main__":
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else None)
    elig = build_eligible_index(cfg)
    if cfg["cohort"].get("materialize_slices") and len(elig):
        materialize_slices(cfg, elig)
