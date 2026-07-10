"""
train_substrate_wm.py — Step 2b/2c: AC-JEPA world model on the cleaned substrate + lab decoder.

State  z_t : frozen CLMBR latent (768).           [decode-only design; probe median R2=0.49]
Action a_t : enriched 34-dim vector (per-agent drips w/ Option-A rates + procedures + PCI/CABG).
Predict    : residual next latent  ẑ_{t+1} = z_t + f(adapter(z_t), enc(a_t), Δt)   (gaussian head).
Deconfound : on the MEASURED confounder = treatment ARM (medical/pci/cabg, 0.83-0.98 recoverable
             from z). Stabilized IPW over π(arm|z_t) + CRN adversary (grad-reversed) on the adapter.
             (Continuous-dose GPS deconfounding is future work; arm is the dominant selection bias.)
Readout    : lab decoder z->14 core labs (LOCF targets), trained separately.

Gates (Step 2c): (1) val 1-step MSE < persistence (ẑ=z_t); (2) treatment_predictability drops from
raw z to adapter z̃; (3) lab-direction (Rising/Falling/Stable) balanced-acc on val. Reports train/val gap.

Run: simr python train_substrate_wm.py   (uses GPU if free).
"""
from __future__ import annotations

import json, pickle
from pathlib import Path
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

BASE = Path("/scratch/users/karun09/Version_2/counterfactual_simulation")
SUB = BASE / "data/train_substrate.pkl"
TRAJ = BASE / "data/trajectories.pkl"
SPLITS = BASE / "data/splits.json"
OUT = BASE / "data"
ARM = {"medical": 0, "pci": 1, "cabg": 2}
CORE = {  # LOINC -> name (same panel as the probe)
    "LOINC/2160-0": "creatinine", "LOINC/3094-0": "bun", "LOINC/2823-3": "potassium",
    "LOINC/2951-2": "sodium", "LOINC/2075-0": "chloride", "LOINC/1963-8": "bicarbonate",
    "LOINC/1863-0": "anion_gap", "LOINC/2345-7": "glucose", "LOINC/2601-3": "magnesium",
    "LOINC/2777-1": "phosphate", "LOINC/718-7": "hemoglobin", "LOINC/4544-3": "hematocrit",
    "LOINC/777-3": "platelets", "LOINC/6690-2": "wbc"}
LOINCS = list(CORE); LABN = [CORE[c] for c in LOINCS]; NL = len(LOINCS)
DEV = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ---------- grad reversal ----------
class _GradRev(torch.autograd.Function):
    @staticmethod
    def forward(ctx, x, lam): ctx.lam = lam; return x.view_as(x)
    @staticmethod
    def backward(ctx, g): return -ctx.lam * g, None
def grad_reverse(x, lam): return _GradRev.apply(x, lam)


# ---------- model ----------
class ACJEPA(nn.Module):
    def __init__(self, zdim, adim, n_arm=3):
        super().__init__()
        self.adapter = nn.Sequential(nn.Linear(zdim, 128), nn.ReLU())
        self.act_enc = nn.Sequential(nn.Linear(adim, 32), nn.ReLU(), nn.Dropout(0.1))
        self.dt_enc  = nn.Sequential(nn.Linear(2, 16), nn.ReLU())
        self.trunk = nn.Sequential(
            nn.Linear(128 + 32 + 16, 256), nn.LayerNorm(256), nn.ReLU(), nn.Dropout(0.1),
            nn.Linear(256, 256), nn.LayerNorm(256), nn.ReLU())
        self.mu = nn.Linear(256, zdim); self.logvar = nn.Linear(256, zdim)
        self.arm_head = nn.Linear(128, n_arm)          # CRN adversary
    def dtf(self, dt):
        dt = dt.clamp(min=0)
        return torch.stack([torch.log1p(dt), (dt / 24.0).clamp(max=30.0)], -1)
    def _core(self, z, a, dt):
        h = self.adapter(z)
        x = torch.cat([h, self.act_enc(a), self.dt_enc(self.dtf(dt))], -1)
        return h, self.trunk(x)
    def forward(self, z, a, dt):
        _, t = self._core(z, a, dt); return z + self.mu(t)
    def nll(self, z, a, dt, zn, w):
        _, t = self._core(z, a, dt)
        mu, lv = self.mu(t), self.logvar(t).clamp(-8, 8)
        tgt = zn - z
        per = (0.5 * (lv + (tgt - mu) ** 2 / lv.exp())).mean(-1)
        return (per * w).sum() / w.sum()
    def adv_loss(self, z, arm, lam):
        h = grad_reverse(self.adapter(z), lam)
        return F.cross_entropy(self.arm_head(h), arm)


class LabDecoder(nn.Module):
    def __init__(self, zdim, nl):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(zdim, 128), nn.ReLU(), nn.Dropout(0.1), nn.Linear(128, nl))
    def forward(self, z): return self.net(z)


