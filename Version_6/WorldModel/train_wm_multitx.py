#!/usr/bin/env python3
"""
Multi-treatment world model (#3 across the full 6-treatment action space).

Uses multitx_cohort.jsonl (ICU-admission anchored):
  state  = 4 target labs over [0,48h] (hourly grid) + baseline confounders (static)
  action = 6-hot treatment vector (which treatments active in first 48h)
  target = 4-lab trajectory over [48,120h] (72 hourly steps)
Reuses the JEPA-hybrid architecture, with C=4 lab channels and a 6-dim action.

First working version: demonstrates the WM conditioning on the multi-hot action and
rolling a trajectory forward. Caveat: pre-window overlaps early treatment (timing not
fully separated) -> associative-leaning; a clean version needs treatment-time gating.
"""
import argparse, json, math, os, random
import numpy as np
import torch
import wm_model
from wm_model import JepaAC

HERE = os.path.dirname(os.path.abspath(__file__))
LABS = ["Creatinine", "BUN (Urea Nitrogen)", "Potassium", "Bicarbonate"]
COMORB = ["aki", "ckd_nonesrd", "diabetes", "sepsis", "hypertension", "cardiogenic_shock", "atrial_fib", "cad", "copd", "liver_disease"]
TREATMENTS = ["diuretic", "vasodilator", "inotrope", "vasopressor", "dialysis", "ventilation"]
PRE_H, POST_H, NLAB, FEAT = 48, 72, 4, 4


def load():
    recs = [json.loads(l) for l in open(os.path.join(HERE, "multitx_cohort.jsonl"))]
    recs = [r for r in recs if any(r["lab_traj"].get(l) for l in LABS)]
    return recs


def scalers(train):
    sc = {}
    for j, lab in enumerate(LABS):
        vals = [v for r in train for (h, v, *_) in r["lab_traj"].get(lab, [])]
        m = np.mean(vals) if vals else 0.0; s = np.std(vals) + 1e-6 if vals else 1.0
        sc[lab] = (m, s)
    ages = [r["age"] for r in train if r["age"]]
    sc["age"] = (np.mean(ages), np.std(ages) + 1e-6)
    return sc


def static_vec(r, sc):
    c = [1.0 if r["comorbidities"].get(k) else 0.0 for k in COMORB]
    c.append(((r["age"] or 65) - sc["age"][0]) / sc["age"][1]); c.append(1.0 if r["sex"] == "M" else 0.0)
    for lab in LABS:
        v = r["baseline_labs"].get(lab); m, s = sc[lab]
        c.append((v - m) / s if v is not None else 0.0)
    return c


def grids(r, sc):
    pre = np.zeros((PRE_H, NLAB, FEAT), np.float32); act = np.zeros((PRE_H, NLAB), np.float32)
    post = np.zeros((POST_H, NLAB), np.float32); pmask = np.zeros((POST_H, NLAB), np.float32)
    for j, lab in enumerate(LABS):
        m, s = sc[lab]
        for (h, v, lo, hi) in sorted(r["lab_traj"].get(lab, [])):
            z = (v - m) / s
            rp = max(-3, min(3, (v - lo) / (hi - lo))) if (lo is not None and hi is not None and hi > lo) else 0.0
            if 0 <= h < PRE_H:
                t = int(h); pre[t, j] = [z, rp, 1.0, 0.0]; act[t, j] = 1.0
            elif PRE_H <= h < PRE_H + POST_H:
                t = int(h) - PRE_H; post[t, j] = z; pmask[t, j] = 1.0
    action = np.array([r["treatments"][t] for t in TREATMENTS], np.float32)
    return pre, act, post, pmask, np.array(static_vec(r, sc), np.float32), action


def batches(data, bs, shuffle, seed=0):
    idx = list(range(len(data)))
    if shuffle: random.Random(seed).shuffle(idx)
    for i in range(0, len(idx), bs): yield [data[j] for j in idx[i:i + bs]]


