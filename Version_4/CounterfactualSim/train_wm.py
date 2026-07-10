#!/usr/bin/env python3
"""
train_wm.py — cohort trainer for the V4 latent world model (P1b).

Replaces V3's train_substrate_wm.py *for the predictor*. The key difference:
V3 flattened the cohort into independent one-step transitions, which destroys the
temporal structure the teacher-forcing + rollout objective needs. This builds
**per-patient fixed-Δt trajectories** on a grid around the anchor and trains
latent_wm.LatentWorldModel with the V-JEPA 2-AC objective (TF + autoregressive
rollout), then reports the honest multi-step gate on the held-out val split:
the AR rollout must beat BOTH persistence (Δz=0) AND the global mean-Δ baseline,
in-distribution.

Trajectory grid (matches serve-time rollout + benchmark-b horizon):
  grid times   = anchor + (k - PRE)·STEP_H hours,  k = 0..PRE+POST
  state z_k    = LOCF over the CLMBR event latents (last event at/<= grid time)
  action a_k   = arm one-hot (none before anchor, patient's family at/after) (4)
               + top-30 procedureevents multi-hot "started by grid time"     (30)
  dt_k         = STEP_H  (constant)

The causal-deconfounding layer (balance adapter / propensity / DR / positivity)
is added on top in P2 (causal.py); this file trains only the predictor so its
gate can be read in isolation.

Usage:
  python train_wm.py --build            # -> wm_sequences.pkl
  python train_wm.py --train --epochs 150
  python train_wm.py --smoke            # tiny synthetic end-to-end
Data-local only (real MIMIC-IV latents); nothing leaves the machine.
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import time
from pathlib import Path

import numpy as np

# reuse the exact action schema + datetime parsing from the V3 substrate builder
from train_substrate_wm import (ACTION_ARMS, ACTION_DIM, ARM_CLASSES, PROC_ITEMS,
                                 STATE_DIM, _epoch, _parse_dt)

HERE = Path(__file__).resolve().parent
V4 = HERE.parent
LONG = V4 / "Longitudinal"
EMB = HERE / "embeddings"
COHORT = LONG / "cohort_data"
CONTEXTS = LONG / "longitudinal_contexts.json"
SEQ_PKL = HERE / "wm_sequences.pkl"
CKPT = HERE / "checkpoints" / "latent_wm.pt"

PRE, POST, STEP_H = 2, 3, 24.0        # anchor-48h .. anchor+72h on a 24h grid -> 6 states


def build():
    import pandas as pd
    print("[build] loading assets …")
    index = json.load(open(EMB / "index.json"))["patients"]
    contexts = {str(c["subject_id"]): c for c in json.load(open(CONTEXTS))["contexts"]}
    split = json.load(open(COHORT / "cohort_split.json"))["by_subject"]
    sub2split = {str(s): name for name in ("train", "val", "test") for s in split.get(name, [])}

    proc = pd.read_parquet(COHORT / "procedureevents.parquet")
    proc = proc[proc.itemid.isin(PROC_ITEMS)]
    proc["t"] = pd.to_datetime(proc.starttime).astype("int64") / 1e9
    proc_by_sub = {}
    for sid, g in proc.groupby("subject_id"):
        proc_by_sub[str(sid)] = {int(iid): float(gg.t.min()) for iid, gg in g.groupby("itemid")}
    proc_col = {iid: i for i, iid in enumerate(PROC_ITEMS)}

    S = PRE + POST + 1
    ZS, AS_, DTS, ARM, MORT, PID, SPLIT = [], [], [], [], [], [], []
    n_skip = 0
    for sid, meta in index.items():
        c = contexts.get(sid)
        if not c or sid not in sub2split:
            n_skip += 1
            continue
        npy = EMB / os.path.basename(meta["path"])
        if not npy.exists():
            n_skip += 1
            continue
        z = np.load(npy).astype("float32")
        ev = meta.get("event_times", [])
        T = min(len(z), len(ev))
        if T < 3:
            n_skip += 1
            continue
        z = z[:T]
        ev_ep = np.array([_epoch(_parse_dt(x)) for x in ev[:T]], dtype="float64")
        order = np.argsort(ev_ep)                       # ensure chronological
        z, ev_ep = z[order], ev_ep[order]
        anchor_ep = _epoch(_parse_dt(meta["anchor_time"]))
        if not np.isfinite(anchor_ep):
            n_skip += 1
            continue
        family = c["anchor"]["family"]
        arm_cls = ARM_CLASSES.index(family) if family in ARM_CLASSES else -1
        mort = float(bool((c.get("A2_outcome") or {}).get("mortality_1y")))
        proc_d = proc_by_sub.get(sid, {})

        z_seq = np.zeros((S, STATE_DIM), "float32")
        a_seq = np.zeros((S, ACTION_DIM), "float32")
        for k in range(S):
            g = anchor_ep + (k - PRE) * STEP_H * 3600.0
            j = int(np.searchsorted(ev_ep, g, side="right") - 1)
            j = max(0, j)                                # LOCF; clamp before-first to first state
            z_seq[k] = z[j]
            # arm one-hot
            if g < anchor_ep:
                a_seq[k, ACTION_ARMS.index("none")] = 1.0
            elif family in ACTION_ARMS:
                a_seq[k, ACTION_ARMS.index(family)] = 1.0
            else:
                a_seq[k, 0] = 1.0
            for iid, st in proc_d.items():
                if st <= g:
                    a_seq[k, len(ACTION_ARMS) + proc_col[iid]] = 1.0

        ZS.append(z_seq); AS_.append(a_seq); DTS.append(np.full(S, STEP_H, "float32"))
        ARM.append(arm_cls); MORT.append(mort); PID.append(sid); SPLIT.append(sub2split[sid])

    out = {"Z": np.asarray(ZS, "float32"), "A": np.asarray(AS_, "float32"),
           "DT": np.asarray(DTS, "float32"), "ARM": np.asarray(ARM, "int64"),
           "MORT": np.asarray(MORT, "float32"), "PID": np.asarray(PID),
           "SPLIT": np.asarray(SPLIT),
           "grid": {"PRE": PRE, "POST": POST, "STEP_H": STEP_H, "S": S},
           "schema": {"action_arms": ACTION_ARMS, "arm_classes": ARM_CLASSES,
                      "proc_items": PROC_ITEMS, "action_dim": ACTION_DIM,
                      "state_dim": STATE_DIM}}
    with open(SEQ_PKL, "wb") as f:
        pickle.dump(out, f)
    sp = out["SPLIT"]
    print(f"[build] {len(ZS)} patient trajectories (S={S} states each), skipped {n_skip}")
    print(f"[build]   train {int((sp=='train').sum())} / val {int((sp=='val').sum())} "
          f"/ test {int((sp=='test').sum())}  -> {SEQ_PKL.name} ({SEQ_PKL.stat().st_size/1e6:.1f} MB)")
    return out


def _baselines(states, targets):
    """MSE of persistence (Δz=0) and global mean-Δ (fit on the same split's states)."""
    import torch
    persist = torch.mean((states - targets) ** 2).item()
    mean_dz = (targets - states).mean((0, 1))
    meanb = torch.mean((states + mean_dz - targets) ** 2).item()
    return persist, meanb


def train(args):
    import torch
    import torch.nn.functional as F
    from latent_wm import LatentWorldModel, rollout_predictions, wm_loss
    torch.manual_seed(0)
    sub = pickle.load(open(SEQ_PKL, "rb"))
    Z, A, DT, SPLIT = sub["Z"], sub["A"], sub["DT"], sub["SPLIT"]
    # inputs are steps 1..S-1, targets are steps 2..S  (S-1 transitions per patient)
    states_all = torch.from_numpy(Z[:, :-1]); targets_all = torch.from_numpy(Z[:, 1:])
    acts_all = torch.from_numpy(A[:, :-1]); dts_all = torch.from_numpy(DT[:, :-1])
    tr = np.where(SPLIT == "train")[0]; va = np.where(SPLIT == "val")[0]
    tri, vai = torch.from_numpy(tr), torch.from_numpy(va)
    print(f"[train] {len(tr)} train / {len(va)} val trajectories, "
          f"{states_all.shape[1]} transitions each, D={states_all.shape[2]}")

    model = LatentWorldModel(state_dim=sub["schema"]["state_dim"],
                             action_dim=sub["schema"]["action_dim"],
                             hidden=args.hidden, depth=args.depth, heads=8)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr, weight_decay=1e-5)
    bs = args.batch_size
    t0 = time.time()
    best = {"ar": float("inf"), "state": None, "epoch": 0}
    per_va, meanb_va = _baselines(states_all[vai], targets_all[vai])

    def val_ar():
        model.eval()
        with torch.no_grad():
            _, z_ar = rollout_predictions(model, states_all[vai], acts_all[vai], dts_all[vai])
            return F.mse_loss(z_ar, targets_all[vai]).item()

    for ep in range(args.epochs):
        model.train()
        perm = tri[torch.randperm(len(tri))]
        ep_loss = 0.0; nb = 0
        for i in range(0, len(perm), bs):
            b = perm[i:i + bs]
            z_tf, z_ar = rollout_predictions(model, states_all[b], acts_all[b], dts_all[b])
            loss = wm_loss(z_tf, targets_all[b]) + wm_loss(z_ar, targets_all[b])
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            ep_loss += float(loss.detach()); nb += 1
        if (ep + 1) % args.eval_every == 0 or ep == 0:
            ar = val_ar()
            if ar < best["ar"]:
                best = {"ar": ar, "epoch": ep + 1,
                        "state": {k: v.detach().clone() for k, v in model.state_dict().items()}}
            print(f"  ep {ep+1:3d}/{args.epochs}  loss={ep_loss/nb:.4f}  "
                  f"| val AR-MSE {ar:.4f}  (persist {per_va:.4f}, mean-Δ {meanb_va:.4f})  "
                  f"[{time.time()-t0:.0f}s]")
    if best["state"] is not None:
        model.load_state_dict(best["state"])

    ar = val_ar()
    improv = 100 * (1 - ar / per_va) if per_va > 0 else 0.0
    beats = ar < per_va and ar < meanb_va
    CKPT.parent.mkdir(exist_ok=True)
    torch.save({"model": model.state_dict(),
                "config": {"hidden": args.hidden, "depth": args.depth,
                           "state_dim": sub["schema"]["state_dim"],
                           "action_dim": sub["schema"]["action_dim"]},
                "grid": sub["grid"], "schema": sub["schema"],
                "metrics": {"val_ar_mse": ar, "persistence_mse": per_va,
                            "mean_dz_mse": meanb_va, "best_epoch": best["epoch"],
                            "improvement_over_persistence_pct": improv,
                            "exit_gate_pass": bool(beats)}}, CKPT)
    print(f"[train] best val AR-MSE {ar:.4f} @ep{best['epoch']}  "
          f"vs persistence {per_va:.4f} ({improv:+.1f}%), mean-Δ {meanb_va:.4f}")
    print(f"[train] EXIT GATE (AR beats persistence AND mean-Δ, in-distribution): "
          f"{'PASS' if beats else 'FAIL'}  -> {CKPT.name}")


def smoke():
    import torch
    from latent_wm import LatentWorldModel, rollout_predictions, wm_loss, _make_synthetic
    S = PRE + POST + 1
    states, actions, dts, targets = _make_synthetic(48, S - 1, 64, ACTION_DIM, seed=1)
    m = LatentWorldModel(64, ACTION_DIM, hidden=96, depth=2, heads=8)
    opt = torch.optim.Adam(m.parameters(), lr=3e-3)
    for _ in range(60):
        z_tf, z_ar = rollout_predictions(m, states, actions, dts)
        loss = wm_loss(z_tf, targets) + wm_loss(z_ar, targets)
        opt.zero_grad(); loss.backward(); opt.step()
    print(f"smoke OK — loss {float(loss.detach()):.4f}, action_dim={ACTION_DIM}, S={S}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--epochs", type=int, default=150)
    ap.add_argument("--eval_every", type=int, default=10)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--batch_size", type=int, default=32)
    ap.add_argument("--hidden", type=int, default=384)
    ap.add_argument("--depth", type=int, default=4)
    args = ap.parse_args()
    if args.smoke:
        smoke()
    if args.build:
        build()
    if args.train:
        train(args)
    if not (args.smoke or args.build or args.train):
        ap.print_help()