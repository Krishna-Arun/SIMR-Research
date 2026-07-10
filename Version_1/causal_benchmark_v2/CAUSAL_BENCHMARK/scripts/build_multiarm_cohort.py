"""
build_multiarm_cohort.py  —  3-arm revascularization cohort with DURABLE outcomes.

Arms (the revascularization decision; reuses build_dataset's code lists):
  - pci      : percutaneous coronary intervention (PTCA / stent)
  - cabg     : surgical revascularization (coronary bypass)
  - medical  : cardiac admission, NO revascularization (guideline-directed medical therapy)

For each admission we assign an arm, set an index time, attach the durable outcomes +
demographics from MIMIC core (via mimic_link), and apply a LANDMARK rule for mortality
(include only patients alive at the landmark; classify the arm by what happened by then) so
we don't credit a procedure for the survival of patients who simply lived long enough to get it.

Output: data/multiarm_cohort.json + per-arm composition stats (a first look at OVERLAP — do
the arms look like similar patients, or are they clearly different populations?).

Runs the arm assignment with no dependencies (works now); the MIMIC-core enrichment activates
as soon as admissions/patients/icustays are readable (admissions.csv.gz has already landed).
"""

import json
import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BENCH = Path(__file__).parent.parent
sys.path.insert(0, str(BENCH / "scripts"))

# Reuse the validated arm-code logic + comorbidity extractor.
from build_dataset import (arm_for_codes, pci_vessel_group, build_comorbidity_vector,
                           COMORBIDITIES, D as CARDIAC_DIR)
import mimic_link

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

PROC_FILE = CARDIAC_DIR / "heart_procedures.csv"
DIAG_FILE = CARDIAC_DIR / "heart_diagnoses_all_true.csv"
CONTEXT_FILE = BENCH / "data" / "context.json"
OUT = BENCH / "data" / "multiarm_cohort.json"

LANDMARK_DAYS = int(os.environ.get("TASKC_LANDMARK_DAYS", "2"))  # treatment must occur by here


def assign_arms():
    """Return (arm_of_hadm, vessel_of_hadm, proc_date_of_hadm, comorbid_of_hadm, universe).
    Universe = all cardiac-cohort admissions (from the diagnoses table)."""
    procs = pd.read_csv(PROC_FILE, dtype={"icd_code": str})
    procs["chartdate"] = pd.to_datetime(procs["chartdate"], errors="coerce")
    codes_by_hadm = procs.groupby("hadm_id")["icd_code"].apply(lambda s: set(map(str, s)))
    arm_of, vessel_of, proc_date = {}, {}, {}
    for h, codes in codes_by_hadm.items():
        arm = arm_for_codes(codes)            # 'pci' | 'cabg' | None
        if arm:
            arm_of[h] = arm
            vessel_of[h] = pci_vessel_group(codes) if arm == "pci" else "n/a"
            sub = procs[(procs["hadm_id"] == h)]
            proc_date[h] = sub["chartdate"].min()

    diag = pd.read_csv(DIAG_FILE, usecols=["hadm_id", "icd_code"], dtype={"icd_code": str})
    diag_by_hadm = diag.groupby("hadm_id")["icd_code"].apply(list).to_dict()
    universe = set(diag_by_hadm)
    # medical arm = cardiac admission with no revascularization procedure
    for h in universe:
        arm_of.setdefault(h, "medical")
    comorbid_of = {h: build_comorbidity_vector(diag_by_hadm.get(h, [])) for h in universe}
    return arm_of, vessel_of, proc_date, comorbid_of, universe


def load_aki():
    """AKI (KDIGO) per hadm_id from context.json (computed there off the creatinine series)."""
    if not CONTEXT_FILE.exists():
        log.warning("context.json absent — AKI outcome unavailable (run build_context.py first)")
        return {}
    ctx = json.loads(CONTEXT_FILE.read_text())["context"]
    return {int(h): c.get("outcomes", {}).get("aki", {}) for h, c in ctx.items()}


