#!/usr/bin/env python3
"""
train_hourly_wm.py — P1: train the hourly world model on hourly_substrate.pkl.

Predicts next-hour STATE (vitals+labs+procedures) from current state + drug ACTION, so a
counterfactual = roll forward under a modified drug sequence.

Handles real-ICU irregular sampling honestly:
  - inputs are forward-filled + standardized (no NaN into the net);
  - the loss is MASKED to cells actually OBSERVED at t+1 (labs supervised only at draw hours,
    vitals densely, procedures always);
  - objective = teacher-forcing (full sequence, 1 pass) + a bounded K-step autoregressive
    rollout (anti-drift; full 71-step rollout is too slow on CPU).

Gate: on held-out stays, the model's multi-step rollout beats persistence (carry last state)
AND mean-Δ over a 12-hour window.
"""
from __future__ import annotations

import pickle
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from latent_wm import LatentWorldModel

HERE = Path(__file__).resolve().parent
SUB = HERE / "hourly_substrate.pkl"
CKPT = HERE / "checkpoints" / "hourly_wm.pt"
AR_TRAIN, AR_EVAL = 4, 12


def ffill(a):
    """Forward-fill NaNs down axis 0 (time), vectorized; leading NaNs left as NaN."""
    import pandas as pd
    return pd.DataFrame(a).ffill().to_numpy(dtype="float32")


def masked_mse(pred, tgt, mask):
    m = mask.sum()
    return ((pred - tgt) ** 2 * mask).sum() / m.clamp(min=1.0)


def build_tensors(sub):
    meta = sub["meta"]; stays = sub["stays"]
    S, D, A = meta["HMAX"], len(meta["state_cols"]), len(meta["drug_cols"])
    n_cont = len(meta["vit_cols"]) + len(meta["lab_cols"])           # continuous state cols (rest = procedures)
    ids = sorted(stays)
    rawZ = np.stack([stays[i]["Z"] for i in ids]).astype("float32")  # [N,S,D] NaN=unobserved
    Araw = np.stack([stays[i]["A"] for i in ids]).astype("float32")  # [N,S,A]
    mask = (~np.isnan(rawZ)).astype("float32")                        # observation mask
    return ids, rawZ, Araw, mask, meta, n_cont


