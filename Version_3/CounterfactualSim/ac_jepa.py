#!/usr/bin/env python3
"""
AC-JEPA (Action-Conditioned JEPA) — the enriched counterfactual world model.

A per-transition, Δt-aware, PROBABILISTIC residual predictor over frozen CLMBR latents,
with causal-inference machinery so it estimates *treatment* effects rather than merely
correlational trajectories:

  predictor:  adapter(z:768→128) ⊕ act_enc(a:34→32) ⊕ dt_enc(Δt:2→16)
              → 2-layer LayerNorm/ReLU trunk (→256)
              → μ head (768) and logvar head (768)      # Gaussian over the residual Δz
              + arm head (128→n_arms) fed through a GRADIENT-REVERSAL layer   # CRN adversary
  target:     residual  Δz = z_{t+1} − z_t   (predict the CHANGE, not the absolute state)
  loss:       IPW-weighted Gaussian NLL(Δz; μ, logvar)  +  λ · CE(arm | GRL(adapter(z)))
  inference:  z_{t+1} = z_t + μ(z_t, a_t, Δt);  counterfactuals swap a_t and Monte-Carlo
              sample Δz ~ N(μ, σ²) (K rolls) → trajectory means + uncertainty bands.

Decoders (trained separately on the SAME frozen latents):
  lab_decoder:      768 → 128 → 14   (standardized LOCF lab panel, masked-MSE)
  outcome_decoder:  768 → 64 → 1     (1-year mortality, BCE)

The CRN adversary (Bica et al., "Estimating counterfactual treatment outcomes over time")
scrubs treatment-arm information out of adapter(z) via gradient reversal, so the balanced
representation does not simply encode "which arm this patient was always going to get" —
that is what lets the μ head express a genuine *action* effect. IPW (stabilized inverse
propensity weights from a logistic π(arm|z)) corrects for confounded treatment assignment.
"""
from __future__ import annotations

import torch
import torch.nn as nn


# ── gradient reversal (CRN adversary) ────────────────────────────────────────
class _GradReverse(torch.autograd.Function):
    @staticmethod
    def forward(ctx, x, lambd):
        ctx.lambd = lambd
        return x.view_as(x)

    @staticmethod
    def backward(ctx, grad):
        return -ctx.lambd * grad, None


def grad_reverse(x, lambd: float = 1.0):
    return _GradReverse.apply(x, lambd)


def featurize_dt(dt_hours: torch.Tensor) -> torch.Tensor:
    """Δt (hours) -> [log1p(Δt), Δt/24].  dt_hours [B] -> [B,2]."""
    dt = dt_hours.clamp(min=0.0)
    return torch.stack([torch.log1p(dt), dt / 24.0], dim=-1)


