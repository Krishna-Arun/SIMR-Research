"""build_icu_meds.py — MEDS + trajectories for the broad 10k-ICU sample (widening step 2).

Generalizes build_cohort_meds.py to an arbitrary subject list (from icu_sample.json). Full history
per subject for CLMBR context; trajectory labels restricted to admission windows; outcomes = mortality
/ mortality_30d (no arm). Same code namespaces + LOINC relabel + action_id computation as the cardiac build.

Run in clmbr311 (needs `datasets`). Heavy: scans full labevents/prescriptions for 10k subjects.
Output: data_icu/mimic_meds/data/icu_000.parquet, data_icu/trajectories_icu.pkl
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
import build_cohort_meds as bc            # reuse helpers + actions import + sys.path setup

MIMIC = bc.MIMIC
BASE = Path("/scratch/users/karun09/Version_2/counterfactual_simulation")
OUT = BASE / "data_icu"
MEDS_DATA = OUT / "mimic_meds" / "data"


def main():
    samp = json.loads((OUT / "icu_sample.json").read_text())
    subjects = [int(s) for s in samp["subjects"]]
    subj_set = set(subjects)
    windows = {int(k): [(pd.Timestamp(a), pd.Timestamp(b)) for a, b in v]
               for k, v in samp["windows"].items()}
    outcomes_in = {int(k): v for k, v in samp["outcomes"].items()}
    lab_map = bc.load_lab_map()
    vocab = bc.ActionVocab(); NOOP = 0
    print(f"building MEDS for {len(subjects):,} ICU subjects; lab->LOINC {len(lab_map)} itemids")

    events = {s: [] for s in subjects}

    # patients: birth/gender/death
    pat = pd.read_csv(MIMIC/"hosp/patients.csv.gz",
                      usecols=["subject_id","gender","anchor_age","anchor_year","dod"], dtype=str)
    pat = pat[pat.subject_id.astype("int64").isin(subj_set)]
    for r in pat.itertuples():
        s = int(r.subject_id)
        try: birth = bc.dt.datetime(int(r.anchor_year)-int(float(r.anchor_age)), 1, 1)
        except Exception: continue
        events[s].append((birth, bc.BIRTH_CODE, None, NOOP))
        events[s].append((birth, f"MIMIC_IV_Gender/{r.gender}", None, NOOP))
        d = bc._t(r.dod)
        if d: events[s].append((d, bc.DEATH_CODE, None, NOOP))
    print(f"  patients: {len(pat)}")

    adm = pd.read_csv(MIMIC/"hosp/admissions.csv.gz", usecols=["hadm_id","dischtime"])
    disch = adm.set_index("hadm_id")["dischtime"].to_dict()
    dx = pd.read_csv(MIMIC/"hosp/diagnoses_icd.csv.gz",
                     usecols=["subject_id","hadm_id","icd_code","icd_version"], dtype=str)
    dx = dx[dx.subject_id.astype("int64").isin(subj_set)]
    for r in dx.itertuples():
        t = bc._t(disch.get(int(r.hadm_id)))
        if t: events[int(r.subject_id)].append((t, bc.icd_dx(r.icd_version, r.icd_code), None, NOOP))
    print(f"  diagnoses: {len(dx)}")

    pr = pd.read_csv(MIMIC/"hosp/procedures_icd.csv.gz",
                     usecols=["subject_id","chartdate","icd_code","icd_version"], dtype=str)
    pr = pr[pr.subject_id.astype("int64").isin(subj_set)]
    for r in pr.itertuples():
        t = bc._t(r.chartdate)
        if t:
            aid = vocab.to_id(bc.procedure_to_group(r.icd_code))
            events[int(r.subject_id)].append((t, bc.icd_proc(r.icd_version, r.icd_code), None, aid))
    print(f"  procedures: {len(pr)}")

    n_rx = 0
    for ch in pd.read_csv(MIMIC/"hosp/prescriptions.csv.gz",
                          usecols=["subject_id","starttime","ndc","drug"], dtype=str, chunksize=2_000_000):
        ch = ch[ch.subject_id.astype("int64").isin(subj_set)]
        for r in ch.itertuples():
            ndc = bc.norm_ndc(r.ndc); t = bc._t(r.starttime)
            if ndc and t:
                aid = vocab.to_id(bc.drug_to_group(r.drug))
                events[int(r.subject_id)].append((t, f"NDC/{ndc}", None, aid)); n_rx += 1
    print(f"  prescriptions: {n_rx}")

    n_lab = 0
    for ch in pd.read_csv(MIMIC/"hosp/labevents.csv.gz",
                          usecols=["subject_id","charttime","itemid","valuenum"],
                          dtype={"subject_id":"float64","itemid":"float64"}, chunksize=2_000_000):
        ch = ch.dropna(subset=["subject_id","itemid"])
        ch = ch[ch.subject_id.astype("int64").isin(subj_set)]
        if not len(ch): continue
        for r in ch.itertuples():
            loinc = lab_map.get(int(r.itemid))
            if not loinc: continue
            t = bc._t(r.charttime)
            if not t: continue
            val = float(r.valuenum) if pd.notna(r.valuenum) else None
            events[int(r.subject_id)].append((t, f"LOINC/{loinc}", val, NOOP)); n_lab += 1
    print(f"  labs (mapped): {n_lab}")

    def in_window(s, t):
        for lo, hi in windows.get(s, []):
            if lo - pd.Timedelta(hours=6) <= t <= hi + pd.Timedelta(hours=6):
                return True
        return False

    meds_rows, trajectories = [], []
    for s in subjects:
        evs = sorted(events[s], key=lambda e: e[0])
        if len(evs) < 2: continue
        meds_rows.append({"patient_id": s,
            "events": [{"time": t, "code": c, "numeric_value": v} for t, c, v, _ in evs]})
        traj = [{"t": t, "code": c, "value": v, "action_id": int(aid)}
                for t, c, v, aid in evs if in_window(s, pd.Timestamp(t))]
        if len(traj) < 2: continue
        o = outcomes_in.get(s, {})
        trajectories.append({"patient_id": s, "static": {}, "events": traj,
            "outcomes": {"mortality": int(o.get("mortality",0)), "mortality_30d": int(o.get("mortality_30d",0)),
                         "readmission_30d": 0, "icu_los_days": 0.0, "arm": "icu_other"}})
    print(f"\nassembled {len(meds_rows)} patients; {len(trajectories)} trajectories")

    import datasets
    MEDS_DATA.mkdir(parents=True, exist_ok=True)
    datasets.Dataset.from_list(meds_rows).to_parquet(str(MEDS_DATA/"icu_000.parquet"))
    bc.save_pickle(trajectories, str(OUT/"trajectories.pkl"))   # name matches encode_clmbr's expectation
    print(f"wrote MEDS + data_icu/trajectories.pkl ({len(trajectories)} patients)")


if __name__ == "__main__":
    main()
