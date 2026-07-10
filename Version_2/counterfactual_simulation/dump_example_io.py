"""dump_example_io.py — write a human-readable JSON of the model's INPUT and OUTPUT for a few
real test-split transitions, so the whole pipeline is concrete. No training; just inference."""
import json, pickle
from pathlib import Path
import numpy as np, pandas as pd, torch
from train_substrate_wm import ACJEPA, LabDecoder, CORE, LOINCS, LABN, NL, ARM

BASE = Path("/scratch/users/karun09/Version_2/counterfactual_simulation")
DEV = "cuda" if torch.cuda.is_available() else "cpu"
ARMN = {v: k for k, v in ARM.items()}

sub = pickle.load(open(BASE/"data/train_substrate.pkl","rb"))
traj = {int(t["patient_id"]): t for t in pickle.load(open(BASE/"data/trajectories.pkl","rb"))}
sp = json.loads((BASE/"data/splits.json").read_text()); test=set(sp["splits"]["test"])
ck = torch.load(BASE/"data/world_model_enriched.pt", map_location=DEV)
model=ACJEPA(ck["zdim"],ck["adim"]).to(DEV); model.load_state_dict(ck["model"]); model.eval()
dec=LabDecoder(ck["zdim"],NL).to(DEV); dec.load_state_dict(ck["dec"]); dec.eval()
lmean=np.array(ck["lab_scaler_mean"]); lstd=np.sqrt(np.array(ck["lab_scaler_var"]))
cols = sub[0]["action_cols"]

def decode_units(z):
    with torch.no_grad():
        return (dec(z).cpu().numpy()*lstd + lmean)[0]

def lab_ser(pid):
    tr=traj.get(pid); ser={c:[] for c in CORE}
    for ev in tr["events"]:
        c=ev.get("code")
        if c in ser and ev.get("value") is not None:
            ser[c].append((pd.Timestamp(ev["t"]), float(ev["value"])))
    for c in ser: ser[c].sort()
    return ser

def val_before(ser, c, t):
    v=None
    for tt,vv in ser[c]:
        if tt<=t: v=vv
        else: break
    return v

def val_after(ser, c, t0, t1):
    post=[vv for tt,vv in ser[c] if t0<tt<=t1]
    return post[-1] if post else None

def active_actions(avec):
    out={}
    for j,c in enumerate(cols):
        if c.endswith("__on") and avec[j]>0:
            g=c[:-4]; rate=avec[cols.index(f"{g}__rate")] if f"{g}__rate" in cols else None
            out[g]= {"active":True, "norm_rate":round(float(rate),2)} if rate is not None else {"active":True}
    return out

FOCUS=["creatinine","bun","potassium","sodium","hemoglobin"]   # labs to compare
examples=[]
for e in sub:
    pid=int(e["patient_id"])
    if pid not in test: continue
    ser=lab_ser(pid)
    times=pd.to_datetime(np.asarray(e["abs_times"])); T=len(times)
    Z=torch.tensor(e["s"],device=DEV).float(); A=torch.tensor(e["action_matrix"],device=DEV).float()
    hrs=np.asarray(e["hours"],float)
    for i in range(T-1):
        if float(A[i+1].abs().sum())==0: continue
        t0,t1=times[i],times[i+1]
        # require >=2 focus labs with a REAL post remeasurement
        comp={}
        for nm in FOCUS:
            c=[k for k,v in CORE.items() if v==nm][0]
            b=val_before(ser,c,t0); a_=val_after(ser,c,t0,t1)
            if b is not None and a_ is not None: comp[nm]=(b,a_)
        if len(comp)<2: continue
        dt=max(hrs[i+1]-hrs[i],0.0)
        with torch.no_grad():
            zhat=model(Z[i:i+1], A[i+1:i+2], torch.tensor([dt],device=DEV).float())
        pred_t=dict(zip(LABN,decode_units(Z[i:i+1]))); pred_n=dict(zip(LABN,decode_units(zhat)))
        def dir3(x0,x1):
            r=(x1-x0)/(abs(x0)+1e-6); return "Rising" if r>0.05 else ("Falling" if r<-0.05 else "Stable")
        labcmp={}
        for nm,(b,a_) in comp.items():
            pt,pn=float(pred_t[nm]),float(pred_n[nm])
            labcmp[nm]={"actual_before":round(b,2),"actual_after":round(a_,2),
                        "predicted_after":round(pn,2),
                        "true_direction":dir3(b,a_),"predicted_direction":dir3(pt,pn),
                        "persistence_direction":"Stable"}
        examples.append({
          "patient_id":pid,"arm":ARMN.get(ARM.get(str(e["outcomes"].get("arm")),0)),
          "INPUT":{
            "state_z_t":{"note":"768-d frozen CLMBR vector (first 6 of 768 shown)","first6":[round(float(x),3) for x in e["s"][i][:6]]},
            "action_a_t (treatment given this step)":active_actions(e["action_matrix"][i+1]),
            "delta_t_hours":round(float(dt),1)},
          "OUTPUT — lab-by-lab (actual vs predicted)":labcmp,
        })
        break
    if len(examples)>=4: break

(BASE/"data/example_io.json").write_text(json.dumps(examples, indent=2))
print(json.dumps(examples[0], indent=2))
print(f"\n... wrote {len(examples)} examples to data/example_io.json")
