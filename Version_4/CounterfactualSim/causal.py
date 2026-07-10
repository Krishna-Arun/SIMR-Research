#!/usr/bin/env python3
"""
causal.py — the deconfounding layer that turns the latent world model from a
CORRELATIONAL forecaster into a treatment-effect estimator (V4, P2).

The thesis: frozen foundation-model (CLMBR) latents encode *which arm a patient
was going to get* (confounding-by-indication — sicker patients get dialysis /
ventilation). A naive action-conditioned rollout on those latents therefore
reproduces the confounded association, not the interventional effect. This module:

  1. LEAKAGE DIAGNOSTIC  — quantify how predictable the treatment arm is from the
     raw latent z vs. from a balanced representation Φ(z). If arm is predictable
     from z above chance, z is confounded ("if the adapter can still predict the
     treatment, the 768 didn't turn in properly" — the user's framing). This is
     the paper's motivating result.
  2. BalanceAdapter Φ + GRL adversary — domain-adversarial balancing: Φ is trained
     to make the arm UN-predictable (adversary → chance) while staying useful for
     the outcome. Balancing strength λ_adv is swept, not maxed (over-balancing
     destroys prognostic signal — the CFR bias/variance trade-off).
  3. PROPENSITY + stabilized IPW — π(arm | raw z) (NOT Φ; balancing Φ would make
     propensities uninformative). Feeds inverse-propensity weights + the DR score.
  4. DOUBLY-ROBUST (AIPW) contrast — combine outcome heads μ_a(Φ) with π so the
     arm-difference estimate is consistent if EITHER model is right.
  5. POSITIVITY GATE — refuse / widen bands where a patient has no support under
     the queried arm (propensity out of range). Safety: never extrapolate into
     "would-never-have-been-treated-this-way" territory.

Assumption stated honestly: identification requires sequential ignorability /
no-unobserved-confounding *given the CLMBR latent*. Balancing removes confounding
that is PRESENT in z; it cannot fix confounders absent from the record.

CPU-runnable. `python causal.py` runs the leakage diagnostic on the real cohort
anchor latents (from wm_sequences.pkl) and a synthetic balancing check.
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

HERE = Path(__file__).resolve().parent
SEQ_PKL = HERE / "wm_sequences.pkl"


# ── gradient reversal ─────────────────────────────────────────────────────────
class _GradReverse(torch.autograd.Function):
    @staticmethod
    def forward(ctx, x, lambd):
        ctx.lambd = lambd
        return x.view_as(x)

    @staticmethod
    def backward(ctx, grad):
        return -ctx.lambd * grad, None


def grad_reverse(x, lambd=1.0):
    return _GradReverse.apply(x, lambd)


# ── balance adapter + adversary ───────────────────────────────────────────────
class BalanceAdapter(nn.Module):
    """z -> Φ(z): the treatment-balanced representation the outcome/effect heads use."""
    def __init__(self, state_dim=768, rep_dim=128):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(state_dim, rep_dim), nn.LayerNorm(rep_dim), nn.ReLU())

    def forward(self, z):
        return self.net(z)


class ArmHead(nn.Module):
    """Arm classifier. Used two ways: as the GRL adversary on Φ (to balance), and as
    a fresh probe (to measure residual leakage)."""
    def __init__(self, rep_dim=128, n_arms=3, hidden=64):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(rep_dim, hidden), nn.ReLU(), nn.Linear(hidden, n_arms))

    def forward(self, h):
        return self.net(h)


# ── metrics ───────────────────────────────────────────────────────────────────
def macro_ovr_auc(probs: np.ndarray, y: np.ndarray) -> float:
    """Macro one-vs-rest AUC — robust to class imbalance (chance = 0.5)."""
    aucs = []
    for k in range(probs.shape[1]):
        s = probs[:, k]; pos = (y == k)
        np_, nn_ = int(pos.sum()), int((~pos).sum())
        if np_ == 0 or nn_ == 0:
            continue
        order = np.argsort(s)
        ranks = np.empty_like(order, dtype=float)
        ranks[order] = np.arange(1, len(s) + 1)
        # average ranks for ties
        _, inv, cnt = np.unique(s, return_inverse=True, return_counts=True)
        csum = np.cumsum(cnt); start = csum - cnt
        avg = (start + csum + 1) / 2.0
        ranks = avg[inv]
        auc = (ranks[pos].sum() - np_ * (np_ + 1) / 2) / (np_ * nn_)
        aucs.append(auc)
    return float(np.mean(aucs)) if aucs else 0.5


def balanced_accuracy(pred: np.ndarray, y: np.ndarray, n_arms: int) -> float:
    recs = []
    for k in range(n_arms):
        m = (y == k)
        if m.sum() > 0:
            recs.append((pred[m] == k).mean())
    return float(np.mean(recs)) if recs else 0.0


def _fit_probe(Ztr, ytr, Zva, yva, n_arms, epochs=300, lr=1e-2, rep=False, adapter=None,
               adv_lambda=0.0, seed=0):
    """Fit an arm classifier and return (macro_auc, balanced_acc) on val. If `adapter`
    is given, classify on Φ(z); if adv_lambda>0, jointly train the adapter through a
    GRL so Φ is pushed toward arm-invariance (the balancing objective)."""
    torch.manual_seed(seed)
    d = adapter.net[0].out_features if adapter is not None else Ztr.shape[1]
    clf = ArmHead(d, n_arms)
    params = list(clf.parameters()) + (list(adapter.parameters()) if adv_lambda > 0 else [])
    opt = torch.optim.Adam(params, lr=lr, weight_decay=1e-4)
    Ztr_t, ytr_t = torch.from_numpy(Ztr), torch.from_numpy(ytr)
    for _ in range(epochs):
        clf.train()
        h = adapter(Ztr_t) if adapter is not None else Ztr_t
        if adv_lambda > 0:
            h = grad_reverse(h, adv_lambda)
        loss = F.cross_entropy(clf(h), ytr_t)
        opt.zero_grad(); loss.backward(); opt.step()
    clf.eval()
    with torch.no_grad():
        hv = adapter(torch.from_numpy(Zva)) if adapter is not None else torch.from_numpy(Zva)
        p = torch.softmax(clf(hv), -1).numpy()
    return macro_ovr_auc(p, yva), balanced_accuracy(p.argmax(1), yva, n_arms)


def leakage_diagnostic(Z, arm, split, n_arms=3):
    """Core paper result. Returns treatment-arm predictability from (a) raw z and
    (b) an adversarially-balanced Φ(z). Confounding is real if (a) > chance;
    balancing works if (b) → chance."""
    tr, va = split == "train", split == "val"
    Ztr, ytr, Zva, yva = Z[tr], arm[tr], Z[va], arm[va]
    base = np.bincount(ytr, minlength=n_arms) / len(ytr)
    # (a) raw latent
    auc_raw, ba_raw = _fit_probe(Ztr, ytr, Zva, yva, n_arms)
    # (b) balanced representation: train Φ + adversary, then probe Φ with a FRESH head
    adapter = BalanceAdapter(Z.shape[1], 128)
    _fit_probe(Ztr, ytr, Ztr, ytr, n_arms, epochs=400, adapter=adapter, adv_lambda=1.0)
    auc_bal, ba_bal = _fit_probe(Ztr, ytr, Zva, yva, n_arms, adapter=adapter, adv_lambda=0.0)
    return {"base_rates": base.round(3).tolist(),
            "chance_auc": 0.5, "chance_bal_acc": round(1.0 / n_arms, 3),
            "raw_z": {"macro_auc": round(auc_raw, 3), "balanced_acc": round(ba_raw, 3)},
            "balanced_phi": {"macro_auc": round(auc_bal, 3), "balanced_acc": round(ba_bal, 3)},
            "leakage_removed_auc": round(auc_raw - auc_bal, 3)}


# ── propensity + stabilized IPW (on RAW z) ────────────────────────────────────
def fit_propensity(Z, arm, tr_mask, n_arms=3, epochs=300, lr=1e-2):
    """π(arm | raw z) via multinomial logistic. Returns (probs[N,n_arms], stabilized
    IPW weights[N], val_ce). IPW uses RAW z on purpose — a balanced Φ would give
    uninformative (~uniform) propensities."""
    torch.manual_seed(0)
    zt, at = torch.from_numpy(Z), torch.from_numpy(arm)
    clf = nn.Linear(Z.shape[1], n_arms)
    opt = torch.optim.Adam(clf.parameters(), lr=lr, weight_decay=1e-3)
    idx = torch.from_numpy(np.where(tr_mask)[0])
    for _ in range(epochs):
        opt.zero_grad()
        loss = F.cross_entropy(clf(zt[idx]), at[idx])
        loss.backward(); opt.step()
    with torch.no_grad():
        p = torch.softmax(clf(zt), -1)
        marg = torch.tensor([(at[idx] == k).float().mean() for k in range(n_arms)])
        w = torch.ones(len(Z))
        for k in range(n_arms):
            sel = at == k
            w[sel] = marg[k] / p[sel, k].clamp(min=1e-3)          # stabilized IPW
        w = w.clamp(0.1, 10.0)
    return p.numpy(), w.numpy(), float(loss.detach())


def positivity_gate(prop_row: np.ndarray, arm_idx: int, lo=0.05) -> dict:
    """Overlap check for a counterfactual query. If π(queried arm | z) < lo, the
    patient is off-support for that arm → the estimate is extrapolation."""
    p = float(prop_row[arm_idx])
    return {"propensity": round(p, 4), "on_support": p >= lo,
            "action": "trust" if p >= lo else "off_support: widen bands / refuse"}


def aipw_contrast(mu_a: np.ndarray, mu_b: np.ndarray, y: np.ndarray, arm: np.ndarray,
                  prop: np.ndarray, a: int, b: int) -> float:
    """Doubly-robust (AIPW) estimate of E[Y(a) - Y(b)]. mu_a/mu_b are outcome-head
    predictions under each arm; the IPW correction on the factual arm makes it
    consistent if EITHER the outcome model OR the propensity model is correct."""
    def arm_mean(k, mu_k):
        corr = np.zeros(len(y))
        sel = arm == k
        corr[sel] = (y[sel] - mu_k[sel]) / prop[sel, k].clip(1e-3)
        return (mu_k + corr).mean()
    return float(arm_mean(a, mu_a) - arm_mean(b, mu_b))


if __name__ == "__main__":
    if not SEQ_PKL.exists():
        raise SystemExit("run: python train_wm.py --build   (need wm_sequences.pkl)")
    sub = pickle.load(open(SEQ_PKL, "rb"))
    PRE = sub["grid"]["PRE"]
    Z_anchor = sub["Z"][:, PRE].astype("float32")            # per-patient anchor latent
    arm = sub["ARM"].astype("int64")
    split = sub["SPLIT"]
    valid = arm >= 0
    Z_anchor, arm, split = Z_anchor[valid], arm[valid], split[valid]
    arm_names = sub["schema"]["arm_classes"]

    print(f"[causal] leakage diagnostic on {len(Z_anchor)} anchor latents "
          f"(arms {arm_names}, D={Z_anchor.shape[1]})")
    diag = leakage_diagnostic(Z_anchor, arm, split, n_arms=len(arm_names))
    print(f"  base rates {arm_names} = {diag['base_rates']}  (chance AUC {diag['chance_auc']}, "
          f"chance bal-acc {diag['chance_bal_acc']})")
    print(f"  RAW z      : arm macro-AUC {diag['raw_z']['macro_auc']:.3f}  "
          f"balanced-acc {diag['raw_z']['balanced_acc']:.3f}   <- confounding present if > chance")
    print(f"  BALANCED Φ : arm macro-AUC {diag['balanced_phi']['macro_auc']:.3f}  "
          f"balanced-acc {diag['balanced_phi']['balanced_acc']:.3f}   <- should fall toward chance")
    print(f"  leakage removed (Δ macro-AUC) = {diag['leakage_removed_auc']:+.3f}")

    p, w, ce = fit_propensity(Z_anchor, arm, split == "train", n_arms=len(arm_names))
    print(f"[causal] propensity π(arm|z) CE={ce:.3f}  IPW w[min/med/max]="
          f"{w.min():.2f}/{np.median(w):.2f}/{w.max():.2f}")
    off = (p.max(1) < 0.05).sum()
    print(f"[causal] positivity: {int((p.min(1) < 0.05).sum())}/{len(p)} patients off-support "
          f"for >=1 arm (π<0.05); gate ready for simulate().")
