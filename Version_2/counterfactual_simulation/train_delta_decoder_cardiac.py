"""train_delta_decoder_cardiac.py — CARDIAC-ONLY delta-aware training (no ICU, no queue).

Same as train_delta_decoder.py but drops the ICU widening loads so it runs locally in minutes.
Tests the training-OBJECTIVE lever (delta loss up-weighting moving labs) in isolation from the
data-scale (widening) lever. Frozen cardiac train/val/test wall unchanged (data/splits.json).

Saves:  data/world_model_cardiac_delta.pt + data/cardiac_delta_metrics.json
        (does NOT touch data/world_model_widened.pt — the queued job still owns that name)
"""
import json, pickle
from pathlib import Path
import numpy as np, pandas as pd, torch, torch.nn as nn, torch.nn.functional as F
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from train_substrate_wm import ACJEPA, LabDecoder, CORE, LOINCS, LABN, NL
from add_outcome_decoder import OutcomeDecoder, OUTC

BASE = Path("/scratch/users/karun09/Version_2/counterfactual_simulation")
DEV = "cuda" if torch.cuda.is_available() else "cpu"
ARM4 = {"medical":0,"pci":1,"cabg":2,"icu_other":3}
ALPHA = 2.0                       # weight on the delta loss
REFS = {"creatinine":(0.5,1.2),"bun":(6,20),"potassium":(3.3,5.1),"sodium":(133,145),
        "chloride":(96,110),"bicarbonate":(22,32),"hemoglobin":(14,18),"platelets":(150,440),
        "glucose":(70,140),"magnesium":(1.6,2.6),"phosphate":(2.5,4.5),"wbc":(4,11),
        "anion_gap":(8,16),"hematocrit":(36,50)}


def lab_series(traj):
    out={}
    for t in traj:
        pid=int(t["patient_id"]); ser={c:[] for c in LOINCS}
        for ev in t["events"]:
            c=ev.get("code")
            if c in ser and ev.get("value") is not None: ser[c].append((pd.Timestamp(ev["t"]),float(ev["value"])))
        for c in ser: ser[c].sort()
        out[pid]=ser
    return out


def locf_and_real(ser, times):
    """returns Y[T,NL] (LOCF) and REAL[T,NL] (1 if measured in (t_{i-1},t_i])."""
    T=len(times); Y=np.full((T,NL),np.nan,np.float32); R=np.zeros((T,NL),np.float32)
    for j,c in enumerate(LOINCS):
        obs=ser.get(c,[]); k=0; last=None
        for i,t in enumerate(times):
            measured=False
            while k<len(obs) and obs[k][0]<=t:
                last=obs[k][1]
                if i>0 and obs[k][0]>times[i-1]: measured=True
                k+=1
            if last is not None: Y[i,j]=last
            if measured: R[i,j]=1.0
    return Y,R


def build(subs, series, split_of):
    Z,ZN,A,DT,ARM,SPL,Yp,Yc,RM=[],[],[],[],[],[],[],[],[]
    for e in subs:
        pid=int(e["patient_id"]); s=e["s"]; a=e["action_matrix"]; h=e["hours"]; T=len(s)
        if T<2: continue
        arm=ARM4.get(str(e["outcomes"].get("arm","icu_other")),3)
        spl=split_of(pid)
        times=pd.to_datetime(np.asarray(e["abs_times"]))
        Y,R=locf_and_real(series.get(pid,{}),times)
        for i in range(1,T):
            Z.append(s[i-1]); ZN.append(s[i]); A.append(a[i]); DT.append(max(h[i]-h[i-1],0.0))
            ARM.append(arm); SPL.append(spl); Yp.append(Y[i-1]); Yc.append(Y[i]); RM.append(R[i])
    return (np.array(Z),np.array(ZN),np.array(A),np.array(DT,np.float32),np.array(ARM),
            np.array(SPL),np.array(Yp),np.array(Yc),np.array(RM))


