#!/usr/bin/env python3
"""
Approach #3: DAG guides the latent representation.

Take the JEPA-hybrid world model and inject the two DAG-derived causal corrections
from approach #2, so the latent encodes the treatment EFFECT rather than the
treatment ASSIGNMENT (confounding):

  - IPW: weight each patient's loss by inverse propensity P(T|C) from the DAG's
         confounder set -> re-balances the confounded cohort during training.
  - CRN: a gradient-reversed 'arm' head on the encoder state -> scrubs treatment-
         assignment information out of the latent.

Success test: the world model's counterfactual CREATININE effect (dialysis-diuretic)
should flip from the confounded POSITIVE to the causal NEGATIVE (IPW baseline -0.37).
"""
import argparse, os
import numpy as np
import torch, torch.nn as nn
import wm_data as D
from wm_model import JepaAC
import train_wm as T
from sklearn.linear_model import LogisticRegression

HERE = os.path.dirname(os.path.abspath(__file__))
NLAB = len(D.TARGET_LABS)
IPW_BASELINE = {"Creatinine": -0.37, "BUN (Urea Nitrogen)": -20.55, "Potassium": 0.14, "Bicarbonate": -2.80}


class _GRL(torch.autograd.Function):
    @staticmethod
    def forward(ctx, x, lam): ctx.lam = lam; return x.view_as(x)
    @staticmethod
    def backward(ctx, g): return -ctx.lam * g, None
def grad_reverse(x, lam): return _GRL.apply(x, lam)


def conf(e, scaler):
    z = []
    for j, l in enumerate(D.TARGET_LABS):
        m, s = scaler["lab"][l]; v = e["bval"][j]
        z.append(((v - m) / s) if v is not None else 0.0)
    return np.array(z + list(D.static_vec(e, scaler)), np.float32)


def collate_w(batch, channels, ci, scaler, device, wmap):
    grid, active, static, action, ptgt, pmask = T.collate(batch, channels, ci, scaler, device)
    arm = torch.tensor([1 if e["cohort"] == "dialysis" else 0 for e in batch]).to(device)
    w = torch.tensor([wmap[e["hadm"]] for e in batch], dtype=torch.float).to(device)
    return grid, active, static, action, ptgt, pmask, arm, w


