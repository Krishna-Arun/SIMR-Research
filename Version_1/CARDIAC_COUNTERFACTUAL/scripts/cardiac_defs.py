"""
cardiac_defs.py  —  self-contained shared definitions for the cardiac counterfactual benchmark.

Arm codes, comorbidity taxonomy, raw-data paths, lab/notes/micro extractors, and the SOFA-like
severity score. Extracted from the original project so this folder stands alone (no backward
imports). Reads the MIMIC-IV cardiac-ext subset (shared raw data).
"""

import pandas as pd
import numpy as np
from pathlib import Path

# ── raw data (MIMIC-IV cardiac-ext subset) ──────────────────────────────────
D = Path("/scratch/users/karun09/physionet.org/files/mimic-iv-ext-cardiac-disease/1.0.0")
LABS_FILE = D / "heart_labevents_examination_group.csv"
PROC_FILE = D / "heart_procedures.csv"
DIAG_FILE = D / "heart_diagnoses_all_true.csv"
NOTES_FILE = D / "heart_diagnoses.csv"
MICRO_FILE = D / "heart_microbiologyevents.csv"

# ── treatment arms ──────────────────────────────────────────────────────────
REVASC_CODES = {"0066", "3607", "3606", "0045", "0046", "0047", "027034Z"}      # PCI / PTCA / stent
CABG_ICD9 = {"3610", "3611", "3612", "3613", "3614", "3615", "3616", "3617", "3619"}
PCI_SINGLE_VESSEL = {"0040"}
PCI_MULTI_VESSEL = {"0041", "0042", "0043"}


def arm_for_codes(codes):
    """Assign an admission to ONE treated arm by priority (CABG > PCI), else None."""
    if any(c.startswith("021") or c in CABG_ICD9 for c in codes):
        return "cabg"
    if codes & REVASC_CODES:
        return "pci"
    return None


def pci_vessel_group(codes):
    if codes & PCI_MULTI_VESSEL:
        return "multi"
    if codes & PCI_SINGLE_VESSEL:
        return "single"
    return "unknown"

# ── comorbidities (ICD-10 prefixes) ─────────────────────────────────────────
COMORBIDITIES = {
    "diabetes": ("E10", "E11"), "hypertension": ("I10", "I11", "I12", "I13"),
    "ckd": ("N18", "N17"), "heart_failure": ("I50",), "afib": ("I48",),
    "prior_mi": ("I21", "I22", "I252"), "hyperlipidemia": ("E78",),
    "copd": ("J44",), "cad": ("I25",), "valve": ("I34", "I35"),
}


def build_comorbidity_vector(codes):
    vec = {k: 0 for k in COMORBIDITIES}
    for code in codes:
        c = str(code)
        for name, prefixes in COMORBIDITIES.items():
            if any(c.startswith(p) for p in prefixes):
                vec[name] = 1
    return vec


def _clip(text, n=1500):
    t = str(text).strip()
    return t[:n] + (" …[truncated]" if len(t) > n else "")


# ── pre-index extractors (charttime <= anchor) ──────────────────────────────
def summarize_all_labs(adm_labs, anchor):
    out = {}
    if adm_labs is None or len(adm_labs) == 0:
        return out
    pre = adm_labs[adm_labs["charttime"] <= anchor]
    for label, md in pre.groupby("label"):
        md = md.sort_values("charttime")
        vals = [float(v) for v in md["valuenum"].tolist()]
        if not vals:
            continue
        unit = str(md["valueuom"].iloc[-1]) if "valueuom" in md and pd.notna(md["valueuom"].iloc[-1]) else ""
        out[str(label)] = {"n": len(vals), "first": round(vals[0], 3), "latest": round(vals[-1], 3),
                           "min": round(min(vals), 3), "max": round(max(vals), 3), "unit": unit}
    return out


def pre_labs_full(adm_labs_all, anchor):
    """FULL timestamped pre-index series for every lab (charttime <= anchor)."""
    out = {}
    if adm_labs_all is None or len(adm_labs_all) == 0:
        return out
    pre = adm_labs_all[adm_labs_all["charttime"] <= anchor]
    for label, md in pre.groupby("label"):
        md = md.sort_values("charttime")
        series = [{"value": round(float(v), 3),
                   "hours_from_index": round((t - anchor).total_seconds() / 3600.0, 1)}
                  for v, t in zip(md["valuenum"], md["charttime"]) if pd.notna(v)]
        if series:
            out[str(label)] = series
    return out


def summarize_micro(adm_micro, anchor, cap=40):
    out = []
    if adm_micro is None or len(adm_micro) == 0:
        return out
    pre = adm_micro[adm_micro["charttime"] <= anchor].sort_values("charttime")
    for _, r in pre.iterrows():
        org, interp = r.get("org_name"), r.get("interpretation")
        out.append({"hours_from_index": round((r["charttime"] - anchor).total_seconds() / 3600.0, 1),
                    "specimen": str(r.get("spec_type_desc", "") or ""), "test": str(r.get("test_name", "") or ""),
                    "organism": str(org) if pd.notna(org) else "", "interpretation": str(interp) if pd.notna(interp) else ""})
    return out[:cap]


# ── SOFA-like severity (from latest pre-index labs dict) ─────────────────────
def compute_severity_score(labs):
    """Simplified SOFA in [0,24] from a {lab_name: value} dict."""
    s = 0
    if "Creatinine" in labs:
        cr = labs["Creatinine"]
        s += 0 if cr < 1.1 else 1 if cr < 1.9 else 2 if cr < 3.5 else 3 if cr < 4.9 else 4
    if "Platelets" in labs:
        p = labs["Platelets"]
        s += 0 if p >= 150 else 1 if p >= 100 else 2 if p >= 50 else 3 if p >= 20 else 4
    if "WBC" in labs:
        w = labs["WBC"]
        s += 0 if 4.5 <= w <= 11.0 else 2 if w < 1.0 else 1 if w > 20.0 else 0
    return min(s, 24)
