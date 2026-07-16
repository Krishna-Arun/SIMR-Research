#!/usr/bin/env python3
"""
CANONICAL pure JEPA-AC (no decoder, no lab-number loss).

Trains ONLY by predicting an EMA target encoder's representation of the future:
  - shared per-hour encoder E: (4 labs + mask) -> representation
  - context: GRU over the pre-anchor hours' E-reps + static  -> context latent
  - action-conditioned predictor rolls the latent forward POST_H hours, predicting
    the representation of each future hour
  - target: E_ema (EMA of E, stop-grad) applied to the real future obs
  - loss: latent regression (invariance) + VICReg variance/covariance (anti-collapse)
  - NO decoder, NO reconstruction, NO lab MSE.

Evaluation (JEPA-standard): freeze the model, fit a LINEAR PROBE rep->labs on train,
report R^2 on test; discrimination is done in latent space (roll under both actions,
compare predicted reps to the EMA-target reps of the observed future, pick closer).

Caveat: to keep the target encoder an EMA of the shared encoder, the context here is
the 4 target-lab pre-trajectory + static -- thinner than the 29-channel grid the other
models use. That is an inherent cost of pure JEPA on this data.
"""
import argparse, copy, math, os
import numpy as np
import torch, torch.nn as nn
import wm_data as D

HERE = os.path.dirname(os.path.abspath(__file__))
NLAB = len(D.TARGET_LABS)


def lab_grid(series_by_lab, hours, scaler, sign):
    """Build [hours, NLAB] standardized values + [hours, NLAB] mask from per-lab
    (h, v) series. sign=+1 for post (h>0), -1 for pre (h<0, bucket by |h|)."""
    vals = np.zeros((hours, NLAB), np.float32); mask = np.zeros((hours, NLAB), np.float32)
    for j, lab in enumerate(D.TARGET_LABS):
        m, sd = scaler["lab"][lab]
        pts = []
        for tup in series_by_lab.get(lab, []):
            h = tup[0]; v = tup[1]
            if h is None or v is None:
                continue
            hh = h if sign > 0 else -h                       # hours from anchor, positive
            if hh <= 0:
                continue
            t = hours - int(math.ceil(hh)) if sign < 0 else int(hh)   # pre: recent=last row; post: 0..
            if 0 <= t < hours:
                pts.append((t, (v - m) / sd))
        for t, zv in sorted(pts):
            vals[t, j] = zv; mask[t, j] = 1.0
    return vals, mask


def build(e, scaler):
    # pre 4-lab grid [48, NLAB] (LOCF-free: just observed points, model's GRU handles gaps)
    pre_v, pre_m = lab_grid({l: [(hh, vv) for (hh, vv, _, _) in e["labs"].get(l, [])] for l in D.TARGET_LABS},
                            D.H, scaler, sign=-1)
    post_v, post_m = lab_grid(e["post"], D.POST_H, scaler, sign=+1)
    static = np.array(D.static_vec(e, scaler), np.float32)
    action = np.array(e["action"], np.float32)
    return pre_v, pre_m, post_v, post_m, static, action


class PureJepaAC(nn.Module):
    def __init__(self, n_static=12, action_dim=4, d=128, H=48, post_h=72, ema_m=0.99):
        super().__init__()
        self.E = nn.Sequential(nn.Linear(NLAB * 2, d), nn.GELU(), nn.Linear(d, d))   # shared hour encoder
        self.ctx = nn.GRU(d, d, batch_first=True)
        self.static_mlp = nn.Sequential(nn.Linear(n_static, d), nn.GELU())
        self.film = nn.Linear(action_dim, 2 * d); nn.init.zeros_(self.film.weight); nn.init.zeros_(self.film.bias)
        self.act_emb = nn.Linear(action_dim, d)
        self.cell = nn.GRUCell(d, d)
        self.dyn = nn.Sequential(nn.Linear(d, d), nn.LayerNorm(d), nn.GELU(), nn.Linear(d, d))
        self.norm = nn.LayerNorm(d)
        self.pred_head = nn.Linear(d, d)
        self.E_ema = copy.deepcopy(self.E)
        for p in self.E_ema.parameters():
            p.requires_grad_(False)
        self.d, self.post_h, self.ema_m = d, post_h, ema_m

    def context(self, pre_v, pre_m, static):
        reps = self.E(torch.cat([pre_v, pre_m], -1))          # [B,H,d]
        out, _ = self.ctx(reps)
        return self.norm(out[:, -1] + self.static_mlp(static))

    def rollout(self, c, action):
        g, b = self.film(action).chunk(2, -1); s = (1 + g) * c + b
        a = self.act_emb(action); out = []
        for _ in range(self.post_h):
            s = self.cell(a, s); s = self.norm(s + self.dyn(s)); out.append(self.pred_head(s))
        return torch.stack(out, 1)                             # [B,post_h,d] predicted reps

    def forward(self, pre_v, pre_m, static, action):
        return self.rollout(self.context(pre_v, pre_m, static), action)

    def target(self, post_v, post_m):
        with torch.no_grad():
            return self.E_ema(torch.cat([post_v, post_m], -1)) # [B,post_h,d] target reps

    @torch.no_grad()
    def ema_update(self):
        for tp, p in zip(self.E_ema.parameters(), self.E.parameters()):
            tp.mul_(self.ema_m).add_(p, alpha=1 - self.ema_m)


