#!/usr/bin/env python3
"""
#3 to the FULL: DAG-guided DISENTANGLED latent world model.

Instead of one latent with an adversary bolted on, the latent is explicitly factored
into two DAG-motivated subspaces (DR-CFR style):
  z_conf  -- the CONFOUNDER/prognosis subspace: allowed to encode treatment assignment
             (an arm head is TRAINED to predict the arm from it) -> keeps prognostic signal
  z_eff   -- the TREATMENT-RESPONSE subspace: assignment is SCRUBBED (gradient-reversed
             arm adversary) -> carries the causal effect; the action + rollout act here
A decorrelation penalty keeps the two subspaces capturing different things.
Decoding combines the effect-rollout-state with z_conf (prognosis + response).
IPW weights the outcome loss.

Hypothesis: correct effect signs (like CRN) WITHOUT the accuracy collapse -- because
prognostic info is preserved in z_conf while only z_eff is de-confounded.
"""
import argparse, os
import numpy as np
import torch, torch.nn as nn
import wm_data as D
import train_wm as T
from train_wm_causal import effect_recovery, IPW_BASELINE, conf, _GRL, grad_reverse
from wm_model import HourlyEncoder
from sklearn.linear_model import LogisticRegression

HERE = os.path.dirname(os.path.abspath(__file__)); NLAB = len(D.TARGET_LABS)


