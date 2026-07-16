#!/usr/bin/env python3
"""
Train the V6 hourly encoder + autoregressive rollout world model.

Target is now the HOUR-BY-HOUR post-anchor trajectory (POST_H hours x 4 labs), not a
single aggregated post value -- so the model learns a transition it can unroll for
multi-step counterfactual rollout.

Objective : masked-MSE over the hours actually measured (labs are sparse -> most masked)
            + counterfactual contrast (opposite-family action must fit the trajectory worse)
Eval       : per-lab MAE/R^2 over observed post-hours; error by horizon bucket;
             counterfactual discrimination (roll out under both actions, pick closer).

  python train_wm.py --epochs 60 --d 128 --device cpu
"""
import argparse, json, os
import torch, torch.nn as nn
import wm_data as D
from wm_model import WorldModel, LatentWorldModel, JepaAC

HERE = os.path.dirname(os.path.abspath(__file__))
NLAB = len(D.TARGET_LABS)


def collate(batch, channels, ci, scaler, device):
    B = len(batch)
    grid = torch.zeros(B, D.H, len(channels), D.FEAT)
    active = torch.zeros(B, D.H, len(channels))
    ptgt = torch.zeros(B, D.POST_H, NLAB); pmask = torch.zeros(B, D.POST_H, NLAB)
    for i, e in enumerate(batch):
        g, a = D.featurize(e, channels, ci, scaler)
        grid[i] = torch.tensor(g); active[i] = torch.tensor(a)
        v, m = D.post_grid(e, scaler)
        ptgt[i] = torch.tensor(v); pmask[i] = torch.tensor(m)
    static = torch.tensor([D.static_vec(e, scaler) for e in batch], dtype=torch.float)
    action = torch.tensor([e["action"] for e in batch], dtype=torch.float)
    return (grid.to(device), active.to(device), static.to(device), action.to(device),
            ptgt.to(device), pmask.to(device))


def batches(data, bs, shuffle, seed=0):
    idx = list(range(len(data)))
    if shuffle:
        import random; random.Random(seed).shuffle(idx)
    for i in range(0, len(idx), bs):
        yield [data[j] for j in idx[i:i + bs]]


def canon_actions(train, device):
    import statistics as st
    dur = st.median([e["action"][2] for e in train if e["cohort"] == "dialysis"] or [1.0])
    ratio = st.median([e["action"][3] for e in train if e["cohort"] == "diuretic"] or [0.5])
    return (torch.tensor([1.0, 0.0, dur, 0.0], device=device),
            torch.tensor([0.0, 1.0, 0.0, ratio], device=device))


@torch.no_grad()
def evaluate(model, data, channels, ci, scaler, device, bs=64):
    model.eval()
    ys = [[] for _ in range(NLAB)]; yh = [[] for _ in range(NLAB)]
    bucket = {"0-24h": [], "24-48h": [], "48-72h": []}
    for batch in batches(data, bs, False):
        grid, active, static, action, ptgt, pmask = collate(batch, channels, ci, scaler, device)
        pred = model(grid, active, static, action).cpu()
        ptgt = ptgt.cpu(); pmask = pmask.cpu()
        for i in range(len(batch)):
            for j, lab in enumerate(D.TARGET_LABS):
                m, sd = scaler["lab"][lab]
                for t in range(D.POST_H):
                    if pmask[i, t, j] > 0:
                        yv = ptgt[i, t, j].item() * sd + m; pv = pred[i, t, j].item() * sd + m
                        ys[j].append(yv); yh[j].append(pv)
                        b = "0-24h" if t < 24 else "24-48h" if t < 48 else "48-72h"
                        bucket[b].append(abs(pred[i, t, j].item() - ptgt[i, t, j].item()))  # standardized
    per_lab = {}
    for j, lab in enumerate(D.TARGET_LABS):
        if not ys[j]:
            continue
        yb = sum(ys[j]) / len(ys[j])
        ss_tot = sum((y - yb) ** 2 for y in ys[j]) or 1.0
        ss_res = sum((y - p) ** 2 for y, p in zip(ys[j], yh[j]))
        mae = sum(abs(y - p) for y, p in zip(ys[j], yh[j])) / len(ys[j])
        per_lab[lab] = dict(mae=round(mae, 3), r2=round(1 - ss_res / ss_tot, 3), n=len(ys[j]))
    horizon = {b: round(sum(x) / len(x), 3) for b, x in bucket.items() if x}
    return dict(per_lab=per_lab, horizon_std_mae=horizon)