class ACJEPAPredictor(nn.Module):
    def __init__(self, state_dim: int = 768, action_dim: int = 34, n_arms: int = 3,
                 adapt: int = 128, act: int = 32, dt: int = 16, trunk: int = 256):
        super().__init__()
        self.state_dim, self.action_dim, self.n_arms = state_dim, action_dim, n_arms
        self.adapter = nn.Sequential(nn.Linear(state_dim, adapt), nn.LayerNorm(adapt), nn.ReLU())
        self.act_enc = nn.Sequential(nn.Linear(action_dim, act), nn.ReLU())
        self.dt_enc = nn.Sequential(nn.Linear(2, dt), nn.ReLU())
        d = adapt + act + dt
        self.trunk = nn.Sequential(
            nn.Linear(d, trunk), nn.LayerNorm(trunk), nn.ReLU(),
            nn.Linear(trunk, trunk), nn.LayerNorm(trunk), nn.ReLU())
        self.mu = nn.Linear(trunk, state_dim)          # predicted residual mean
        self.logvar = nn.Linear(trunk, state_dim)      # predicted residual log-variance
        self.arm_head = nn.Linear(adapt, n_arms)       # CRN adversary on adapter(z)

    def forward(self, z, a, dt_hours, adv_lambda: float = 0.5):
        """z [B,768], a [B,34], dt_hours [B] -> (mu[B,768], logvar[B,768], arm_logits[B,n_arms])."""
        h_z = self.adapter(z)
        h = torch.cat([h_z, self.act_enc(a), self.dt_enc(featurize_dt(dt_hours))], dim=-1)
        t = self.trunk(h)
        mu = self.mu(t)
        logvar = self.logvar(t).clamp(-8.0, 8.0)       # numerical stability
        arm_logits = self.arm_head(grad_reverse(h_z, adv_lambda))
        return mu, logvar, arm_logits

    @torch.no_grad()
    def next_latent(self, z, a, dt_hours):
        """Deterministic transition:  z_{t+1} = z_t + μ(z_t, a_t, Δt)."""
        mu, _, _ = self.forward(z, a, dt_hours, adv_lambda=0.0)
        return z + mu

    @torch.no_grad()
    def sample_next(self, z, a, dt_hours):
        """Stochastic transition: sample Δz ~ N(μ, σ²), return z + Δz (for MC rollout)."""
        mu, logvar, _ = self.forward(z, a, dt_hours, adv_lambda=0.0)
        eps = torch.randn_like(mu)
        dz = mu + torch.exp(0.5 * logvar) * eps
        return z + dz


def gaussian_nll(target, mu, logvar, weight=None):
    """IPW-weighted diagonal-Gaussian NLL of `target` under N(mu, exp(logvar)).
    target/mu/logvar [B,D]; weight [B] (per-transition IPW) or None. Returns scalar."""
    nll = 0.5 * (logvar + (target - mu) ** 2 * torch.exp(-logvar))   # [B,D]
    per_row = nll.sum(dim=-1)                                        # [B]
    if weight is not None:
        per_row = per_row * weight
        return per_row.sum() / weight.sum().clamp(min=1e-6)
    return per_row.mean()


# ── frozen-latent readout decoders ───────────────────────────────────────────
class LabDecoder(nn.Module):
    """768 -> 128 -> n_labs.  Decodes a (predicted) latent to a standardized lab panel."""
    def __init__(self, state_dim: int = 768, n_labs: int = 14, hidden: int = 128):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(state_dim, hidden), nn.ReLU(), nn.Linear(hidden, n_labs))

    def forward(self, z):
        return self.net(z)


class OutcomeDecoder(nn.Module):
    """768 -> 64 -> 1 mortality logit."""
    def __init__(self, state_dim: int = 768, hidden: int = 64):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(state_dim, hidden), nn.ReLU(), nn.Linear(hidden, 1))

    def forward(self, z):
        return self.net(z).squeeze(-1)


def masked_mse(pred, target, mask):
    """MSE over observed lab entries only. pred/target/mask [B,n_labs]."""
    diff = (pred - target) ** 2 * mask
    return diff.sum() / mask.sum().clamp(min=1e-6)


if __name__ == "__main__":
    torch.manual_seed(0)
    B = 8
    pred = ACJEPAPredictor()
    z = torch.randn(B, 768); a = torch.randn(B, 34); dt = torch.rand(B) * 48
    mu, lv, arm = pred(z, a, dt)
    tgt = torch.randn(B, 768)
    w = torch.rand(B) + 0.5
    print("mu", tuple(mu.shape), "logvar", tuple(lv.shape), "arm", tuple(arm.shape))
    print("nll", float(gaussian_nll(tgt, mu, lv, w)))
    print("next_latent", tuple(pred.next_latent(z, a, dt).shape),
          "| sample_next", tuple(pred.sample_next(z, a, dt).shape))
    ld, od = LabDecoder(), OutcomeDecoder()
    print("lab", tuple(ld(z).shape), "outcome", tuple(od(z).shape),
          "| params:", sum(p.numel() for p in pred.parameters()))