def main():
    arm_of, vessel_of, proc_date, comorbid_of, universe = assign_arms()
    aki_by_hadm = load_aki()
    arms = {a: 0 for a in ("pci", "cabg", "medical")}
    for h in universe:
        a = arm_of.get(h)
        if a in arms:
            arms[a] += 1
    log.info(f"Arm sizes (pre-enrichment, n={len(universe)} cardiac admissions): {arms}")

    # ── MIMIC-core enrichment (mortality / readmission / ICU / age-sex) ──
    root = mimic_link.mimic_root()
    enriched = []
    try:
        adm, pat, icu = mimic_link.load_core(root)
        adm_by_hadm, pat_by_subj, icu_agg = mimic_link.build_index(adm, pat, icu)
        have_core = True
        log.info(f"MIMIC core loaded from {root.name}: adm={len(adm)} pat={len(pat)} icu={len(icu)}")
    except Exception as e:
        have_core = False
        log.warning(f"MIMIC core not yet readable ({e}); writing arm assignment only.")
        adm_by_hadm = pat_by_subj = icu_agg = None

    n_linked = 0
    for h in sorted(universe):
        aki = aki_by_hadm.get(int(h), {})
        rec = {"hadm_id": int(h), "arm": arm_of[h], "pci_vessels": vessel_of.get(h, "n/a"),
               "comorbidities": comorbid_of[h],
               "n_comorbidities": int(sum(comorbid_of[h].values())),
               "aki": aki.get("aki"), "aki_stage": aki.get("aki_stage")}
        if have_core and h in adm_by_hadm.index:
            a = adm_by_hadm.loc[h]
            if isinstance(a, pd.DataFrame):
                a = a.iloc[0]
            index_time = a["admittime"]          # admission-anchored index for durable outcomes
            pdt = proc_date.get(h)
            # landmark: was the procedure done by the landmark, and alive at landmark?
            out = mimic_link.link_episode(h, index_time, adm_by_hadm, pat_by_subj, icu_agg)
            treated_by_landmark = (rec["arm"] == "medical") or (
                pd.notna(pdt) and (pdt - index_time).days <= LANDMARK_DAYS)
            d2d = out.get("days_index_to_death")
            alive_at_landmark = (d2d is None) or (d2d > LANDMARK_DAYS)
            rec.update(out)
            rec["index_time"] = str(index_time)
            rec["treated_by_landmark"] = bool(treated_by_landmark)
            rec["alive_at_landmark"] = bool(alive_at_landmark)
            rec["eligible"] = bool(treated_by_landmark and alive_at_landmark)
            n_linked += 1
        else:
            rec["_linked"] = False
            rec["eligible"] = None
        enriched.append(rec)

    OUT.write_text(json.dumps({
        "task": "multiarm_revascularization_cohort",
        "arms": ["pci", "cabg", "medical"],
        "landmark_days": LANDMARK_DAYS,
        "mimic_root": str(root), "core_loaded": have_core,
        "n_cardiac_admissions": len(universe), "n_linked": n_linked,
        "arm_sizes": arms, "episodes": enriched,
    }, indent=2))
    log.info(f"Wrote {OUT} (linked {n_linked}/{len(universe)})")

    # ── overlap first-look: per-arm composition (do arms look like similar patients?) ──
    if have_core and n_linked:
        df = pd.DataFrame([e for e in enriched if e.get("_linked") is not False
                           and e.get("eligible")])
        if len(df):
            log.info(f"Eligible after landmark: {len(df)}  by arm: {df['arm'].value_counts().to_dict()}")
            log.info("Per-arm composition (overlap sanity — closer = more overlap):")
            for a, g in df.groupby("arm"):
                age = g["age"].dropna()
                log.info(f"  {a:8s} n={len(g):4d}  age={age.mean():.0f}  "
                         f"comorbid={g['n_comorbidities'].mean():.1f}  "
                         f"readmit30={g['readmission_30d'].mean():.3f}  "
                         f"AKI={g['aki'].mean():.3f}  "
                         f"30d_mort={g['mortality_30d'].mean():.3f}  "
                         f"icu_los={g['icu_los_days'].mean():.1f}")


if __name__ == "__main__":
    main()
