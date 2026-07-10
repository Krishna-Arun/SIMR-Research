"""build_enriched_actions_icu.py — enriched 34-dim actions for the ICU broad sample.
Reuses the CARDIAC-fit Option-A scaler (data/action_schema.json) so both cohorts share ONE action scale.
Output: data_icu/enriched_actions.pkl (aligned to data_icu/encoded_states_clmbr.pkl abs_times)."""
import json, pickle
from pathlib import Path
import numpy as np, pandas as pd
import build_enriched_actions as bea   # reuse groups + scan + norm_rate

BASE = Path("/scratch/users/karun09/Version_2/counterfactual_simulation")
MIMIC = Path("/scratch/users/karun09/physionet.org/files/mimiciv/3.1")
OUT = BASE / "data_icu"


def main():
    enc = pickle.load(open(OUT/"encoded_states_clmbr.pkl","rb"))
    schema = json.loads((BASE/"data/action_schema.json").read_text())
    cols = schema["columns"]; ci = {c:i for i,c in enumerate(cols)}; D = len(cols)
    scalers = schema["rate_scalers"]                 # reuse cardiac-fit scaler
    samp = json.loads((OUT/"icu_sample.json").read_text())
    subj = set(int(s) for s in samp["subjects"])
    # hadm set = all admissions of the ICU subjects
    adm = pd.read_csv(MIMIC/"hosp/admissions.csv.gz", usecols=["subject_id","hadm_id"])
    hadm_set = set(adm.loc[adm.subject_id.isin(subj),"hadm_id"].astype(int).tolist())
    traj = {int(t["patient_id"]): t for t in pickle.load(open(OUT/"trajectories.pkl","rb"))}

    want_drip = set().union(*bea.CONT_GROUPS.values(), *bea.PRES_DRIP_GROUPS.values())
    want_proc = set().union(*bea.PROC_GROUPS.values())
    print("scanning inputevents/procedureevents (ICU-scoped)...")
    drips = bea.scan_inputevents(hadm_set, want_drip)
    procs = bea.scan_procedureevents(hadm_set, want_proc)
    drips_by_s = {s:g for s,g in drips.groupby("subject_id")}
    procs_by_s = {s:g for s,g in procs.groupby("subject_id")}

    out=[]
    for e in enc:
        pid=int(e["patient_id"]); T_abs=pd.to_datetime(np.asarray(e["abs_times"])); T=len(T_abs)
        A=np.zeros((T,D),np.float32)
        d=drips_by_s.get(pid); p=procs_by_s.get(pid); tr=traj.get(pid)
        pcicabg={g:[] for g in bea.TRAJ_ACTION}
        if tr:
            for ev in tr["events"]:
                for g,aid in bea.TRAJ_ACTION.items():
                    if int(ev.get("action_id",0))==aid: pcicabg[g].append(pd.Timestamp(ev["t"]))
        for i in range(1,T):
            lo,hi=T_abs[i-1],T_abs[i]
            if d is not None:
                ov=d[(d["starttime"]<=hi)&(d["endtime"]>lo)]
                for g,sub_ in ov.groupby("group"):
                    A[i,ci[f"{g}__on"]]=1.0
                    if g in bea.CONT_GROUPS:
                        raw=sub_["rate"].dropna(); rmax=float(raw.max()) if len(raw) else None
                        A[i,ci[f"{g}__rate"]]=bea.norm_rate(g,rmax,scalers)
            if p is not None:
                ov=p[(p["starttime"]<=hi)&(p["endtime"]>lo)]
                for g in ov["group"].unique(): A[i,ci[f"{g}__on"]]=1.0
            for g,times in pcicabg.items():
                if any(lo<t<=hi for t in times): A[i,ci[f"{g}__on"]]=1.0
        out.append({"patient_id":pid,"abs_times":e["abs_times"],"action_matrix":A})
    pickle.dump(out, open(OUT/"enriched_actions.pkl","wb"))
    print(f"wrote {OUT/'enriched_actions.pkl'} ({len(out)} patients)")


if __name__=="__main__":
    main()
