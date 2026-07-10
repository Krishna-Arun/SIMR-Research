"""Load MIMIC-IV tables (demo, full v3.1, or cardiac subset) as pandas DataFrames.

Handles both plain ``.csv`` (demo 2.2) and gzipped ``.csv.gz`` (full v3.1) layouts by globbing
``hosp/<table>.csv*`` / ``icu/<table>.csv*``.

Required tables for this project: admissions, diagnoses_icd, procedures_icd, prescriptions,
labevents, patients, icustays.

Research environment only — not a clinical tool.
"""
from __future__ import annotations

import glob
import os
from typing import Optional

import pandas as pd

from utils.common import get_logger

log = get_logger("load_mimic")

# Module -> subdir under the dataset root. MIMIC-IV splits hosp/ and icu/.
TABLE_SUBDIR = {
    "admissions": "hosp",
    "patients": "hosp",
    "diagnoses_icd": "hosp",
    "procedures_icd": "hosp",
    "prescriptions": "hosp",
    "labevents": "hosp",
    "d_labitems": "hosp",
    "icustays": "icu",
}

# Datetime columns to parse per table (only those present are parsed).
DATETIME_COLS = {
    "admissions": ["admittime", "dischtime", "deathtime", "edregtime", "edouttime"],
    "patients": ["dod"],
    "procedures_icd": ["chartdate"],
    "prescriptions": ["starttime", "stoptime"],
    "labevents": ["charttime", "storetime"],
    "icustays": ["intime", "outtime"],
}


def _root(cfg: dict) -> str:
    src = cfg["data"].get("source", "demo")
    if src == "demo":
        return cfg["data"]["demo_root"]
    if src == "full":
        return cfg["data"]["full_root"]
    if src == "cardiac":
        return cfg["data"].get("cardiac_root", cfg["data"]["demo_root"])
    raise ValueError(f"unknown data.source={src!r}")


def _find_table(root: str, table: str) -> Optional[str]:
    sub = TABLE_SUBDIR.get(table, "hosp")
    matches = sorted(glob.glob(os.path.join(root, sub, f"{table}.csv*")))
    return matches[0] if matches else None


def load_table(cfg: dict, table: str, usecols: Optional[list] = None,
               nrows: Optional[int] = None) -> pd.DataFrame:
    """Load one MIMIC table. Returns an empty DataFrame if the file is missing."""
    root = _root(cfg)
    path = _find_table(root, table)
    if path is None:
        log.warning("table %s not found under %s — returning empty frame", table, root)
        return pd.DataFrame()
    log.info("loading %s from %s", table, path)
    df = pd.read_csv(path, usecols=usecols, nrows=nrows, low_memory=False)
    for col in DATETIME_COLS.get(table, []):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def load_all(cfg: dict) -> dict:
    """Load every table this project consumes. Missing tables come back empty."""
    tables = ["admissions", "patients", "diagnoses_icd", "procedures_icd",
              "prescriptions", "labevents", "icustays"]
    out = {t: load_table(cfg, t) for t in tables}
    for t, df in out.items():
        log.info("  %-16s rows=%d cols=%d", t, len(df), df.shape[1] if len(df) else 0)
    return out
