#!/usr/bin/env python3
"""
Build the transition substrate and train the enriched AC-JEPA world model.

PIPELINE
  build()  — walk each cohort patient's frozen CLMBR latent sequence (embeddings/*.npy),
             aligned to real MIMIC event times, and emit one-step transitions
                 (z_t, a_t, Δt, z_{t+1}, arm, patient_id)  + LOCF lab panel + mask
             restricted to the index-admission window; keep the train/val/test split.
             Standardize the 14-lab panels with a train-fit StandardScaler.
             -> train_substrate.pkl
  train()  — 1) fit stabilized IPW weights from a logistic π(arm|z);
             2) train the AC-JEPA predictor ~60 epochs (Adam 1e-3, wd 1e-4, batch 256,
                grad-clip 1.0) minimizing IPW-weighted Gaussian NLL on the residual Δz,
                plus a gradient-reversed arm-CE (CRN adversary, λ=0.5); validate against
                the persistence baseline (ẑ=z_t) every 10 epochs;
             3) train the lab decoder (masked-MSE) + outcome decoder (BCE) on frozen latents.
             -> world_model_enriched.pt  (+ world_model_enriched.metrics.json)

ACTION SCHEMA (34-d):  arm one-hot [none,dialysis,transfusion,ventilation] (4)
                     + top-30 procedureevents itemids, multi-hot "started by t" (30).
LAB PANEL (14):        highest-coverage cohort labs (all 471 patients).

Data-local only (real MIMIC-IV); nothing here leaves the machine.

Usage:
  python train_substrate_wm.py --build
  python train_substrate_wm.py --train --epochs 60
  python train_substrate_wm.py --smoke              # tiny synthetic end-to-end check
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pickle
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
V3 = HERE.parent
LONG = V3 / "Longitudinal"
EMB = HERE / "embeddings"
COHORT = LONG / "cohort_data"
CONTEXTS = LONG / "longitudinal_contexts.json"
SUBSTRATE = HERE / "train_substrate.pkl"
ENRICHED = HERE / "checkpoints" / "world_model_enriched.pt"

# ── fixed schema (data-driven; see build_icd_map / cohort stats) ─────────────
# 14 highest-coverage labs, chosen to cover ALL arms' decisive labs:
# dialysis (Creatinine/Urea/K/Bicarbonate), transfusion (Hemoglobin/Hematocrit/RBC/Platelet).
LAB_ITEMS = [50983, 50882, 50868, 50902, 50912, 50931, 50960, 50971,
             51006, 51301, 51222, 51221, 51279, 51265]                       # 14 labs
LAB_NAMES = ["Sodium", "Bicarbonate", "Anion Gap", "Chloride", "Creatinine",
             "Glucose", "Magnesium", "Potassium", "Urea Nitrogen", "White Blood Cells",
             "Hemoglobin", "Hematocrit", "Red Blood Cells", "Platelet Count"]
PROC_ITEMS = [224275, 225459, 225402, 225752, 225792, 224277, 227194, 224274, 225469,
              224263, 225401, 225432, 224276, 228129, 224267, 224560, 225966, 229581,
              229351, 227712, 225454, 224385, 224264, 225441, 221217, 228128, 225794,
              225789, 225802, 221214]                                        # 30 procedures
ACTION_ARMS = ["none", "dialysis", "transfusion", "ventilation"]             # one-hot dims 0-3
ARM_CLASSES = ["dialysis", "transfusion", "ventilation"]                     # IPW/CRN classes
ACTION_DIM = len(ACTION_ARMS) + len(PROC_ITEMS)                              # 4 + 30 = 34
STATE_DIM = 768
N_LABS = len(LAB_ITEMS)
DT_CAP_HOURS = 336.0                                                          # 14 days


def _parse_dt(s):
    if isinstance(s, dt.datetime):
        return s
    s = str(s).replace("T", " ").strip()
    for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s[:len("2000-01-01 00:00:00")] if len(s) >= 19
                                        else s, f)
        except ValueError:
            continue
    return None


def _epoch(d):
    return d.timestamp() if d else np.nan


# ── substrate builder ────────────────────────────────────────────────────────
def build():
    import pandas as pd
    print("[build] loading assets …")
    index = json.load(open(EMB / "index.json"))["patients"]
    contexts = {str(c["subject_id"]): c for c in json.load(open(CONTEXTS))["contexts"]}
    split = json.load(open(COHORT / "cohort_split.json"))["by_subject"]
    sub2split = {}
    for name in ("train", "val", "test"):
        for sid in split.get(name, []):
            sub2split[str(sid)] = name

    adm = pd.read_parquet(COHORT / "admissions.parquet")
    adm_win = {int(r.hadm_id): (r.admittime, r.dischtime) for r in adm.itertuples()}

    labs = pd.read_parquet(COHORT / "labs.parquet")
    labs = labs[labs.itemid.isin(LAB_ITEMS)].dropna(subset=["valuenum"])
    labs["t"] = pd.to_datetime(labs.charttime).astype("int64") / 1e9        # epoch secs
    lab_by_sub = {}                                                          # sid -> itemid -> (times[], vals[])
    for sid, g in labs.groupby("subject_id"):
        d = {}
        for iid, gg in g.groupby("itemid"):
            gg = gg.sort_values("t")
            d[int(iid)] = (gg.t.to_numpy(), gg.valuenum.to_numpy(dtype="float32"))
        lab_by_sub[str(sid)] = d

    proc = pd.read_parquet(COHORT / "procedureevents.parquet")
    proc = proc[proc.itemid.isin(PROC_ITEMS)]
    proc["t"] = pd.to_datetime(proc.starttime).astype("int64") / 1e9
    proc_by_sub = {}                                                         # sid -> itemid -> earliest start epoch
    for sid, g in proc.groupby("subject_id"):
        d = {}
        for iid, gg in g.groupby("itemid"):
            d[int(iid)] = float(gg.t.min())
        proc_by_sub[str(sid)] = d

    proc_col = {iid: i for i, iid in enumerate(PROC_ITEMS)}
    Z, A, DT, ZN, ARM, PID, LAB, MASK, SPLIT = [], [], [], [], [], [], [], [], []
    pat_anchor = {}                                                          # pid -> (anchor_z, mortality, split)
    pat_sim = {}                                                             # pid -> {proc_at_anchor, dt_median}
    n_pat = 0
    for sid, meta in index.items():
        c = contexts.get(sid)
        if not c or sid not in sub2split:
            continue
        npy = EMB / os.path.basename(meta["path"])
        if not npy.exists():
            continue
        z = np.load(npy).astype("float32")
        ev = meta.get("event_times", [])
        T = min(len(z), len(ev))
        if T < 3:
            continue
        z = z[:T]
        ev_dt = [_parse_dt(x) for x in ev[:T]]
        ev_ep = np.array([_epoch(d) for d in ev_dt], dtype="float64")
        anchor_time = _parse_dt(meta["anchor_time"])
        anchor_ep = _epoch(anchor_time)
        family = c["anchor"]["family"]
        arm_cls = ARM_CLASSES.index(family) if family in ARM_CLASSES else -1
        mort = float(bool((c.get("A2_outcome") or {}).get("mortality_1y")))
        spl = sub2split[sid]

        # admission window
        hadm = int(c["hadm_id"])
        win = adm_win.get(hadm)
        if win:
            lo, hi = _epoch(_parse_dt(str(win[0]))), _epoch(_parse_dt(str(win[1])))
        else:
            lo, hi = -np.inf, np.inf
        margin = 6 * 3600
        in_win = [(i) for i in range(T) if (lo - margin) <= ev_ep[i] <= (hi + margin)]
        if len(in_win) < 3:
            in_win = list(range(T))                                          # fallback: whole seq

        lab_d = lab_by_sub.get(sid, {})
        proc_d = proc_by_sub.get(sid, {})

        def locf_panel(t_ep):
            vals = np.zeros(N_LABS, dtype="float32")
            msk = np.zeros(N_LABS, dtype="float32")
            for j, iid in enumerate(LAB_ITEMS):
                arr = lab_d.get(iid)
                if arr is None:
                    continue
                times, vv = arr
                k = np.searchsorted(times, t_ep, side="right") - 1
                if k >= 0:
                    vals[j] = vv[k]
                    msk[j] = 1.0
            return vals, msk

        def action_vec(t_ep):
            a = np.zeros(ACTION_DIM, dtype="float32")
            a[ACTION_ARMS.index("none") if t_ep < anchor_ep
              else ACTION_ARMS.index(family) if family in ACTION_ARMS else 0] = 1.0
            for iid, st in proc_d.items():
                if st <= t_ep:                                               # procedure started by now
                    a[4 + proc_col[iid]] = 1.0
            return a

        # anchor latent for the outcome decoder (last state <= anchor)
        pre = [i for i in range(T) if ev_ep[i] <= anchor_ep]
        aidx = pre[-1] if pre else T - 1
        pat_anchor[sid] = (z[aidx].copy(), mort, spl)

        added = 0; pat_dts = []
        for pos in range(len(in_win) - 1):
            i, inext = in_win[pos], in_win[pos + 1]
            dth = (ev_ep[inext] - ev_ep[i]) / 3600.0
            if not (0.0 < dth <= DT_CAP_HOURS):
                continue
            vals, msk = locf_panel(ev_ep[i])
            Z.append(z[i]); ZN.append(z[inext]); A.append(action_vec(ev_ep[i]))
            DT.append(dth); ARM.append(arm_cls); PID.append(sid)
            LAB.append(vals); MASK.append(msk); SPLIT.append(spl)
            pat_dts.append(dth); added += 1
        if added:
            n_pat += 1
            proc_hot = [1 if proc_d.get(iid, np.inf) <= anchor_ep else 0 for iid in PROC_ITEMS]
            pat_sim[sid] = {"proc_at_anchor": proc_hot,
                            "dt_median": float(np.median(pat_dts)),
                            "family": family, "split": spl}

    Z = np.asarray(Z, "float32"); ZN = np.asarray(ZN, "float32"); A = np.asarray(A, "float32")
    DT = np.asarray(DT, "float32"); ARM = np.asarray(ARM, "int64"); LAB = np.asarray(LAB, "float32")
    MASK = np.asarray(MASK, "float32"); SPLIT = np.asarray(SPLIT); PID = np.asarray(PID)
    print(f"[build] {len(Z)} transitions from {n_pat} patients "
          f"(train {int((SPLIT=='train').sum())} / val {int((SPLIT=='val').sum())} / "
          f"test {int((SPLIT=='test').sum())})")

    # standardize labs on TRAIN observed entries
    tr = SPLIT == "train"
    mean = np.zeros(N_LABS, "float32"); std = np.ones(N_LABS, "float32")
    for j in range(N_LABS):
        obs = LAB[tr, j][MASK[tr, j] > 0]
        if obs.size > 5:
            mean[j] = obs.mean(); std[j] = obs.std() + 1e-6
    LABZ = ((LAB - mean) / std) * MASK                                       # standardized, masked

    substrate = {"Z": Z, "ZN": ZN, "A": A, "DT": DT, "ARM": ARM, "PID": PID,
                 "LABZ": LABZ, "MASK": MASK, "SPLIT": SPLIT,
                 "lab_mean": mean, "lab_std": std,
                 "pat_anchor": pat_anchor,
                 "schema": {"lab_items": LAB_ITEMS, "lab_names": LAB_NAMES,
                            "proc_items": PROC_ITEMS, "action_arms": ACTION_ARMS,
                            "arm_classes": ARM_CLASSES, "action_dim": ACTION_DIM,
                            "state_dim": STATE_DIM, "n_labs": N_LABS}}
    with open(SUBSTRATE, "wb") as f:
        pickle.dump(substrate, f)
    ENRICHED.parent.mkdir(exist_ok=True)
    (ENRICHED.parent / "sim_patient_actions.json").write_text(json.dumps(pat_sim))
    print(f"[build] wrote {SUBSTRATE}  ({SUBSTRATE.stat().st_size/1e6:.1f} MB) "
          f"+ sim_patient_actions.json ({len(pat_sim)} patients)")
    return substrate


# ── IPW: stabilized inverse propensity weights from logistic π(arm|z) ────────
def fit_ipw(torch, Z, ARM, tr_mask, epochs=200, lr=0.05):
    dev = "cpu"
    zt = torch.from_numpy(Z)
    at = torch.from_numpy(ARM)
    valid = at >= 0
    n_arms = len(ARM_CLASSES)
    clf = torch.nn.Linear(Z.shape[1], n_arms)
    opt = torch.optim.Adam(clf.parameters(), lr=lr, weight_decay=1e-4)
    trv = torch.from_numpy(tr_mask) & valid
    idx = trv.nonzero(as_tuple=True)[0]
    for _ in range(epochs):
        opt.zero_grad()
        logit = clf(zt[idx])
        loss = torch.nn.functional.cross_entropy(logit, at[idx])
        loss.backward(); opt.step()
    with torch.no_grad():
        p = torch.softmax(clf(zt), dim=-1)                                   # π(arm|z) [N,3]
        marg = torch.zeros(n_arms)
        for k in range(n_arms):
            marg[k] = (at[trv] == k).float().mean()
        w = torch.ones(Z.shape[0])
        for k in range(n_arms):
            sel = at == k
            w[sel] = marg[k] / p[sel, k].clamp(min=1e-3)                     # stabilized IPW
        w = w.clamp(0.1, 10.0)
        w[~valid] = 1.0
    return w, float(loss)


def train(args):
    import torch
    import torch.nn.functional as F
    from ac_jepa import (ACJEPAPredictor, LabDecoder, OutcomeDecoder,
                         gaussian_nll, masked_mse)
    torch.manual_seed(0)
    sub = pickle.load(open(SUBSTRATE, "rb"))
    Z, ZN, A, DT = sub["Z"], sub["ZN"], sub["A"], sub["DT"]
    ARM, LABZ, MASK, SPLIT = sub["ARM"], sub["LABZ"], sub["MASK"], sub["SPLIT"]
    RES = (ZN - Z).astype("float32")                                         # residual target Δz
    tr = SPLIT == "train"; va = SPLIT == "val"
    print(f"[train] transitions: train {int(tr.sum())} val {int(va.sum())}")

    ipw, clf_loss = fit_ipw(torch, Z, ARM, tr)
    print(f"[train] IPW fit (π(arm|z) CE={clf_loss:.3f})  "
          f"w[min/med/max]={float(ipw.min()):.2f}/{float(ipw.median()):.2f}/{float(ipw.max()):.2f}")

    dev = "cpu"
    zt, at, dtt = torch.from_numpy(Z), torch.from_numpy(A), torch.from_numpy(DT)
    rest, armt = torch.from_numpy(RES), torch.from_numpy(ARM)
    tr_idx = torch.from_numpy(np.where(tr)[0])
    va_idx = torch.from_numpy(np.where(va)[0])

    pred = ACJEPAPredictor(STATE_DIM, ACTION_DIM, n_arms=len(ARM_CLASSES)).to(dev)
    opt = torch.optim.Adam(pred.parameters(), lr=args.lr, weight_decay=1e-4)
    bs, adv_lambda = args.batch_size, 0.5
    t0 = time.time()
    metrics = {"epochs": [], "val": []}
    best = {"mse": float("inf"), "state": None, "epoch": 0}

    def run_val():
        pred.eval()
        with torch.no_grad():
            mu, _, _ = pred(zt[va_idx], at[va_idx], dtt[va_idx], adv_lambda=0.0)
            mse_model = ((mu - rest[va_idx]) ** 2).mean().item()             # predicted residual vs true
            mse_persist = (rest[va_idx] ** 2).mean().item()                  # ẑ=z_t -> residual 0
        return mse_model, mse_persist

    for ep in range(args.epochs):
        pred.train()
        perm = tr_idx[torch.randperm(len(tr_idx))]
        ep_nll = ep_adv = 0.0; nb = 0
        for i in range(0, len(perm), bs):
            b = perm[i:i + bs]
            valid = armt[b] >= 0
            mu, logvar, arm_logits = pred(zt[b], at[b], dtt[b], adv_lambda=adv_lambda)
            nll = gaussian_nll(rest[b], mu, logvar, weight=ipw[b])
            adv = (F.cross_entropy(arm_logits[valid], armt[b][valid])
                   if valid.any() else torch.zeros((), device=dev))
            loss = nll + adv_lambda * adv
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(pred.parameters(), 1.0)
            opt.step()
            ep_nll += float(nll); ep_adv += float(adv); nb += 1
        metrics["epochs"].append({"epoch": ep + 1, "nll": ep_nll / nb, "adv": ep_adv / nb})
        if (ep + 1) % 5 == 0 or ep == 0:
            mm, mp = run_val()
            improv = 100 * (1 - mm / mp) if mp > 0 else 0.0
            metrics["val"].append({"epoch": ep + 1, "val_mse": mm, "persist_mse": mp,
                                   "improvement_pct": improv})
            if mm < best["mse"]:
                best = {"mse": mm, "epoch": ep + 1,
                        "state": {k: v.detach().clone() for k, v in pred.state_dict().items()}}
            print(f"  ep {ep+1:3d}/{args.epochs}  nll={ep_nll/nb:8.2f} adv={ep_adv/nb:.3f}  "
                  f"| val Δz-MSE {mm:.4f} vs persistence {mp:.4f}  ({improv:+.1f}%)  [{time.time()-t0:.0f}s]")
    if best["state"] is not None:                                            # restore best-val predictor
        pred.load_state_dict(best["state"])
        print(f"[train] restored best-val predictor from epoch {best['epoch']} (Δz-MSE {best['mse']:.4f})")

    # ── decoders on frozen latents ───────────────────────────────────────────
    print("[train] training lab + outcome decoders on frozen latents …")
    labt, maskt = torch.from_numpy(LABZ), torch.from_numpy(MASK)
    lab_dec = LabDecoder(STATE_DIM, N_LABS)
    lopt = torch.optim.Adam(lab_dec.parameters(), lr=1e-3, weight_decay=1e-4)
    for ep in range(args.decoder_epochs):
        lab_dec.train(); perm = tr_idx[torch.randperm(len(tr_idx))]
        for i in range(0, len(perm), bs):
            b = perm[i:i + bs]
            loss = masked_mse(lab_dec(zt[b]), labt[b], maskt[b])
            lopt.zero_grad(); loss.backward(); lopt.step()
    with torch.no_grad():
        lab_val = masked_mse(lab_dec(zt[va_idx]), labt[va_idx], maskt[va_idx]).item()

    # outcome decoder on per-patient anchor latents
    pa = sub["pat_anchor"]
    aZ = np.stack([v[0] for v in pa.values()]).astype("float32")
    aY = np.array([v[1] for v in pa.values()], "float32")
    aS = np.array([v[2] for v in pa.values()])
    aZt, aYt = torch.from_numpy(aZ), torch.from_numpy(aY)
    a_tr = torch.from_numpy(np.where(aS == "train")[0]); a_va = torch.from_numpy(np.where(aS == "val")[0])
    out_dec = OutcomeDecoder(STATE_DIM)
    oopt = torch.optim.Adam(out_dec.parameters(), lr=1e-3, weight_decay=1e-3)
    for ep in range(args.decoder_epochs * 4):
        out_dec.train()
        loss = F.binary_cross_entropy_with_logits(out_dec(aZt[a_tr]), aYt[a_tr])
        oopt.zero_grad(); loss.backward(); oopt.step()
    with torch.no_grad():
        pv = torch.sigmoid(out_dec(aZt[a_va])).numpy(); yv = aY[a_va.numpy()]
    auc = _auc(pv.tolist(), yv.tolist())
    print(f"[train] lab-decoder val masked-MSE={lab_val:.4f} | outcome val mortality-AUC={auc:.3f}")

    ENRICHED.parent.mkdir(exist_ok=True)
    torch.save({"predictor": pred.state_dict(), "lab_decoder": lab_dec.state_dict(),
                "outcome_decoder": out_dec.state_dict(),
                "lab_mean": sub["lab_mean"], "lab_std": sub["lab_std"],
                "schema": sub["schema"],
                "config": {"epochs": args.epochs, "lr": args.lr, "batch_size": bs,
                           "adv_lambda": adv_lambda, "dt_cap_hours": DT_CAP_HOURS}}, ENRICHED)
    mm, mp = run_val()
    metrics["final"] = {"val_residual_mse": mm, "persistence_mse": mp,
                        "improvement_over_persistence_pct": 100 * (1 - mm / mp) if mp > 0 else 0.0,
                        "lab_decoder_val_masked_mse": lab_val, "outcome_val_mortality_auc": auc,
                        "n_transitions": int(len(Z))}
    (ENRICHED.parent / "world_model_enriched.metrics.json").write_text(json.dumps(metrics, indent=2))
    print(f"[train] saved {ENRICHED}  ({ENRICHED.stat().st_size/1e6:.1f} MB)")
    print(f"[train] FINAL: Δz-MSE {mm:.4f} vs persistence {mp:.4f} "
          f"({metrics['final']['improvement_over_persistence_pct']:+.1f}%), "
          f"lab-MSE {lab_val:.3f}, mortality-AUC {auc:.3f}")


def _auc(scores, labels):
    pairs = sorted(zip(scores, labels)); pos = sum(labels); neg = len(labels) - pos
    if pos == 0 or neg == 0:
        return 0.5
    rank_sum = 0; i = 0; ss = sorted(scores)
    ranks = {}
    for r, s in enumerate(ss, 1):
        ranks.setdefault(s, []).append(r)
    rsum = sum(sum(ranks[s]) / len(ranks[s]) for s, l in zip(scores, labels) if l == 1)
    return (rsum - pos * (pos + 1) / 2) / (pos * neg)


def smoke():
    """Tiny synthetic end-to-end: verify shapes + training step run without real data."""
    import torch
    from ac_jepa import ACJEPAPredictor, gaussian_nll
    N = 512
    Z = np.random.randn(N, STATE_DIM).astype("float32")
    A = np.zeros((N, ACTION_DIM), "float32"); A[np.arange(N), np.random.randint(0, 4, N)] = 1
    DT = (np.random.rand(N) * 48).astype("float32")
    ARM = np.random.randint(0, 3, N).astype("int64")
    RES = (0.1 * Z + np.random.randn(N, STATE_DIM) * 0.05).astype("float32")
    pred = ACJEPAPredictor(STATE_DIM, ACTION_DIM, 3)
    opt = torch.optim.Adam(pred.parameters(), lr=1e-3)
    zt, at, dtt, rt, armt = map(torch.from_numpy, (Z, A, DT, RES, ARM))
    for ep in range(5):
        mu, lv, arm = pred(zt, at, dtt, adv_lambda=0.5)
        loss = gaussian_nll(rt, mu, lv) + 0.5 * torch.nn.functional.cross_entropy(arm, armt)
        opt.zero_grad(); loss.backward(); opt.step()
    print(f"smoke OK — final loss {float(loss):.3f}, action_dim={ACTION_DIM}, labs={N_LABS}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--decoder_epochs", type=int, default=40)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--batch_size", type=int, default=256)
    args = ap.parse_args()
    if args.smoke:
        smoke()
    if args.build:
        build()
    if args.train:
        train(args)
    if not (args.smoke or args.build or args.train):
        ap.print_help()
