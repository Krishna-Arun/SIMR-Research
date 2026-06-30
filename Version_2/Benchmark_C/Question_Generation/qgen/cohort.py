"""Benchmark C cohort: build baseline covariates per eligible ICU procedure, then generate
overlap-matched patient pairs with DIFFERENT procedures (qgen.overlap).

Reuses Benchmark B's already-scanned artifacts (cohort.reuse_from): procedures.parquet,
core_labs.parquet, eligible_index.parquet — so we do NOT rescan the 2.5 GB labevents again.

Outputs:
  covariates.parquet         one row per eligible procedure (baseline core labs + comorbidities + age)
  matched_pairs.parquet      overlap-matched (A,B) pairs with different procedures + shown_post_owner
  overlap_diagnostic.json    per procedure-pair AUC / SMD diagnostics
  pool.parquet               the matched pairs (sampling unit for generation)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from qgen.config import load_config, mimic_root, out_dir
from qgen.mimic_features import COMORBIDITIES, build_comorbidity_vector
from qgen.overlap import build_pairs


def _reuse(cfg) -> Path:
    return Path(cfg["cohort"]["reuse_from"])


def _gz(root, subdir, table):
    p = root / subdir / f"{table}.csv.gz"
    return p if p.exists() else root / subdir / f"{table}.csv"


def build_covariates(cfg: dict) -> pd.DataFrame:
    root, od, src = mimic_root(cfg), out_dir(cfg), _reuse(cfg)
    core = list(cfg["cohort"]["core_labs"])
    elig = pd.read_parquet(src / "eligible_index.parquet")
    labs = pd.read_parquet(src / "core_labs.parquet", columns=["hadm_id", "label", "charttime", "valuenum"])
    labs["charttime"] = pd.to_datetime(labs["charttime"], errors="coerce")
    labs_by = {h: g for h, g in labs.groupby("hadm_id")}

    patients = pd.read_csv(_gz(root, "hosp", "patients"), usecols=["subject_id", "anchor_age"]).set_index("subject_id")
    diag = pd.read_csv(_gz(root, "hosp", "diagnoses_icd"), usecols=["hadm_id", "icd_code"])
    diag_by = {h: g["icd_code"].astype(str).tolist() for h, g in diag.groupby("hadm_id")}

    rows = []
    for hadm, eg in elig.groupby("hadm_id"):
        g = labs_by.get(hadm)
        if g is None:
            continue
        comorbid = build_comorbidity_vector(diag_by.get(hadm, []))
        for r in eg.itertuples():
            start = pd.to_datetime(r.starttime)
            pre = g[g["charttime"] <= start]
            rec = {"proc_uid": r.proc_uid, "hadm_id": int(hadm), "subject_id": int(r.subject_id),
                   "proc_label": str(r.proc_label), "starttime": start}
            for lab in core:
                gl = pre[pre["label"] == lab].sort_values("charttime")
                rec[f"lab_{lab}"] = float(gl["valuenum"].iloc[-1]) if len(gl) else np.nan
            for k, v in comorbid.items():
                rec[f"cm_{k}"] = v
            age = patients.loc[r.subject_id, "anchor_age"] if r.subject_id in patients.index else np.nan
            rec["age"] = float(age) if pd.notna(age) else np.nan
            rows.append(rec)
    df = pd.DataFrame(rows)
    # median-impute missing lab/age covariates; fillna(0) catches any column that is entirely NaN
    # (e.g. a core lab never measured pre-procedure across the cohort), then drop zero-variance cols.
    cov_cols = [c for c in df.columns if c.startswith("lab_") or c.startswith("cm_") or c == "age"]
    df[cov_cols] = df[cov_cols].apply(lambda c: c.fillna(c.median())).fillna(0.0)
    keep = [c for c in cov_cols if df[c].nunique() > 1]   # drop constant covariates
    drop = [c for c in cov_cols if c not in keep]
    if drop:
        print(f"   dropped {len(drop)} constant covariates: {drop}")
    df = df.drop(columns=drop)
    df.to_parquet(od / "covariates.parquet", index=False)
    print(f"covariates for {len(df):,} eligible procedures, {len(cov_cols)} covariates")
    return df


def build(cfg: dict):
    od = out_dir(cfg)
    df = build_covariates(cfg)
    cov_cols = [c for c in df.columns if c.startswith("lab_") or c.startswith("cm_") or c == "age"]
    pairs, diags = build_pairs(df, cov_cols, cfg)
    json.dump(diags, open(od / "overlap_diagnostic.json", "w"), indent=2)
    if len(pairs) == 0:
        print("WARN: no matched pairs passed the overlap gate — relax caliper/max_smd."); return pairs
    # assign which patient's post-state is shown (seeded)
    rng = np.random.default_rng(int(cfg.get("seed", 0)))
    pairs = pairs.reset_index(drop=True)
    pairs["pair_uid"] = [f"c{i:06d}" for i in range(len(pairs))]
    pairs["shown_post_owner"] = np.where(rng.random(len(pairs)) < 0.5, "A", "B")
    pairs.to_parquet(od / "matched_pairs.parquet", index=False)
    pairs.to_parquet(od / "pool.parquet", index=False)
    print(f"\nmatched pairs: {len(pairs):,}  ->  matched_pairs.parquet")
    print("procedure-pair coverage:\n" +
          pairs.groupby(["procA", "procB"]).size().sort_values(ascending=False).head(12).to_string())
    return pairs


if __name__ == "__main__":
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else None)
    build(cfg)