def main():
    torch.manual_seed(0)
    sub = pickle.load(open(SUB, "rb"))
    # restrict to the equipoise cohort: only patients who could HONESTLY have received any
    # of medical / PCI / CABG (multi-way common support) — the identifiable counterfactuals
    import pandas as pd
    eq = pd.read_parquet(HERE / "cad_equipoise.parquet")
    eq_hadms = set(eq[eq.equipoise == 1].hadm_id.astype(int))
    before = len(sub["stays"])
    sub["stays"] = {s: v for s, v in sub["stays"].items() if v["hadm_id"] in eq_hadms}
    print(f"[hwm] equipoise filter: {len(sub['stays']):,}/{before:,} ICU stays "
          f"(patients who could have gotten any of medical/PCI/CABG)")
    ids, rawZ, Araw, mask, meta, n_cont = build_tensors(sub)
    N, S, D = rawZ.shape; Ad = Araw.shape[2]
    rng = np.random.default_rng(0); perm = rng.permutation(N)
    va_ids = set(perm[: N // 10]); tr = np.array([k not in va_ids for k in range(N)]); va = ~tr
    print(f"[hwm] {N:,} stays (train {tr.sum():,}/val {va.sum():,}), state_dim {D}, action_dim {Ad}")

    # standardize continuous state on observed TRAIN cells; procedures left 0/1
    cont = slice(0, n_cont)
    obs_tr = mask[tr][:, :, cont] > 0
    xc = rawZ[tr][:, :, cont]
    mu = np.array([xc[:, :, j][obs_tr[:, :, j]].mean() if obs_tr[:, :, j].any() else 0.0 for j in range(n_cont)], "float32")
    sd = np.array([xc[:, :, j][obs_tr[:, :, j]].std() + 1e-3 if obs_tr[:, :, j].any() else 1.0 for j in range(n_cont)], "float32")
    Zstd = rawZ.copy(); Zstd[:, :, cont] = (rawZ[:, :, cont] - mu) / sd
    # inputs: ffill per stay, leading NaN -> 0 (=mean)
    Zin = np.stack([ffill(Zstd[i]) for i in range(N)]); Zin = np.nan_to_num(Zin, nan=0.0)
    # actions: log1p + standardize on train
    Alog = np.log1p(np.clip(Araw, 0, None))
    amu = Alog[tr].reshape(-1, Ad).mean(0); asd = Alog[tr].reshape(-1, Ad).std(0) + 1e-3
    Ain = (Alog - amu) / asd
    # targets standardized (masked); NaN->0 (masked out anyway)
    Ztgt = np.nan_to_num(Zstd, nan=0.0)

    Zin_t, Ain_t, Ztgt_t, mask_t = map(lambda x: torch.tensor(x, dtype=torch.float32),
                                       (Zin, Ain, Ztgt, mask))
    del Zstd, Zin, Ain, Ztgt, Alog, rawZ, Araw          # free numpy copies
    import gc; gc.collect()
    tri = torch.tensor(np.where(tr)[0]); vai = torch.tensor(np.where(va)[0])
    if len(tri) > 6000:                                              # subsample train for CPU speed
        tri = tri[torch.randperm(len(tri))[:6000]]
    dt = torch.ones(1)                                               # 1-hour steps

    model = LatentWorldModel(state_dim=D, action_dim=Ad, hidden=128, depth=3, heads=8)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)

    def tf_and_ar(idx, ar_steps):
        st, ac = Zin_t[idx], Ain_t[idx]
        dts = dt.expand(len(idx), S)
        # teacher forcing: predict z_{t+1} for all t
        z_tf = model.forward(st, ac, dts)                            # [B,S,D], out[:,t]=pred z_{t+1}
        tf_pred, tf_tgt, tf_m = z_tf[:, :-1], Ztgt_t[idx][:, 1:], mask_t[idx][:, 1:]
        # bounded AR rollout from hour 0
        seq = st[:, :1]
        for k in range(ar_steps):
            nxt = model.forward(seq, ac[:, :k + 1], dts[:, :k + 1])[:, -1:]
            seq = torch.cat([seq, nxt], 1)
        ar_pred, ar_tgt, ar_m = seq[:, 1:], Ztgt_t[idx][:, 1:ar_steps + 1], mask_t[idx][:, 1:ar_steps + 1]
        return (masked_mse(tf_pred, tf_tgt, tf_m), masked_mse(ar_pred, ar_tgt, ar_m))

    def eval_gate():
        model.eval()
        with torch.no_grad():
            st = Zin_t[vai]; ac = Ain_t[vai]; dts = dt.expand(len(vai), S)
            seq = st[:, :1]
            for k in range(AR_EVAL):
                nxt = model.forward(seq, ac[:, :k + 1], dts[:, :k + 1])[:, -1:]
                seq = torch.cat([seq, nxt], 1)
            pred = seq[:, 1:]; tgt = Ztgt_t[vai][:, 1:AR_EVAL + 1]; m = mask_t[vai][:, 1:AR_EVAL + 1]
            ar = masked_mse(pred, tgt, m).item()
            per = masked_mse(st[:, :1].expand(-1, AR_EVAL, -1), tgt, m).item()   # carry hour 0
            dmean = ((Ztgt_t[tri][:, 1:] - Zin_t[tri][:, :-1]) * mask_t[tri][:, 1:]).sum((0, 1)) / \
                    mask_t[tri][:, 1:].sum((0, 1)).clamp(min=1)
            steps = torch.arange(1, AR_EVAL + 1).float()[None, :, None]
            mean_pred = st[:, :1] + steps * dmean[None, None, :]
            mdb = masked_mse(mean_pred, tgt, m).item()
        return ar, per, mdb

    bs = 32; t0 = time.time(); best = {"ar": 1e9, "state": None}
    EPOCHS = 20
    for ep in range(EPOCHS):
        model.train(); pp = tri[torch.randperm(len(tri))]
        tot = 0.0; nb = 0
        for i in range(0, len(pp), bs):
            b = pp[i:i + bs]
            l_tf, l_ar = tf_and_ar(b, AR_TRAIN)
            loss = l_tf + l_ar
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0); opt.step()
            tot += float(loss); nb += 1
        if (ep + 1) % 3 == 0 or ep == 0:
            ar, per, mdb = eval_gate()
            if ar < best["ar"]:
                best = {"ar": ar, "state": {k: v.detach().clone() for k, v in model.state_dict().items()}, "ep": ep + 1}
            print(f"  ep {ep+1:2d}/{EPOCHS} loss {tot/nb:.4f} | val {AR_EVAL}h-rollout MSE {ar:.4f} "
                  f"(persist {per:.4f}, mean-Δ {mdb:.4f}) [{time.time()-t0:.0f}s]")
    model.load_state_dict(best["state"])
    ar, per, mdb = eval_gate()
    beats = ar < per and ar < mdb
    CKPT.parent.mkdir(exist_ok=True)
    torch.save({"model": model.state_dict(), "state_mu": mu, "state_sd": sd,
                "act_mu": amu, "act_sd": asd, "meta": meta,
                "metrics": {"val_rollout_mse": ar, "persistence": per, "mean_delta": mdb,
                            "beats_baselines": bool(beats), "best_epoch": best["ep"]}}, CKPT)
    print(f"\n[hwm] best {AR_EVAL}h-rollout MSE {ar:.4f} @ep{best['ep']} vs persist {per:.4f} / mean-Δ {mdb:.4f}")
    print(f"[hwm] EXIT GATE (rollout beats persistence AND mean-Δ): {'PASS' if beats else 'FAIL'}  -> {CKPT.name}")


if __name__ == "__main__":
    main()