@torch.no_grad()
def discriminate(model, data, channels, ci, scaler, device, train, bs=64):
    a_dial, a_diur = canon_actions(train, device)
    model.eval(); n = correct = n_dial = 0
    for batch in batches(data, bs, False):
        grid, active, static, _, ptgt, pmask = collate(batch, channels, ci, scaler, device)
        B = grid.shape[0]
        pd = model(grid, active, static, a_dial.unsqueeze(0).repeat(B, 1))
        pu = model(grid, active, static, a_diur.unsqueeze(0).repeat(B, 1))
        dd = (((pd - ptgt) ** 2) * pmask).sum((1, 2))
        du = (((pu - ptgt) ** 2) * pmask).sum((1, 2))
        pick_dial = (dd <= du).cpu()
        for i, e in enumerate(batch):
            true_dial = (e["cohort"] == "dialysis")
            correct += (bool(pick_dial[i].item()) == true_dial); n += 1; n_dial += true_dial
    base = max(n_dial, n - n_dial) / n if n else 0.0
    return dict(disc_acc=round(correct / n, 4) if n else 0.0,
                majority_baseline=round(base, 4), n=n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--bs", type=int, default=64)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--d", type=int, default=128)
    ap.add_argument("--dropout", type=float, default=0.2)
    ap.add_argument("--patience", type=int, default=8)
    ap.add_argument("--lambda-contrast", type=float, default=0.5)
    ap.add_argument("--margin", type=float, default=0.2)
    ap.add_argument("--arch", default="obs", choices=["obs", "latent", "jepa"])
    ap.add_argument("--d-lat", type=int, default=192)
    ap.add_argument("--lam-jepa", type=float, default=1.0, help="JEPA latent-regression weight")
    ap.add_argument("--lam-rec", type=float, default=1.0, help="JEPA obs-autoencoder weight")
    ap.add_argument("--device", default="auto", choices=["auto", "cpu", "mps"])
    ap.add_argument("--seed", type=int, default=20260714)
    ap.add_argument("--out", default=os.path.join(HERE, "wm_checkpoint.pt"))
    args = ap.parse_args()
    torch.manual_seed(args.seed)
    device = ("mps" if torch.backends.mps.is_available() else "cpu") if args.device == "auto" else args.device

    train, val, test, channels, ci, scaler, meta = D.build(seed=args.seed)
    st = {e["subject"] for e in train} | {e["subject"] for e in val}
    assert not (st & {e["subject"] for e in test}), "LEAK: benchmark subjects in train/val!"
    print(f"device={device}  post_h={D.POST_H}  {meta}")
    print(f"leakage OK | train {len(train)} / val {len(val)} / test {len(test)}")

    if args.arch == "latent":
        model = LatentWorldModel(meta["C"], meta["n_static"], n_labs=NLAB, action_dim=meta["action_dim"],
                                 d=args.d, d_lat=args.d_lat, dropout=args.dropout, H=meta["H"], post_h=D.POST_H).to(device)
    elif args.arch == "jepa":
        model = JepaAC(meta["C"], meta["n_static"], n_labs=NLAB, action_dim=meta["action_dim"],
                       d=args.d, d_lat=args.d_lat, dropout=args.dropout, H=meta["H"], post_h=D.POST_H).to(device)
    else:
        model = WorldModel(meta["C"], meta["n_static"], n_labs=NLAB, action_dim=meta["action_dim"],
                           d=args.d, dropout=args.dropout, H=meta["H"], post_h=D.POST_H).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    print(f"model params: {sum(p.numel() for p in model.parameters())/1e6:.2f}M")
    canon_dial, canon_diur = canon_actions(train, device)

    @torch.no_grad()
    def val_mse():
        model.eval(); s = n = 0.0
        for batch in batches(val, 64, False):
            grid, active, static, action, ptgt, pmask = collate(batch, channels, ci, scaler, device)
            pred = model(grid, active, static, action)
            s += ((((pred - ptgt) ** 2) * pmask).sum()).item(); n += pmask.sum().item()
        return s / max(n, 1)

    best = float("inf"); best_state = None; bad = 0
    for ep in range(1, args.epochs + 1):
        model.train(); tot = tc = nb = 0.0
        for batch in batches(train, args.bs, True, seed=args.seed + ep):
            grid, active, static, action, ptgt, pmask = collate(batch, channels, ci, scaler, device)
            B = grid.shape[0]
            per = pmask.sum((1, 2)).clamp(min=1)
            is_dial = (action[:, :1] > 0.5)
            a_cf = torch.where(is_dial, canon_diur.expand(B, -1), canon_dial.expand(B, -1)).contiguous()
            if args.arch == "jepa":
                pred_lat = model.rollout_latents(grid, active, static, action)          # [B,T,d_lat]
                pred = model.obs_dec(pred_lat)                                           # decoded labs
                y = model.obs_target(ptgt, pmask)                                        # EMA target latent (stop-grad)
                _, rec = model.obs_online(ptgt, pmask)                                   # obs autoencoder
                hour = (pmask.sum(-1, keepdim=True) > 0).float()                         # [B,T,1] hour observed
                mse = (((pred - ptgt) ** 2) * pmask).sum() / pmask.sum().clamp(min=1)    # decode readout
                jepa = (torch.abs(pred_lat - y).mean(-1, keepdim=True) * hour).sum() / hour.sum().clamp(min=1)
                rec_l = (((rec - ptgt) ** 2) * pmask).sum() / pmask.sum().clamp(min=1)
                pred_cf = model(grid, active, static, a_cf)
                d_f = (((pred - ptgt) ** 2) * pmask).sum((1, 2)) / per
                d_c = (((pred_cf - ptgt) ** 2) * pmask).sum((1, 2)) / per
                contrast = torch.relu(args.margin - (d_c - d_f)).mean()
                loss = mse + args.lam_jepa * jepa + args.lam_rec * rec_l + args.lambda_contrast * contrast
            else:
                pred = model(grid, active, static, action)
                mse = (((pred - ptgt) ** 2) * pmask).sum() / pmask.sum().clamp(min=1)
                pred_cf = model(grid, active, static, a_cf)
                d_f = (((pred - ptgt) ** 2) * pmask).sum((1, 2)) / per
                d_c = (((pred_cf - ptgt) ** 2) * pmask).sum((1, 2)) / per
                contrast = torch.relu(args.margin - (d_c - d_f)).mean()
                loss = mse + args.lambda_contrast * contrast
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0); opt.step()
            if args.arch == "jepa":
                model.ema_update()
            tot += mse.item(); tc += contrast.item(); nb += 1
        vm = val_mse()
        if vm < best - 1e-4:
            best = vm; bad = 0
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        else:
            bad += 1
        if ep % 2 == 0 or ep == 1:
            print(f"ep {ep:3d} | train_mse {tot/nb:.3f} contrast {tc/nb:.3f} | val_mse {vm:.3f} "
                  f"(best {best:.3f}, patience {bad}/{args.patience})", flush=True)
        if bad >= args.patience:
            print(f"early stop at epoch {ep}"); break

    if best_state is not None:
        model.load_state_dict(best_state)
    torch.save({"model": model.state_dict(), "channels": channels, "scaler": scaler,
                "meta": meta, "args": vars(args), "post_h": D.POST_H}, args.out)

    for name, split in [("VAL", val), ("TEST", test)]:
        m = evaluate(model, split, channels, ci, scaler, device)
        d = discriminate(model, split, channels, ci, scaler, device, train)
        print(f"\n===== {name} (held-out) =====")
        for lab, s in m["per_lab"].items():
            print(f"  {lab:20s}  MAE {s['mae']:8.3f}  R2 {s['r2']:+.3f}  (n={s['n']})")
        print(f"  horizon std-MAE: {m['horizon_std_mae']}")
        print(f"  counterfactual discrimination: {d['disc_acc']:.3f} (majority {d['majority_baseline']:.3f}, n={d['n']})")
    print(f"\ncheckpoint -> {args.out}")


if __name__ == "__main__":
    main()