class DisentangledCausalWM(nn.Module):
    def __init__(self, C, n_static, n_labs=4, action_dim=4, d=128, d_conf=96, d_eff=96, post_h=72, dropout=0.2):
        super().__init__()
        self.encoder = HourlyEncoder(C, n_static, d=d, dropout=dropout, H=48)
        self.to_conf = nn.Linear(d, d_conf); self.to_eff = nn.Linear(d, d_eff)
        self.film = nn.Linear(action_dim, 2 * d_eff); nn.init.zeros_(self.film.weight); nn.init.zeros_(self.film.bias)
        self.act_emb = nn.Linear(action_dim, d_eff)
        self.cell = nn.GRUCell(d_eff, d_eff)
        self.dyn = nn.Sequential(nn.Linear(d_eff, d_eff), nn.LayerNorm(d_eff), nn.GELU(), nn.Linear(d_eff, d_eff))
        self.norm = nn.LayerNorm(d_eff)
        self.dec = nn.Sequential(nn.Linear(d_eff + d_conf, d), nn.LayerNorm(d), nn.GELU(), nn.Dropout(dropout), nn.Linear(d, n_labs))
        self.conf_arm = nn.Sequential(nn.Linear(d_conf, d_conf // 2), nn.GELU(), nn.Linear(d_conf // 2, 2))
        self.eff_arm = nn.Sequential(nn.Linear(d_eff, d_eff // 2), nn.GELU(), nn.Linear(d_eff // 2, 2))
        self.post_h, self.d_conf, self.d_eff = post_h, d_conf, d_eff

    def encode(self, grid, active, static):
        z = self.encoder(grid, active, static)
        return self.to_conf(z), self.to_eff(z)

    def rollout(self, z_conf, z_eff, action):
        g, b = self.film(action).chunk(2, -1); s = (1 + g) * z_eff + b
        a = self.act_emb(action); outs = []
        for _ in range(self.post_h):
            s = self.cell(a, s); s = self.norm(s + self.dyn(s))
            outs.append(self.dec(torch.cat([s, z_conf], -1)))
        return torch.stack(outs, 1)

    def forward(self, grid, active, static, action):
        zc, ze = self.encode(grid, active, static)
        return self.rollout(zc, ze, action)


def decorr(zc, ze):
    zc = (zc - zc.mean(0)) / (zc.std(0) + 1e-5); ze = (ze - ze.mean(0)) / (ze.std(0) + 1e-5)
    c = (zc.T @ ze) / zc.shape[0]
    return (c ** 2).mean()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=45); ap.add_argument("--d", type=int, default=128)
    ap.add_argument("--lam-conf", type=float, default=0.5); ap.add_argument("--lam-eff", type=float, default=0.5)
    ap.add_argument("--lam-dec", type=float, default=1.0); ap.add_argument("--seed", type=int, default=20260714)
    args = ap.parse_args(); torch.manual_seed(args.seed); dev = "cpu"

    train, val, test, channels, ci, scaler, meta = D.build(seed=args.seed)
    Ctr = np.stack([conf(e, scaler) for e in train]); Ttr = np.array([e["cohort"] == "dialysis" for e in train]).astype(int)
    ps = LogisticRegression(max_iter=1000).fit(Ctr, Ttr); pT = Ttr.mean()
    wmap = {}
    for e in train + val + test:
        p = float(np.clip(ps.predict_proba(conf(e, scaler)[None])[0, 1], 1e-3, 1 - 1e-3))
        wmap[e["hadm"]] = float(np.clip((pT / p) if e["cohort"] == "dialysis" else ((1 - pT) / (1 - p)), 0.1, 10))
    print(f"disentangled causal WM | train {len(train)} val {len(val)} test {len(test)}")

    model = DisentangledCausalWM(meta["C"], meta["n_static"], action_dim=meta["action_dim"], d=args.d, post_h=D.POST_H).to(dev)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4); ce = nn.CrossEntropyLoss()
    cd, cu = T.canon_actions(train, dev)
    print(f"params: {sum(p.numel() for p in model.parameters())/1e6:.2f}M | z_conf={model.d_conf} z_eff={model.d_eff}")

    def collate_w(b):
        grid, active, static, action, ptgt, pmask = T.collate(b, channels, ci, scaler, dev)
        arm = torch.tensor([1 if e["cohort"] == "dialysis" else 0 for e in b]).to(dev)
        w = torch.tensor([wmap[e["hadm"]] for e in b], dtype=torch.float).to(dev)
        return grid, active, static, action, ptgt, pmask, arm, w

    best = 1e9; bad = 0; best_state = None
    for ep in range(1, args.epochs + 1):
        model.train(); grl = min(1.0, ep / 8.0); tot = ca = ea = nb = 0.0
        for b in T.batches(train, 64, True, seed=args.seed + ep):
            grid, active, static, action, ptgt, pmask, arm, w = collate_w(b)
            zc, ze = model.encode(grid, active, static)
            pred = model.rollout(zc, ze, action)
            w3 = w[:, None, None]
            mse = (((pred - ptgt) ** 2) * pmask * w3).sum() / (pmask * w3).sum().clamp(min=1)
            l_conf = ce(model.conf_arm(zc), arm)                       # z_conf SHOULD predict arm
            l_eff = ce(model.eff_arm(grad_reverse(ze, grl)), arm)      # z_eff should NOT (reversed)
            l_dec = decorr(zc, ze)
            loss = mse + args.lam_conf * l_conf + args.lam_eff * grl * l_eff + args.lam_dec * l_dec
            opt.zero_grad(); loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0); opt.step()
            tot += mse.item(); ca += l_conf.item(); ea += l_eff.item(); nb += 1
        # val mse
        model.eval(); s = n = 0.0
        with torch.no_grad():
            for b in T.batches(val, 128, False):
                grid, active, static, action, ptgt, pmask = T.collate(b, channels, ci, scaler, dev)
                pr = model(grid, active, static, action); s += (((pr - ptgt) ** 2) * pmask).sum().item(); n += pmask.sum().item()
        vm = s / max(n, 1)
        if vm < best - 1e-4: best = vm; bad = 0; best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        else: bad += 1
        if ep % 3 == 0 or ep == 1:
            print(f"ep {ep:3d} | mse {tot/nb:.3f} conf_arm {ca/nb:.3f} eff_arm {ea/nb:.3f} | val {vm:.3f} (best {best:.3f}, pat {bad}/10)", flush=True)
        if bad >= 10: print(f"early stop {ep}"); break
    if best_state: model.load_state_dict(best_state)

    m = T.evaluate(model, test, channels, ci, scaler, dev)
    d = T.discriminate(model, test, channels, ci, scaler, dev, train)
    eff = effect_recovery(model, test, channels, ci, scaler, dev, train)
    print("\n===== DISENTANGLED CAUSAL WM -- TEST =====")
    for lab, sdict in m["per_lab"].items():
        print(f"  {lab:20s} R2 {sdict['r2']:+.3f}  MAE {sdict['mae']:.3f}")
    print(f"  discrimination: {d['disc_acc']:.3f} (majority {d['majority_baseline']:.3f})")
    print("\n  EFFECT RECOVERY (dialysis - diuretic):")
    print(f"  {'lab':20s} {'WM effect':>10} {'IPW baseline':>13} {'sign OK?':>9}")
    for j, lab in enumerate(D.TARGET_LABS):
        base = IPW_BASELINE[lab]; ok = "yes" if np.sign(eff[j]) == np.sign(base) else "NO"
        print(f"  {lab:20s} {eff[j]:+10.2f} {base:+13.2f} {ok:>9}")
    torch.save({"model": model.state_dict(), "args": vars(args)}, os.path.join(HERE, "wm_disentangled.pt"))
    print("\ncheckpoint -> wm_disentangled.pt")


if __name__ == "__main__":
    main()