def collate(batch, sc, dev):
    P, A, Q, M, S, AC = zip(*[grids(r, sc) for r in batch])
    return (torch.tensor(np.stack(P)).to(dev), torch.tensor(np.stack(A)).to(dev),
            torch.tensor(np.stack(S)).to(dev), torch.tensor(np.stack(AC)).to(dev),
            torch.tensor(np.stack(Q)).to(dev), torch.tensor(np.stack(M)).to(dev))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--epochs", type=int, default=40); ap.add_argument("--d", type=int, default=128)
    ap.add_argument("--seed", type=int, default=20260714); args = ap.parse_args()
    torch.manual_seed(args.seed); dev = "cpu"
    recs = load()
    # subject-level split
    subs = sorted({r["subject_id"] for r in recs}); random.Random(args.seed).shuffle(subs)
    nte = int(len(subs) * 0.2); nva = int(len(subs) * 0.15)
    te_s, va_s = set(subs[:nte]), set(subs[nte:nte + nva])
    train = [r for r in recs if r["subject_id"] not in te_s and r["subject_id"] not in va_s]
    val = [r for r in recs if r["subject_id"] in va_s]; test = [r for r in recs if r["subject_id"] in te_s]
    sc = scalers(train)
    print(f"multi-tx WM | train {len(train)} val {len(val)} test {len(test)} | C={NLAB} action_dim=6")

    model = JepaAC(NLAB, len(COMORB) + 2 + NLAB, n_labs=NLAB, action_dim=6, d=args.d, d_lat=192,
                   dropout=0.2, H=PRE_H, post_h=POST_H).to(dev)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    print(f"params: {sum(p.numel() for p in model.parameters())/1e6:.2f}M")

    def vloss():
        model.eval(); s = n = 0.0
        with torch.no_grad():
            for b in batches(val, 128, False):
                pre, a, st, ac, q, m = collate(b, sc, dev)
                pr = model(pre, a, st, ac); s += (((pr - q) ** 2) * m).sum().item(); n += m.sum().item()
        return s / max(n, 1)

    best = 1e9; bad = 0; best_state = None
    for ep in range(1, args.epochs + 1):
        model.train(); tot = nb = 0.0
        for b in batches(train, 64, True, seed=args.seed + ep):
            pre, a, st, ac, q, m = collate(b, sc, dev)
            pl = model.rollout_latents(pre, a, st, ac); pred = model.obs_dec(pl)
            y = model.obs_target(q, m); _, rec = model.obs_online(q, m)
            hour = (m.sum(-1, keepdim=True) > 0).float()
            mse = (((pred - q) ** 2) * m).sum() / m.sum().clamp(min=1)
            jepa = (torch.abs(pl - y).mean(-1, keepdim=True) * hour).sum() / hour.sum().clamp(min=1)
            recl = (((rec - q) ** 2) * m).sum() / m.sum().clamp(min=1)
            loss = mse + jepa + recl
            opt.zero_grad(); loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0); opt.step(); model.ema_update()
            tot += mse.item(); nb += 1
        vl = vloss()
        if vl < best - 1e-4: best = vl; bad = 0; best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        else: bad += 1
        if ep % 4 == 0 or ep == 1: print(f"ep {ep:3d} | mse {tot/nb:.3f} | val {vl:.3f} (best {best:.3f}, pat {bad}/8)", flush=True)
        if bad >= 8: print(f"early stop {ep}"); break
    if best_state: model.load_state_dict(best_state)

    # eval R2 per lab over post trajectory
    model.eval(); ys = [[] for _ in LABS]; yh = [[] for _ in LABS]
    with torch.no_grad():
        for b in batches(test, 128, False):
            pre, a, st, ac, q, m = collate(b, sc, dev); pr = model(pre, a, st, ac).cpu().numpy(); q = q.cpu().numpy(); m = m.cpu().numpy()
            for i in range(len(b)):
                for j, lab in enumerate(LABS):
                    mm, s = sc[lab]
                    for t in range(POST_H):
                        if m[i, t, j] > 0: ys[j].append(q[i, t, j] * s + mm); yh[j].append(pr[i, t, j] * s + mm)
    print("\n===== MULTI-TREATMENT WM (test, R2 over 48-120h trajectory) =====")
    for j, lab in enumerate(LABS):
        if not ys[j]: continue
        yb = np.mean(ys[j]); sst = np.sum((np.array(ys[j]) - yb) ** 2) or 1
        r2 = 1 - np.sum((np.array(ys[j]) - np.array(yh[j])) ** 2) / sst
        print(f"  {lab:20s} R2 {r2:+.3f}  (n={len(ys[j])})")
    torch.save({"model": model.state_dict(), "scaler": sc}, os.path.join(HERE, "wm_multitx.pt"))
    print("checkpoint -> wm_multitx.pt")


if __name__ == "__main__":
    main()
