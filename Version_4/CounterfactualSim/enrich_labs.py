#!/usr/bin/env python3
"""
enrich_labs.py — chunk-extract a baseline lab panel for the CAD cohort from the 2.4GB
labevents, so the propensity/outcome models see prognostic severity (troponin, BNP,
creatinine, HbA1c, LDL, …), not just demographics + comorbidity codes.

Filters labevents by (a) a targeted CAD panel of itemids and (b) the cohort's admissions,
keeping the EARLIEST value per (hadm, itemid) as the baseline. Saves cad_labs.parquet.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

LAB = Path("/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/2physionet.org/files/mimiciv/3.1/hosp/labevents.csv.gz")
COH = Path(__file__).resolve().parent / "cad_cohort_full.parquet"
OUT = Path(__file__).resolve().parent / "cad_labs.parquet"

# canonical MIMIC-IV serum panel itemids (prognostically relevant for CAD)
PANEL = {50912: "creatinine", 51222: "hemoglobin", 51221: "hematocrit", 51265: "platelet",
         51301: "wbc", 50983: "sodium", 50971: "potassium", 50882: "bicarbonate",
         51006: "bun", 50931: "glucose", 51003: "troponin_t", 50963: "ntprobnp",
         50852: "hba1c", 50905: "ldl"}


def main():
    coh = pd.read_parquet(COH)
    hadms = set(int(h) for h in coh.hadm_id.dropna().unique())
    print(f"[labs] extracting {len(PANEL)} labs for {len(hadms):,} cohort admissions from labevents …")

    keep = []
    n_rows = 0
    for ch in pd.read_csv(LAB, chunksize=2_000_000,
                          usecols=["hadm_id", "itemid", "charttime", "valuenum"]):
        n_rows += len(ch)
        ch = ch[ch.itemid.isin(PANEL)].dropna(subset=["valuenum", "hadm_id"])
        ch = ch[ch.hadm_id.astype("int64").isin(hadms)]
        if len(ch):
            keep.append(ch)
        print(f"\r[labs]   scanned {n_rows:,} rows, kept {sum(len(k) for k in keep):,}", end="")
    print()
    lab = pd.concat(keep, ignore_index=True)
    lab["hadm_id"] = lab.hadm_id.astype("int64")
    lab = lab.sort_values("charttime").groupby(["hadm_id", "itemid"], as_index=False).first()  # earliest
    lab["name"] = lab.itemid.map(PANEL)
    panel = lab.pivot_table(index="hadm_id", columns="name", values="valuenum", aggfunc="first")
    panel.columns = ["lab_" + c for c in panel.columns]
    panel.to_parquet(OUT)
    cov = panel.notna().mean().sort_values()
    print(f"[labs] saved {OUT.name}: {panel.shape[0]:,} admissions x {panel.shape[1]} labs")
    print("[labs] coverage (fraction of admissions with the lab):")
    print(cov.round(2).to_string())


if __name__ == "__main__":
    main()
