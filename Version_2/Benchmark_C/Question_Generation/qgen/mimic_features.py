"""Pure per-admission feature extractors (vendored from
Version_1/CARDIAC_COUNTERFACTUAL/scripts/cardiac_defs.py so Version_2 stays self-contained).

All extractors take a per-admission DataFrame already filtered to one hadm_id plus a `anchor`
(time-zero) Timestamp, and return ONLY pre-anchor data (charttime <= anchor) — no leakage past
time-zero. Expected columns:
  labs:  charttime, label, valuenum, valueuom, flag, ref_range_lower, ref_range_upper
  micro: charttime, spec_type_desc, test_name, org_name, ab_name, interpretation
"""
from __future__ import annotations

import pandas as pd

# ICD-10 comorbidity prefixes (from cardiac_defs.COMORBIDITIES)
COMORBIDITIES = {
    "diabetes": ("E10", "E11"), "hypertension": ("I10", "I11", "I12", "I13"),
    "ckd": ("N18", "N17"), "heart_failure": ("I50",), "afib": ("I48",),
    "prior_mi": ("I21", "I22", "I252"), "hyperlipidemia": ("E78",),
    "copd": ("J44",), "cad": ("I25",), "valve": ("I34", "I35"),
    "sepsis": ("A40", "A41", "R652"), "aki": ("N17",), "pneumonia": ("J18", "J15"),
    "uti": ("N39",), "stroke": ("I63", "I61"),
}


def build_comorbidity_vector(codes) -> dict[str, int]:
    vec = {k: 0 for k in COMORBIDITIES}
    for code in codes:
        c = str(code)
        for name, prefixes in COMORBIDITIES.items():
            if any(c.startswith(p) for p in prefixes):
                vec[name] = 1
    return vec


def summarize_all_labs(adm_labs: pd.DataFrame, anchor) -> dict:
    """Pre-anchor summary per lab: n / first / latest / min / max / unit / any_abnormal."""
    out: dict = {}
    if adm_labs is None or len(adm_labs) == 0:
        return out
    pre = adm_labs[adm_labs["charttime"] <= anchor]
    for label, md in pre.groupby("label"):
        md = md.sort_values("charttime")
        vals = [float(v) for v in md["valuenum"].tolist() if pd.notna(v)]
        if not vals:
            continue
        unit = ""
        if "valueuom" in md and pd.notna(md["valueuom"].iloc[-1]):
            unit = str(md["valueuom"].iloc[-1])
        any_abn = False
        if "flag" in md:
            any_abn = bool((md["flag"].notna() & (md["flag"].astype(str).str.strip() != "")).any())
        out[str(label)] = {"n": len(vals), "first": round(vals[0], 3), "latest": round(vals[-1], 3),
                           "min": round(min(vals), 3), "max": round(max(vals), 3), "unit": unit,
                           "any_abnormal": any_abn}
    return out


def pre_labs_full(adm_labs: pd.DataFrame, anchor) -> dict:
    """FULL timestamped pre-anchor series per lab: {label: [{value, hours_from_index, abnormal}]}"""
    out: dict = {}
    if adm_labs is None or len(adm_labs) == 0:
        return out
    pre = adm_labs[adm_labs["charttime"] <= anchor]
    for label, md in pre.groupby("label"):
        md = md.sort_values("charttime")
        series = []
        for _, r in md.iterrows():
            if pd.isna(r["valuenum"]):
                continue
            abn = bool(pd.notna(r.get("flag")) and str(r.get("flag")).strip() != "")
            series.append({"value": round(float(r["valuenum"]), 3),
                           "hours_from_index": round((r["charttime"] - anchor).total_seconds() / 3600.0, 1),
                           "abnormal": abn})
        if series:
            out[str(label)] = series
    return out


def summarize_micro(adm_micro: pd.DataFrame, anchor, cap: int = 60) -> list[dict]:
    out: list[dict] = []
    if adm_micro is None or len(adm_micro) == 0:
        return out
    pre = adm_micro[adm_micro["charttime"] <= anchor].sort_values("charttime")
    for _, r in pre.iterrows():
        org, interp = r.get("org_name"), r.get("interpretation")
        out.append({"hours_from_index": round((r["charttime"] - anchor).total_seconds() / 3600.0, 1),
                    "specimen": str(r.get("spec_type_desc", "") or ""),
                    "test": str(r.get("test_name", "") or ""),
                    "antibiotic": str(r.get("ab_name", "") or "") if pd.notna(r.get("ab_name")) else "",
                    "organism": str(org) if pd.notna(org) else "",
                    "interpretation": str(interp) if pd.notna(interp) else ""})
    return out[:cap]


def summarize_meds(adm_meds: pd.DataFrame, anchor, cap: int = 80) -> list[dict]:
    """Pre-anchor medications, names/dates only, de-duplicated by drug:
    [{drug, route, hours_from_index}]. Source rows: hadm_id, starttime, drug, route."""
    out: list[dict] = []
    if adm_meds is None or len(adm_meds) == 0 or "starttime" not in adm_meds:
        return out
    pre = adm_meds[adm_meds["starttime"] <= anchor].sort_values("starttime")
    seen: set[str] = set()
    for _, r in pre.iterrows():
        drug = str(r.get("drug", "") or "").strip()
        if not drug or drug.lower() in seen:
            continue
        seen.add(drug.lower())
        out.append({"drug": drug, "route": str(r.get("route", "") or ""),
                    "hours_from_index": round((r["starttime"] - anchor).total_seconds() / 3600.0, 1)})
    return out[:cap]


# ── cardiovascular cohort filter (cardiac + major vessel; excludes cerebrovascular I60-I69 / 430-438) ──
def is_cardiovascular(code, version) -> bool:
    """STRICTLY HEART (cardiac) primary diagnosis. Excludes peripheral-vascular (I70-I89 / 440-459),
    hypertension-only (I10/I12/I15 / 401,403,405), cerebrovascular (I60-I69 / 430-438), and
    pulmonary-circulation (I26-I28 / 415-417)."""
    c = str(code)
    if int(version) == 10:
        p = c[:3]
        return (p in ("I11", "I13")          # hypertensive HEART disease
                or "I01" <= p <= "I09"        # rheumatic / inflammatory heart disease
                or "I20" <= p <= "I25"        # ischemic heart disease / MI / angina
                or "I30" <= p <= "I52")       # pericarditis/endocarditis/valve/HF/arrhythmia/cardiomyopathy
    try:
        n = int(c[:3])
    except ValueError:
        return False
    return n in (402, 404) or (393 <= n <= 398) or (410 <= n <= 414) or (420 <= n <= 429)


def cardiovascular_hadms(diag_path, primary_only: bool = True) -> set:
    """Set of hadm_ids whose (primary) diagnosis is cardiovascular. diag_path -> diagnoses_icd.csv(.gz)."""
    import pandas as pd
    dx = pd.read_csv(diag_path, usecols=["hadm_id", "icd_code", "icd_version", "seq_num"])
    if primary_only:
        dx = dx[dx["seq_num"] == 1]
    keep = [is_cardiovascular(c, v) for c, v in zip(dx["icd_code"], dx["icd_version"])]
    dx = dx[keep]
    return set(dx["hadm_id"].dropna().astype("int64"))
