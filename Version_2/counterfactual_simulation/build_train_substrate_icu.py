"""build_train_substrate_icu.py — clean substrate for the ICU broad sample (window + cap), same rules
as the cardiac substrate. Windows come from icu_sample.json. Output: data_icu/train_substrate.pkl."""
import json, pickle
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path("/scratch/users/karun09/Version_2/counterfactual_simulation")
OUT = BASE / "data_icu"
CAP = 150


def main():
    enc = pickle.load(open(OUT/"encoded_states_clmbr.pkl","rb"))
    acts = {int(a["patient_id"]): a for a in pickle.load(open(OUT/"enriched_actions.pkl","rb"))}
    schema = json.loads((BASE/"data/action_schema.json").read_text()); cols = schema["columns"]
    samp = json.loads((OUT/"icu_sample.json").read_text())
    wins = {int(k): [(pd.Timestamp(a), pd.Timestamp(b)) for a,b in v] for k,v in samp["windows"].items()}

    out=[]; Tb=[]; Ta=[]
    for e in enc:
        pid=int(e["patient_id"]); a=acts.get(pid)
        if a is None: continue
        t=pd.to_datetime(np.asarray(e["abs_times"])); Tb.append(len(t))
        w=wins.get(pid,[])
        if not w: continue
        keep=np.zeros(len(t),bool)
        for lo,hi in w: keep |= (t>=lo-pd.Timedelta(hours=6))&(t<=hi+pd.Timedelta(hours=6))
        idx=np.where(keep)[0]
        if len(idx)<2: continue
        if len(idx)>CAP:
            sel=np.linspace(0,len(idx)-1,CAP).round().astype(int); idx=idx[np.unique(sel)]
        Ta.append(len(idx))
        abs_t=np.asarray(e["abs_times"])[idx]
        hrs=((pd.to_datetime(abs_t)-pd.to_datetime(abs_t)[0]).total_seconds()/3600.0).to_numpy(np.float32)
        out.append({"patient_id":pid,"s":np.asarray(e["s"],np.float32)[idx],"abs_times":abs_t,
                    "hours":hrs,"action_matrix":a["action_matrix"][idx].astype(np.float32),
                    "action_cols":cols,"outcomes":e["outcomes"]})
    pickle.dump(out, open(OUT/"train_substrate.pkl","wb"))
    print(f"ICU substrate: {len(out)} patients, {sum(Ta):,} timepoints "
          f"(was {sum(Tb):,}); median T={int(np.median(Ta))}")
    print(f"wrote {OUT/'train_substrate.pkl'}")


if __name__=="__main__":
    main()