@torch.no_grad()
def effect_recovery(model, data, channels, ci, scaler, device, train):
    a_d, a_u = T.canon_actions(train, device)
    sums = np.zeros(NLAB); n = 0
    model.eval()
    for b in T.batches(data, 64, False):
        grid, active, static, action, ptgt, pmask = T.collate(b, channels, ci, scaler, device)
        B = grid.shape[0]
        pd = model(grid, active, static, a_d.unsqueeze(0).repeat(B, 1)).cpu().numpy()
        pu = model(grid, active, static, a_u.unsqueeze(0).repeat(B, 1)).cpu().numpy()
        for j, l in enumerate(D.TARGET_LABS):
            m, s = scaler["lab"][l]
            sums[j] += (((pd[:, :, j] - pu[:, :, j]) * s).mean(1)).sum()
        n += B
    return sums / n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=45)
    ap.add_argument("--bs", type=int, default=64)
    ap.add_argument("--d", type=int, default=128)
    ap.add_argument("--d-lat", type=int, default=192)
    ap.add_argument("--lam-crn", type=float, default=0.5)
    ap.add_argument("--lam-jepa", type=float, default=1.0)
    ap.add_argument("--lam-rec", type=float, default=1.0)
    ap.add_argument("--lambda-contrast", type=float, default=0.5)
    ap.add_argument("--margin", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=20260714)
    ap.add_argument("--out", default=os.path.join(HERE, "wm_causal.pt"))
    args = ap.parse_args()
    torch.manual_seed(args.seed); dev = "cpu"

    train, val, test, channels, ci, scaler, meta = D.build(seed=args.seed)

    # ---- IPW weights from the DAG confounder set (propensity fit on TRAIN only) ----
    Ctr = np.stack([conf(e, scaler) for e in train]); Ttr = np.array([e["cohort"] == "dialysis" for e in train]).astype(int)
    ps_model = LogisticRegression(max_iter=1000).fit(Ctr, Ttr)
    pT = Ttr.mean()
    wmap = {}
    for e in train + val + test:
        p = float(ps_model.predict_proba(conf(e, scaler)[None])[0, 1]).clip(1e-3, 1 - 1e-3) if False else \
            float(np.clip(ps_model.predict_proba(conf(e, scaler)[None])[0, 1], 1e-3, 1 - 1e-3))
        d = e["cohort"] == "dialysis"
        wmap[e["hadm"]] = float(np.clip((pT / p) if d else ((1 - pT) / (1 - p)), 0.1, 10.0))
    print(f"IPW: propensity fit (n_train={len(train)}); mean w = {np.mean(list(wmap.values())):.2f}")

    model = JepaAC(meta["C"], meta["n_static"], n_labs=NLAB, action_dim=meta["action_dim"],
                   d=args.d, d_lat=args.d_lat, dropout=0.2, H=meta["H"], post_h=D.POST_H).to(dev)
    arm_head = nn.Sequential(nn.Linear(args.d, args.d // 2), nn.GELU(), nn.Linear(args.d // 2, 2)).to(dev)
    opt = torch.optim.AdamW(list(model.parameters()) + list(arm_head.parameters()), lr=1e-3, weight_decay=1e-4)
    ce = nn.CrossEntropyLoss()
    cd, cu = T.canon_actions(train, dev)
    print(f"params: {sum(p.numel() for p in model.parameters())/1e6:.2f}M + CRN head")

    def wmean(x, m, w):  # weighted masked mean; x,m [...], w broadcast [B,1,1]
        return (x * m * w).sum() / (m * w).sum().clamp(min=1)

    best = float("inf"); best_state = None; bad = 0
    for ep in range(1, args.epochs + 1):
        model.train(); grl = args.lam_crn * min(1.0, ep / 8.0)
        tot = tcrn = nb = 0.0
        for b in T.batches(train, args.bs, True, seed=args.seed + ep):
            grid, active, static, action, ptgt, pmask, arm, w = collate_w(b, channels, ci, scaler, dev, wmap)
            B = grid.shape[0]; w3 = w[:, None, None]
            pred_lat = model.rollout_latents(grid, active, static, action)
            pred = model.obs_dec(pred_lat)
            y = model.obs_target(ptgt, pmask); _, rec = model.obs_online(ptgt, pmask)
            hour = (pmask.sum(-1, keepdim=True) > 0).float()
            mse = wmean((pred - ptgt) ** 2, pmask, w3)
            jepa = wmean(torch.abs(pred_lat - y).mean(-1, keepdim=True), hour, w[:, None, None])
            recl = wmean((rec - ptgt) ** 2, pmask, w3)
            # contrast (weighted)
            is_d = (action[:, :1] > 0.5)
            a_cf = torch.where(is_d, cu.expand(B, -1), cd.expand(B, -1)).contiguous()
            pcf = model(grid, active, static, a_cf)
            per = pmask.sum((1, 2)).clamp(min=1)
            d_f = ((pred - ptgt) ** 2 * pmask).sum((1, 2)) / per
            d_c = ((pcf - ptgt) ** 2 * pmask).sum((1, 2)) / per
            contrast = (torch.relu(args.margin - (d_c - d_f)) * w).sum() / w.sum()
            # CRN: scrub arm from the encoder state
            z = model.context(grid, active, static)
            crn = ce(arm_head(grad_reverse(z, grl)), arm)
            loss = mse + args.lam_jepa * jepa + args.lam_rec * recl + args.lambda_contrast * contrast + grl * crn
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(list(model.parameters()) + list(arm_head.parameters()), 1.0)
            opt.step(); model.ema_update()
            tot += mse.item(); tcrn += crn.item(); nb += 1
        # val (unweighted mse for early stop)
        model.eval(); s = nn_ = 0.0
        with torch.no_grad():
            for b in T.batches(val, 128, False):
                grid, active, static, action, ptgt, pmask = T.collate(b, channels, ci, scaler, dev)
                pr = model(grid, active, static, action)
                s += (((pr - ptgt) ** 2) * pmask).sum().item(); nn_ += pmask.sum().item()
        vm = s / max(nn_, 1)
        if vm < best - 1e-4: best = vm; bad = 0; best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        else: bad += 1
        if ep % 3 == 0 or ep == 1:
            print(f"ep {ep:3d} | mse {tot/nb:.3f} crn {tcrn/nb:.3f} | val {vm:.3f} (best {best:.3f}, pat {bad}/10)", flush=True)
        if bad >= 10: print(f"early stop {ep}"); break
    if best_state: model.load_state_dict(best_state)

    m = T.evaluate(model, test, channels, ci, scaler, dev)
    d = T.discriminate(model, test, channels, ci, scaler, dev, train)
    eff = effect_recovery(model, test, channels, ci, scaler, dev, train)
    print("\n===== CAUSAL WM (IPW + CRN) -- TEST =====")
    for lab, s in m["per_lab"].items():
        print(f"  {lab:20s}  R2 {s['r2']:+.3f}  MAE {s['mae']:.3f}")
    print(f"  discrimination: {d['disc_acc']:.3f} (majority {d['majority_baseline']:.3f})")
    print("\n  EFFECT RECOVERY (dialysis - diuretic):")
    print(f"  {'lab':20s} {'WM effect':>10} {'IPW baseline':>13} {'sign OK?':>9}")
    for j, lab in enumerate(D.TARGET_LABS):
        base = IPW_BASELINE[lab]; ok = "yes" if np.sign(eff[j]) == np.sign(base) else "NO"
        print(f"  {lab:20s} {eff[j]:+10.2f} {base:+13.2f} {ok:>9}")
    torch.save({"model": model.state_dict(), "meta": meta, "args": vars(args)}, args.out)
    print(f"\ncheckpoint -> {args.out}")


if __name__ == "__main__":
    main()