# ---------- data ----------
def locf_panel(sub, traj):
    tmap = {int(t["patient_id"]): t for t in traj}
    Y = {}
    for e in sub:
        pid = int(e["patient_id"]); tr = tmap.get(pid)
        times = pd.to_datetime(np.asarray(e["abs_times"]))
        ser = {c: [] for c in LOINCS}
        if tr:
            for ev in tr["events"]:
                c = ev.get("code")
                if c in ser and ev.get("value") is not None:
                    ser[c].append((pd.Timestamp(ev["t"]), float(ev["value"])))
            for c in ser: ser[c].sort()
        M = np.full((len(times), NL), np.nan, np.float32)
        for i, t in enumerate(times):
            for j, c in enumerate(LOINCS):
                v = None
                for tt, vv in ser[c]:
                    if tt <= t: v = vv
                    else: break
                if v is not None: M[i, j] = v
        Y[pid] = M
    return Y


def build(sub, labY):
    """transitions: z,a,dt,zn,arm,pid + lab rows at t and t+1."""
    Z, A, DT, ZN, ARr, PID, Lt, Ln = [], [], [], [], [], [], [], []
    for e in sub:
        pid = int(e["patient_id"]); s = e["s"]; a = e["action_matrix"]; h = e["hours"]
        arm = ARM.get(str(e["outcomes"].get("arm", "medical")), 0)
        Y = labY[pid]
        T = len(s)
        if T < 2: continue
        for i in range(1, T):
            Z.append(s[i-1]); ZN.append(s[i]); A.append(a[i]); DT.append(max(h[i]-h[i-1], 0.0))
            ARr.append(arm); PID.append(pid); Lt.append(Y[i-1]); Ln.append(Y[i])
    return (np.array(Z), np.array(A), np.array(DT, np.float32), np.array(ZN),
            np.array(ARr), np.array(PID), np.array(Lt), np.array(Ln))