def main():
    # ---- CARDIAC ONLY (no ICU loads) ----
    car=pickle.load(open(BASE/"data/train_substrate.pkl","rb"))
    sp=json.loads((BASE/"data/splits.json").read_text())
    trS,vaS,teS=set(sp["splits"]["train"]),set(sp["splits"]["val"]),set(sp["splits"]["test"])
    def split_of(pid): return "val" if pid in vaS else ("test" if pid in teS else "train")
    ser=lab_series(pickle.load(open(BASE/"data/trajectories.pkl","rb")))

    subs=car
    Z,ZN,A,DT,ARM,SPL,Yp,Yc,RM=build(subs,ser,split_of)
    zdim,adim=Z.shape[1],A.shape[1]
    trm=(SPL=="train"); tem=(SPL=="test")
    print(f"transitions {len(Z):,}  train {trm.sum():,} (cardiac)  test {tem.sum():,} (cardiac)  zdim={zdim} adim={adim}",flush=True)

    # lab standardizer on train
    lsc=StandardScaler().fit(np.nan_to_num(Yp[trm],nan=np.nanmedian(Yp[trm],axis=0)))
    lm,ls=lsc.mean_,np.sqrt(lsc.var_)
    def sd(x): return (np.nan_to_num(x,nan=0.0)-lm)/ls

    def T_(x): return torch.tensor(x,device=DEV)
    Zt,ZNt,At,DTt=T_(Z).float(),T_(ZN).float(),T_(A).float(),T_(DT).float()
    ARMt=T_(ARM).long()
    Ypt,Yct=T_(sd(Yp)).float(),T_(sd(Yc)).float()
    mp,mc=T_(np.isfinite(Yp)).float(),T_(np.isfinite(Yc)).float()
    RMt=T_(RM).float()
    tri=np.where(trm)[0]

    # IPW (4-class arm) — cardiac has medical/pci/cabg; keep 4-class for parity, guard degenerate
    ppl=LogisticRegression(max_iter=1500,C=1.0,multi_class="multinomial").fit(Z[trm],ARM[trm])
    proba=ppl.predict_proba(Z); cls=list(ppl.classes_)
    marg=np.bincount(ARM[trm],minlength=4)/trm.sum()
    pa=proba[np.arange(len(ARM)),[cls.index(a) for a in ARM]]
    W=T_(np.clip(marg[ARM]/np.clip(pa,1e-3,None),0.1,10.0).astype(np.float32))

    n_arm=int(max(4, ARM.max()+1))
    model=ACJEPA(zdim,adim,n_arm=4).to(DEV)
    opt=torch.optim.Adam(model.parameters(),1e-3,weight_decay=1e-4); LAM=0.5
    persist=float(F.mse_loss(ZNt[tem],Zt[tem]).item())
    for ep in range(60):
        model.train(); perm=tri[torch.randperm(len(tri)).numpy()]
        for b in range(0,len(perm),256):
            idx=perm[b:b+256]
            loss=model.nll(Zt[idx],At[idx],DTt[idx],ZNt[idx],W[idx])+LAM*model.adv_loss(Zt[idx],ARMt[idx],LAM)
            opt.zero_grad(); loss.backward(); nn.utils.clip_grad_norm_(model.parameters(),1.0); opt.step()
    model.eval()
    with torch.no_grad():
        vm=float(F.mse_loss(model(Zt[tem],At[tem],DTt[tem]),ZNt[tem]).item())
    print(f"predictor: test_mse={vm:.4f} vs persistence={persist:.4f}  beats={vm<persist}",flush=True)

    # ---- DELTA-AWARE lab decoder ----
    dec=LabDecoder(zdim,NL).to(DEV); dopt=torch.optim.Adam(dec.parameters(),1e-3,weight_decay=1e-4)
    for ep in range(90):
        dec.train(); perm=tri[torch.randperm(len(tri)).numpy()]
        for b in range(0,len(perm),512):
            idx=perm[b:b+512]
            dz,dzn=dec(Zt[idx]),dec(ZNt[idx])
            val=(((dz-Ypt[idx])**2)*mp[idx]).sum()/mp[idx].sum().clamp(min=1) \
               +(((dzn-Yct[idx])**2)*mc[idx]).sum()/mc[idx].sum().clamp(min=1)
            true_d=Yct[idx]-Ypt[idx]; pred_d=dzn-dz
            wmove=(1.0+true_d.abs())*RMt[idx]                    # up-weight real, moving labs
            dl=((pred_d-true_d)**2*wmove).sum()/wmove.sum().clamp(min=1)
            loss=val+ALPHA*dl
            dopt.zero_grad(); loss.backward(); dopt.step()

    # outcome decoder (per-transition outcome = patient outcome)
    od=OutcomeDecoder(zdim,len(OUTC)).to(DEV); oopt=torch.optim.Adam(od.parameters(),1e-3,weight_decay=1e-4)
    outc=[]
    for e in subs:
        y=[int(e["outcomes"].get(k,0) or 0) for k in OUTC]
        for _ in range(len(e["s"])-1): outc.append(y)
    Yo=T_(np.array(outc,np.float32))
    for ep in range(60):
        od.train(); perm=tri[torch.randperm(len(tri)).numpy()]
        for b in range(0,len(perm),512):
            idx=perm[b:b+512]
            loss=F.binary_cross_entropy_with_logits(od(Zt[idx]),Yo[idx])
            oopt.zero_grad(); loss.backward(); oopt.step()

    # ---- 1-step direction gate on cardiac TEST ----
    dec.eval()
    with torch.no_grad():
        zhat=model(Zt[tem],At[tem],DTt[tem])
        pd_units=(dec(zhat).cpu().numpy()*ls+lm); pc_units=(dec(Zt[tem]).cpu().numpy()*ls+lm)
    Ypc,Ycc,RMc=Yp[tem],Yc[tem],RM[tem]
    def d3(post,base,lo,hi):
        if lo<=post<=hi: return "Stable"
        return "Rising" if post>=base else "Falling"
    rows=[]
    for n,nm in enumerate(LABN):
        lo,hi=REFS[nm]
        for r in range(tem.sum()):
            if RMc[r,n]==0 or not np.isfinite(Ypc[r,n]) or not np.isfinite(Ycc[r,n]): continue
            base=Ypc[r,n]; true=d3(Ycc[r,n],base,lo,hi)
            sim=d3(pd_units[r,n],base,lo,hi); pers=d3(base,base,lo,hi)
            rows.append((nm,true,sim,pers,(base<lo or base>hi)))
    df=pd.DataFrame(rows,columns=["lab","true","sim","pers","oor"])
    def bal(t,p):
        a=[ (p[t==c]==c).mean() for c in ["Rising","Falling","Stable"] if (t==c).sum()>0]
        return round(float(np.mean(a)),3) if a else float("nan")
    res={"n_eval":len(df),
         "overall":{"sim":bal(df["true"].values,df["sim"].values),"pers":bal(df["true"].values,df["pers"].values)},
         "abnormal_baseline":{"n":int(df["oor"].sum()),
             "sim":bal(df[df.oor]["true"].values,df[df.oor]["sim"].values),
             "pers":bal(df[df.oor]["true"].values,df[df.oor]["pers"].values)},
         "predictor_test_mse":round(vm,4),"persistence_mse":round(persist,4),
         "alpha":ALPHA,"train_transitions":int(trm.sum()),"cohort":"cardiac_only"}
    torch.save({"model":model.state_dict(),"dec":dec.state_dict(),"outcome_dec":od.state_dict(),
                "zdim":zdim,"adim":adim,"lab_scaler_mean":lm.tolist(),"lab_scaler_var":lsc.var_.tolist(),
                "labn":LABN,"outcome_names":OUTC}, BASE/"data/world_model_cardiac_delta.pt")
    (BASE/"data/cardiac_delta_metrics.json").write_text(json.dumps(res,indent=2))
    print("\n==== CARDIAC-ONLY + DELTA-AWARE — 1-step direction gate (cardiac TEST) ====",flush=True)
    print(f"  overall            sim={res['overall']['sim']}  pers={res['overall']['pers']}")
    print(f"  abnormal baseline  sim={res['abnormal_baseline']['sim']}  pers={res['abnormal_baseline']['pers']}  (n={res['abnormal_baseline']['n']})")
    print(f"  (pre-delta reference: overall sim≈pers≈0.585; abnormal sim 0.512 vs pers 0.333)")
    print(f"saved world_model_cardiac_delta.pt + cardiac_delta_metrics.json",flush=True)


if __name__=="__main__":
    main()
