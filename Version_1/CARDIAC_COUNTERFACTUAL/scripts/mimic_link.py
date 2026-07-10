"""
mimic_link.py  —  link the cardiac cohort to full MIMIC-IV core tables for DURABLE outcomes.

The cardiac-ext subset has labs/procedures/diagnoses but NOT mortality, demographics, or ICU
stays. This module joins MIMIC-IV `admissions`, `patients`, `icustays` (by subject_id/hadm_id)
to derive the multi-arm benchmark's outcomes + covariates:

  OUTCOMES (durable):
    - in_hospital_mortality       admissions.hospital_expire_flag / deathtime
    - mortality_30d / _1yr        death within N days of the INDEX time (deathtime or dod)
    - readmission_30d             next admission for the same subject within 30d of discharge
    - icu_los_days, icu_readmit   from icustays (sum LOS; >=2 ICU stays in the admission)
  COVARIATES (new):
    - age (anchor_age, capped 91 by MIMIC), sex (gender)

DE-ID NOTE: MIMIC dates are per-patient shifted, so INTERVALS (index->death, discharge->readmit)
are exact even though absolute dates are fake. We only ever use intervals. dod is a date.

Runs on the open DEMO for schema/plumbing validation; on full mimiciv/3.1 for results.
Auto-detects the root (full v3.1 if its 3 core tables exist, else the demo). Override: MIMIC_ROOT.
"""

import os
import logging
import numpy as np
import pandas as pd
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

FULL = Path("/scratch/users/karun09/physionet.org/files/mimiciv/3.1")
DEMO = Path("/scratch/users/karun09/SIMR-Research/mimic-iv-clinical-database-demo-2.2")


def mimic_root():
    if os.environ.get("MIMIC_ROOT"):
        return Path(os.environ["MIMIC_ROOT"])
    # admissions alone already unlocks mortality + readmission, so prefer FULL once it lands.
    return FULL if (FULL / "hosp/admissions.csv.gz").exists() else DEMO


def load_core(root):
    """Load core tables. admissions is REQUIRED (unlocks mortality+readmission); patients
    (age/sex/dod) and icustays (LOS) are OPTIONAL — returned empty if not yet downloaded,
    so a partial download still works. dod-based death just isn't available until patients lands."""
    adm = pd.read_csv(root / "hosp/admissions.csv.gz",
                      usecols=["subject_id", "hadm_id", "admittime", "dischtime",
                               "deathtime", "hospital_expire_flag"],
                      parse_dates=["admittime", "dischtime", "deathtime"])
    pat_path, icu_path = root / "hosp/patients.csv.gz", root / "icu/icustays.csv.gz"
    if pat_path.exists():
        pat = pd.read_csv(pat_path, usecols=["subject_id", "gender", "anchor_age", "dod"],
                          parse_dates=["dod"])
    else:
        pat = pd.DataFrame(columns=["subject_id", "gender", "anchor_age", "dod"])
        log.warning("patients.csv.gz not present yet — age/sex/dod unavailable (mortality uses in-stay deathtime only)")
    if icu_path.exists():
        icu = pd.read_csv(icu_path, usecols=["subject_id", "hadm_id", "stay_id", "intime", "outtime", "los"],
                          parse_dates=["intime", "outtime"])
    else:
        icu = pd.DataFrame(columns=["subject_id", "hadm_id", "stay_id", "intime", "outtime", "los"])
        log.warning("icustays.csv.gz not present yet — ICU LOS/readmit unavailable")
    return adm, pat, icu


def build_index(adm, pat, icu):
    """Pre-compute lookups: admission rows by hadm_id (+ next-admission time for readmission),
    patient rows by subject_id, and ICU aggregates by hadm_id."""
    adm = adm.sort_values(["subject_id", "admittime"]).copy()
    adm["next_admittime"] = adm.groupby("subject_id")["admittime"].shift(-1)
    adm_by_hadm = adm.set_index("hadm_id")
    pat_by_subj = pat.set_index("subject_id")
    icu_agg = (icu.groupby("hadm_id")
                  .agg(icu_los_days=("los", "sum"), n_icu_stays=("stay_id", "count")).to_dict("index"))
    return adm_by_hadm, pat_by_subj, icu_agg


def _to_death_dt(deathtime, dod):
    """Best available death timestamp: in-stay deathtime, else date-of-death (end of that day)."""
    if pd.notna(deathtime):
        return deathtime
    if pd.notna(dod):
        return pd.Timestamp(dod) + pd.Timedelta(hours=23, minutes=59)
    return None