def vicreg(z):                                                 # z [N,d]
    z = z - z.mean(0)
    std = torch.sqrt(z.var(0) + 1e-4)
    var = torch.relu(1.0 - std).mean()
    N, d = z.shape
    cov = (z.T @ z) / (N - 1)
    cov_off = (cov - torch.diag(torch.diag(cov)))
    return var, (cov_off ** 2).sum() / d


def to_dev(arrs, dev):
    return [torch.tensor(np.stack(a)).to(dev) for a in arrs]


def batches(data, bs, shuffle, seed=0):
    idx = list(range(len(data)))
    if shuffle:
        import random; random.Random(seed).shuffle(idx)
    for i in range(0, len(idx), bs):
        yield [data[j] for j in idx[i:i + bs]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--bs", type=int, default=64)
    ap.add_argument("--d", type=int, default=128)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--lam-var", type=float, default=1.0)
    ap.add_argument("--lam-cov", type=float, default=0.04)
    ap.add_argument("--patience", type=int, default=10)
    ap.add_argument("--seed", type=int, default=20260714)
    args = ap.parse_args()
    torch.manual_seed(args.seed)
    dev = "cpu"

    tr, va, te, ch, ci, scaler, meta = D.build(seed=args.seed)
    TR = [build(e, scaler) for e in tr]; VA = [build(e, scaler) for e in va]; TE = [build(e, scaler) for e in te]
    print(f"pure JEPA-AC | train {len(TR)} val {len(VA)} test {len(TE)}")

    model = PureJepaAC(n_static=meta["n_static"], action_dim=meta["action_dim"], d=args.d,
                       H=meta["H"], post_h=D.POST_H).to(dev)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    print(f"params: {sum(p.numel() for p in model.parameters())/1e6:.2f}M")

    def pack(batch):
        pv, pm, qv, qm, st, ac = zip(*batch)
        return to_dev([pv, pm, qv, qm, st, ac], dev)

    @torch.no_grad()
    def val_loss():
        model.eval(); s = n = 0.0
        for b in batches(VA, 128, False):
            pv, pm, qv, qm, st, ac = pack(b)
            pred = model(pv, pm, st, ac); y = model.target(qv, qm)
            hm = (qm.sum(-1, keepdim=True) > 0).float()
            s += ((torch.abs(pred - y).mean(-1, keepdim=True) * hm).sum()).item(); n += hm.sum().item()
        return s / max(n, 1)

    best = float("inf"); best_state = None; bad = 0
    for ep in range(1, args.epochs + 1):
        model.train(); tj = tv = tc = nb = 0.0
        for b in batches(TR, args.bs, True, seed=args.seed + ep):
            pv, pm, qv, qm, st, ac = pack(b)
            pred = model(pv, pm, st, ac)                       # [B,T,d]
            y = model.target(qv, qm)                           # stop-grad EMA target
            hm = (qm.sum(-1, keepdim=True) > 0).float()        # [B,T,1] observed hours
            inv = (torch.abs(pred - y).mean(-1, keepdim=True) * hm).sum() / hm.sum().clamp(min=1)
            flat = pred[(hm.squeeze(-1) > 0)]                  # observed-hour reps [N,d]
            var, cov = vicreg(flat) if flat.shape[0] > 2 else (torch.zeros(()), torch.zeros(()))
            loss = inv + args.lam_var * var + args.lam_cov * cov
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0); opt.step(); model.ema_update()
            tj += inv.item(); tv += float(var); tc += float(cov); nb += 1
        vl = val_loss()
        if vl < best - 1e-4:
            best = vl; bad = 0; best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        else:
            bad += 1
        if ep % 2 == 0 or ep == 1:
            print(f"ep {ep:3d} | inv {tj/nb:.3f} var {tv/nb:.3f} cov {tc/nb:.3f} | val_inv {vl:.3f} "
                  f"(best {best:.3f}, pat {bad}/{args.patience})", flush=True)
        if bad >= args.patience:
            print(f"early stop at {ep}"); break
    if best_state:
        model.load_state_dict(best_state)
    model.eval()

    # ---- LINEAR PROBE: fit rep(true action)->labs on TRAIN, R^2 on TEST ----
    @torch.no_grad()
    def collect(split):
        X, Y = [], []
        for b in batches(split, 128, False):
            pv, pm, qv, qm, st, ac = pack(b)
            pred = model(pv, pm, st, ac).cpu().numpy(); qvv = qv.cpu().numpy(); qmm = qm.cpu().numpy()
            for i in range(len(b)):
                for t in range(D.POST_H):
                    if qmm[i, t].sum() > 0:
                        X.append(pred[i, t]); Y.append((qvv[i, t], qmm[i, t]))
        return np.array(X), Y
    Xtr, Ytr = collect(TR); Xte, Yte = collect(TE)
    A = np.hstack([Xtr, np.ones((len(Xtr), 1))])               # [n,d+1]
    Ytr_v = np.array([y for y, _ in Ytr]); Ytr_m = np.array([m for _, m in Ytr])
    # per-lab ridge probe (mask per lab)
    W = np.zeros((NLAB, A.shape[1]))
    for j in range(NLAB):
        sel = Ytr_m[:, j] > 0
        W[j] = np.linalg.lstsq(A[sel] + 0, Ytr_v[sel, j], rcond=None)[0] if sel.sum() > A.shape[1] else 0
    Ate = np.hstack([Xte, np.ones((len(Xte), 1))])
    Yte_v = np.array([y for y, _ in Yte]); Yte_m = np.array([m for _, m in Yte])
    print("\n===== PURE JEPA-AC (linear-probe R^2, TEST) =====")
    for j, lab in enumerate(D.TARGET_LABS):
        sel = Yte_m[:, j] > 0
        yt = Yte_v[sel, j]; yh = Ate[sel] @ W[j]
        ss_tot = ((yt - yt.mean()) ** 2).sum() or 1.0; r2 = 1 - ((yt - yh) ** 2).sum() / ss_tot
        print(f"  {lab:20s}  R2 {r2:+.3f}  (n={int(sel.sum())})")

    # ---- discrimination in latent space (roll under both actions) ----
    import statistics as st
    dur = st.median([e["action"][2] for e in tr if e["cohort"] == "dialysis"] or [1.0])
    ratio = st.median([e["action"][3] for e in tr if e["cohort"] == "diuretic"] or [0.5])
    a_d = torch.tensor([1., 0., dur, 0.]); a_u = torch.tensor([0., 1., 0., ratio])
    corr = n = ndial = 0
    with torch.no_grad():
        for i, e in enumerate(te):
            pv, pm, qv, qm, stt, _ = pack([TE[i]])
            tgt = model.target(qv, qm); hm = (qm.sum(-1, keepdim=True) > 0).float()
            pd = model(pv, pm, stt, a_d.unsqueeze(0)); pu = model(pv, pm, stt, a_u.unsqueeze(0))
            dd = ((torch.abs(pd - tgt).mean(-1, keepdim=True) * hm).sum()).item()
            du = ((torch.abs(pu - tgt).mean(-1, keepdim=True) * hm).sum()).item()
            true_dial = (e["cohort"] == "dialysis")
            corr += ((dd <= du) == true_dial); n += 1; ndial += true_dial
    base = max(ndial, n - ndial) / n
    print(f"\n  counterfactual discrimination: {corr/n:.3f}  (majority {base:.3f}, n={n})")


if __name__ == "__main__":
    main()