def main():
    sub = pickle.load(open(SUB, "rb"))
    traj = pickle.load(open(TRAJ, "rb"))
    sp = json.loads(SPLITS.read_text())
    tr_s, va_s = set(sp["splits"]["train"]), set(sp["splits"]["val"])
    labY = locf_panel(sub, traj)
    Z, A, DT, ZN, AR, PID, Lt, Ln = build(sub, labY)
    zdim, adim = Z.shape[1], A.shape[1]
    trm, vam = np.isin(PID, list(tr_s)), np.isin(PID, list(va_s))
    print(f"transitions: {len(Z):,}  (train {trm.sum():,} / val {vam.sum():,})  zdim={zdim} adim={adim}")

    # ---- stabilized IPW on arm ----
    ppl = LogisticRegression(max_iter=2000, C=1.0, multi_class="multinomial")
    ppl.fit(Z[trm], AR[trm])
    proba = ppl.predict_proba(Z); classes = list(ppl.classes_)
    marg = np.bincount(AR[trm], minlength=3) / trm.sum()
    pa = proba[np.arange(len(AR)), [classes.index(a) for a in AR]]
    W = np.clip(marg[AR] / np.clip(pa, 1e-3, None), 0.1, 10.0).astype(np.float32)
    print(f"IPW: mean={W.mean():.2f} min={W.min():.2f} max={W.max():.2f}")

    # tensors
    def T_(x): return torch.tensor(x, device=DEV)
    Zt, At, DTt, ZNt, Wt = T_(Z).float(), T_(A).float(), T_(DT).float(), T_(ZN).float(), T_(W)
    ARt = T_(AR).long()
    tri = np.where(trm)[0]; vai = np.where(vam)[0]

    # persistence baseline (val)
    persist = float(F.mse_loss(ZNt[vai], Zt[vai]).item())

    model = ACJEPA(zdim, adim).to(DEV)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
    LAM = 0.5; EP = 60; BS = 256
    print(f"params={sum(p.numel() for p in model.parameters())/1e6:.2f}M  persistence_val_mse={persist:.5f}")
    hist = []
    for ep in range(EP):
        model.train(); perm = tri[torch.randperm(len(tri)).numpy()]
        for b in range(0, len(perm), BS):
            idx = perm[b:b+BS]
            loss = model.nll(Zt[idx], At[idx], DTt[idx], ZNt[idx], Wt[idx]) \
                 + LAM * model.adv_loss(Zt[idx], ARt[idx], LAM)
            opt.zero_grad(); loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0); opt.step()
        if ep % 10 == 9 or ep == EP-1:
            model.eval()
            with torch.no_grad():
                vp = model(Zt[vai], At[vai], DTt[vai]); vm = float(F.mse_loss(vp, ZNt[vai]).item())
                tp = model(Zt[tri], At[tri], DTt[tri]); tm = float(F.mse_loss(tp, ZNt[tri]).item())
            hist.append({"epoch": ep, "train_mse": round(tm,5), "val_mse": round(vm,5)})
            print(f"  ep{ep:2d} train_mse={tm:.5f} val_mse={vm:.5f} (persist={persist:.5f})")

    val_mse = hist[-1]["val_mse"]; train_mse = hist[-1]["train_mse"]

    # ---- treatment_predictability: arm from raw z vs adapter z̃ (val) ----
    model.eval()
    with torch.no_grad():
        ztil = model.adapter(Zt).cpu().numpy()
    def arm_auc(feat):
        lr = LogisticRegression(max_iter=1000, multi_class="multinomial").fit(feat[trm], AR[trm])
        return float((lr.predict(feat[vam]) == AR[vam]).mean())
    tp_raw = arm_auc(Z); tp_bal = arm_auc(ztil)

    # ---- lab decoder (train on train timepoints; targets standardized on train) ----
    valid = np.isfinite(Lt).all(1) if False else np.isfinite(Lt)  # per-lab mask
    lsc = StandardScaler().fit(np.nan_to_num(Lt[trm], nan=np.nanmedian(Lt[trm], axis=0)))
    def std(x): return (np.nan_to_num(x, nan=0.0) - lsc.mean_) / np.sqrt(lsc.var_)
    dec = LabDecoder(zdim, NL).to(DEV); dopt = torch.optim.Adam(dec.parameters(), 1e-3, weight_decay=1e-4)
    Ltt = torch.tensor(std(Lt), device=DEV).float(); mask_t = torch.tensor(np.isfinite(Lt), device=DEV).float()
    for ep in range(80):
        dec.train(); perm = tri[torch.randperm(len(tri)).numpy()]
        for b in range(0, len(perm), 512):
            idx = perm[b:b+512]
            pr = dec(Zt[idx]); m = mask_t[idx]
            loss = (((pr - Ltt[idx])**2) * m).sum() / m.sum().clamp(min=1)
            dopt.zero_grad(); loss.backward(); dopt.step()

    # ---- lab-direction (Rising/Falling/Stable) on val: predicted ẑ_{t+1} vs z_t ----
    dec.eval()
    with torch.no_grad():
        zhat = model(Zt[vai], At[vai], DTt[vai])
        dpred = (dec(zhat) - dec(Zt[vai])).cpu().numpy()   # predicted std-lab change
    dtrue = std(Ln[vai]) - std(Lt[vai])
    okmask = np.isfinite(Ln[vai]) & np.isfinite(Lt[vai])
    band = 0.15
    def cls(x): return np.where(x > band, 2, np.where(x < -band, 0, 1))
    dir_acc = {}
    for j, nm in enumerate(LABN):
        m = okmask[:, j]
        if m.sum() < 50: continue
        yt, yp = cls(dtrue[m, j]), cls(dpred[m, j])
        # balanced acc
        accs = [(yp[yt==k]==k).mean() for k in [0,1,2] if (yt==k).sum()>0]
        dir_acc[nm] = round(float(np.mean(accs)), 3)
    mean_dir = round(float(np.mean(list(dir_acc.values()))), 3)

    torch.save({"model": model.state_dict(), "dec": dec.state_dict(),
                "zdim": zdim, "adim": adim, "lab_scaler_mean": lsc.mean_.tolist(),
                "lab_scaler_var": lsc.var_.tolist(), "labn": LABN}, OUT / "world_model_enriched.pt")
    metrics = {"persistence_val_mse": round(persist,5), "val_mse": round(val_mse,5),
               "train_mse": round(train_mse,5), "beats_persistence": bool(val_mse < persist),
               "train_val_gap": round(val_mse-train_mse,5),
               "treatment_predictability_raw_z": round(tp_raw,3),
               "treatment_predictability_adapter": round(tp_bal,3),
               "arm_prevalence_majority": round(float(marg.max()),3),
               "lab_direction_balacc": dir_acc, "lab_direction_mean": mean_dir, "history": hist}
    (OUT / "world_model_enriched_metrics.json").write_text(json.dumps(metrics, indent=2))
    print("\n==== RESULTS ====")
    print(f"beats_persistence: {metrics['beats_persistence']}  (val {val_mse:.5f} vs persist {persist:.5f})")
    print(f"train/val gap: {metrics['train_val_gap']:.5f}  (overfit check)")
    print(f"treatment_predictability arm:  raw z={tp_raw:.3f} -> adapter z̃={tp_bal:.3f}  (majority={marg.max():.3f})")
    print(f"lab-direction mean bal-acc (val): {mean_dir}  (chance=0.333)")
    for nm, v in sorted(dir_acc.items(), key=lambda x:-x[1]): print(f"    {nm:12s} {v}")
    print(f"\nwrote {OUT/'world_model_enriched.pt'} + metrics json")


if __name__ == "__main__":
    main()