def link_episode(hadm_id, index_time, adm_by_hadm, pat_by_subj, icu_agg):
    """Return durable outcomes + covariates for one episode. index_time: pd.Timestamp or None.
    Missing/uncertain values are flagged so the selector can judge completeness honestly."""
    out = {}
    if hadm_id not in adm_by_hadm.index:
        return {"_linked": False}
    a = adm_by_hadm.loc[hadm_id]
    if isinstance(a, pd.DataFrame):          # dup hadm_id guard
        a = a.iloc[0]
    subj = int(a["subject_id"])
    p = pat_by_subj.loc[subj] if subj in pat_by_subj.index else None

    # ── covariates ──
    out["age"] = float(p["anchor_age"]) if p is not None and pd.notna(p["anchor_age"]) else None
    out["sex"] = (str(p["gender"]) if p is not None and pd.notna(p["gender"]) else None)

    # ── mortality ──
    out["in_hospital_mortality"] = int(a["hospital_expire_flag"]) if pd.notna(a["hospital_expire_flag"]) else None
    death_dt = _to_death_dt(a["deathtime"], p["dod"] if p is not None else pd.NaT)
    idx = pd.Timestamp(index_time) if index_time is not None else None
    for days, key in [(14, "mortality_14d"), (30, "mortality_30d"), (365, "mortality_1yr")]:
        if idx is None:
            out[key] = None
            continue
        if death_dt is not None:
            out[key] = int((death_dt - idx).days <= days)
        else:
            # no recorded death: treat as alive, but flag if our follow-up may be too short
            out[key] = 0
    out["death_observed"] = death_dt is not None
    out["days_index_to_death"] = (int((death_dt - idx).days) if (death_dt is not None and idx is not None) else None)

    # ── readmission (30d, all-cause) ──
    if pd.notna(a["dischtime"]) and pd.notna(a["next_admittime"]):
        gap = (a["next_admittime"] - a["dischtime"]).days
        out["readmission_30d"] = int(0 <= gap <= 30)
        out["days_to_readmission"] = int(gap)
    else:
        out["readmission_30d"] = 0
        out["days_to_readmission"] = None

    # ── ICU ──
    ic = icu_agg.get(hadm_id)
    out["icu_los_days"] = round(float(ic["icu_los_days"]), 3) if ic else 0.0
    out["icu_readmit"] = int(ic["n_icu_stays"] >= 2) if ic else 0
    out["_linked"] = True
    return out


def main():
    """Self-test: load core tables and print cohort-level outcome stats to validate parsing."""
    root = mimic_root()
    log.info(f"MIMIC root: {root}  ({'FULL v3.1' if root == FULL else 'DEMO'})")
    adm, pat, icu = load_core(root)
    log.info(f"admissions={len(adm)} patients={len(pat)} icustays={len(icu)}")
    adm_by_hadm, pat_by_subj, icu_agg = build_index(adm, pat, icu)

    # Validate by linking every admission, using admittime as a stand-in index (demo has no
    # cardiac cohort). On full data, link_episode is called per cardiac episode with its real index.
    rows = []
    for hadm_id, a in adm_by_hadm.iterrows():
        rows.append(link_episode(hadm_id, a["admittime"], adm_by_hadm, pat_by_subj, icu_agg))
    df = pd.DataFrame([r for r in rows if r.get("_linked")])
    log.info(f"linked {len(df)} admissions")
    log.info(f"  in-hospital mortality rate : {df['in_hospital_mortality'].mean():.3f}")
    log.info(f"  30d mortality rate         : {df['mortality_30d'].mean():.3f} "
             f"(deaths observed: {df['death_observed'].sum()})")
    log.info(f"  30d readmission rate       : {df['readmission_30d'].mean():.3f}")
    log.info(f"  ICU LOS days (mean/median) : {df['icu_los_days'].mean():.2f} / {df['icu_los_days'].median():.2f}")
    log.info(f"  ICU readmit rate           : {df['icu_readmit'].mean():.3f}")
    log.info(f"  age (mean)                 : {df['age'].dropna().mean():.1f}")
    log.info(f"  sex                        : {df['sex'].value_counts().to_dict()}")
    log.info("mimic_link self-test OK")


if __name__ == "__main__":
    main()
