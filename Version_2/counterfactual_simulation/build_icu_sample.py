"""build_icu_sample.py — pick the broad-training ICU sample (widening step 1).

10,000 adult ICU subjects, EXCLUDING every cardiac-cohort subject (so the cardiac val/test wall stays
absolute — the broad set can never leak a held-out patient). Emits each subject's admission windows +
mortality outcomes (no arm; arm is cardiac-only and only used at eval/application time).

Output: data_icu/icu_sample.json  {seed, n, subjects:[...], windows:{sid:[[admit,disch],...]},
outcomes:{sid:{mortality, mortality_30d}}}
"""
import json, pickle
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path("/scratch/users/karun09/Version_2/counterfactual_simulation")
M = Path("/scratch/users/karun09/physionet.org/files/mimiciv/3.1")
OUT = BASE / "data_icu"; OUT.mkdir(exist_ok=True)
N, SEED = 10_000, 0


def main():
    icu = pd.read_csv(M/"icu/icustays.csv.gz", usecols=["subject_id"])
    icu_subj = set(icu.subject_id.unique().tolist())
    # exclude ALL cardiac-cohort subjects (train too — union happens at training time; keeps it clean)
    cardiac = {int(t["patient_id"]) for t in pickle.load(open(BASE/"data/trajectories.pkl","rb"))}
    # adults only
    pat = pd.read_csv(M/"hosp/patients.csv.gz", usecols=["subject_id","anchor_age","dod"])
    adult = set(pat.loc[pat.anchor_age >= 18, "subject_id"].tolist())
    pool = sorted((icu_subj & adult) - cardiac)
    print(f"ICU adult subjects (excl. cardiac cohort): {len(pool):,}")
    rng = np.random.default_rng(SEED)
    sample = sorted(int(x) for x in rng.choice(pool, size=min(N, len(pool)), replace=False))
    ss = set(sample)

    adm = pd.read_csv(M/"hosp/admissions.csv.gz",
                      usecols=["subject_id","hadm_id","admittime","dischtime","hospital_expire_flag"],
                      parse_dates=["admittime","dischtime"])
    adm = adm[adm.subject_id.isin(ss)]
    dod = pat.set_index("subject_id")["dod"].to_dict()
    windows, outcomes = {}, {}
    for sid, g in adm.groupby("subject_id"):
        windows[int(sid)] = [[r.admittime.isoformat(), r.dischtime.isoformat()]
                             for r in g.itertuples() if pd.notna(r.admittime) and pd.notna(r.dischtime)]
        mort = int(g.hospital_expire_flag.max())
        d = pd.to_datetime(dod.get(sid), errors="coerce")
        last_disch = g.dischtime.max()
        m30 = int(mort or (pd.notna(d) and pd.notna(last_disch) and (d - last_disch).days <= 30 and (d - last_disch).days >= -1))
        outcomes[int(sid)] = {"mortality": mort, "mortality_30d": m30}

    keep = [s for s in sample if s in windows and windows[s]]
    out = {"seed": SEED, "n": len(keep), "subjects": keep,
           "windows": {str(s): windows[s] for s in keep},
           "outcomes": {str(s): outcomes[s] for s in keep}}
    (OUT/"icu_sample.json").write_text(json.dumps(out))
    mrate = np.mean([outcomes[s]["mortality"] for s in keep])
    print(f"sampled {len(keep):,} ICU subjects (seed {SEED}); in-hosp mortality {mrate:.3f}")
    print(f"wrote {OUT/'icu_sample.json'}")


if __name__ == "__main__":
    main()
