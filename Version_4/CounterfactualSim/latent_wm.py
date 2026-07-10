#!/usr/bin/env python3
"""
latent_wm.py — 1-D action-conditioned latent world model (V4).

A faithful 1-D adaptation of V-JEPA 2-AC's `VisionTransformerPredictorAC`
(Version_3/vjepa2/src/models/ac_predictor.py) to a TEMPORAL patient-state
sequence. It replaces both V3 world models:

  - ac_jepa.py      : per-transition MLP, trained 1-step / served 3-step (OOD).
  - world_model.py  : transformer + EMA teacher that was never wired in.

Design (matches V-JEPA 2-AC, adapted to D=768 CLMBR latents):

  tokens per step t : [ action_t , dt_t , z_t ]          (2 cond tokens + 1 state)
  attention         : BLOCK-CAUSAL — step t attends to all tokens of steps <= t
  prediction        : read the state-slot output at step t -> residual Δz_t
                      z_{t+1} = z_t + Δz_t   (predict the CHANGE; natural-history base)
  objective (Eq.2+3): L = L_teacher_forcing + L_rollout   (both raw L1)
                      TF   : predict z_{2..T+1} from the REAL z_{1..T}
                      AR   : predict z_{2..T+1} from the model's OWN rollout
                             (this is what stops multi-step drift at serve time)

The action-effect / causal-deconfounding machinery (balance adapter, propensity,
doubly-robust heads, positivity gate) is layered ON TOP of this predictor in
causal.py (P2). This file is only the predictor + losses + rollout, so its
exit-gate can be measured in isolation: beat persistence AND mean-Δ AND the
1-step baseline on MULTI-STEP validation, in-distribution.

STATUS: CPU-runnable. `python latent_wm.py` runs a synthetic smoke train that
must show the rollout loss decreasing and beating persistence.
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


def featurize_dt(dt_hours: torch.Tensor) -> torch.Tensor:
    """Δt (hours) -> [log1p(Δt), Δt/24]. dt_hours [...] -> [...,2]."""
    dt = dt_hours.clamp(min=0.0)
    return torch.stack([torch.log1p(dt), dt / 24.0], dim=-1)


def build_block_causal_mask(T: int, tokens_per_step: int, device) -> torch.Tensor:
    """Additive attention mask [N,N] (N=T*tokens_per_step). A token in step i may
    attend to every token in steps j <= i (full attention within an allowed step,
    including the future cond-tokens of the current step — they carry the action we
    are conditioning on). Future steps are masked with -inf."""
    n = T * tokens_per_step
    step = torch.arange(n, device=device) // tokens_per_step          # step index per token
    allowed = step[None, :] <= step[:, None]                          # [N,N] bool: key_step <= query_step
    mask = torch.zeros(n, n, device=device)
    mask.masked_fill_(~allowed, float("-inf"))
    return mask


class LatentWorldModel(nn.Module):
    def __init__(self, state_dim: int = 768, action_dim: int = 34, hidden: int = 512,
                 depth: int = 6, heads: int = 8, mlp_ratio: float = 4.0, dropout: float = 0.0):
        super().__init__()
        self.state_dim, self.action_dim = state_dim, action_dim
        self.tokens_per_step = 3                                       # [action, dt, state]
        self.state_in = nn.Linear(state_dim, hidden)
        self.action_in = nn.Linear(action_dim, hidden)
        self.dt_in = nn.Linear(2, hidden)
        self.pos = nn.Embedding(4096, hidden)                         # position over token stream
        layer = nn.TransformerEncoderLayer(hidden, heads, int(hidden * mlp_ratio),
                                           dropout=dropout, batch_first=True, activation="gelu")
        self.blocks = nn.TransformerEncoder(layer, depth)
        self.norm = nn.LayerNorm(hidden)
        self.head = nn.Linear(hidden, state_dim)                      # -> residual Δz

    def _encode(self, states, actions, dts):
        """states [B,T,D], actions [B,T,A], dts [B,T] -> token stream [B, 3T, H]."""
        B, T, _ = states.shape
        a = self.action_in(actions)                                   # [B,T,H]
        d = self.dt_in(featurize_dt(dts))                             # [B,T,H]
        s = self.state_in(states)                                     # [B,T,H]
        tok = torch.stack([a, d, s], dim=2).reshape(B, self.tokens_per_step * T, -1)
        idx = torch.arange(tok.size(1), device=states.device)
        return tok + self.pos(idx)[None]

    def forward(self, states, actions, dts):
        """Teacher-forced next-state prediction.
        states [B,T,D], actions [B,T,A], dts [B,T] -> predicted z_{t+1} [B,T,D]."""
        B, T, _ = states.shape
        tok = self._encode(states, actions, dts)
        mask = build_block_causal_mask(T, self.tokens_per_step, states.device)
        tok = self.blocks(tok, mask=mask)
        s_slots = tok[:, 2::self.tokens_per_step, :]                  # state-slot outputs, one per step
        dz = self.head(self.norm(s_slots))                           # residual Δz
        return states + dz                                            # z_{t+1} = z_t + Δz

    @torch.no_grad()
    def rollout(self, z0, action_seq, dt_seq):
        """Autoregressive counterfactual rollout from z0 [B,D] under actions
        [B,K,A] / dts [B,K]. Returns predicted latents [B,K,D]."""
        self.eval()
        states = z0.unsqueeze(1)                                      # [B,1,D]
        outs = []
        for t in range(action_seq.shape[1]):
            acts = action_seq[:, : t + 1, :]
            dts = dt_seq[:, : t + 1]
            nxt = self.forward(states, acts, dts)[:, -1:, :]          # predicted z_{t+1}
            outs.append(nxt)
            states = torch.cat([states, nxt], dim=1)
        return torch.cat(outs, dim=1)


def rollout_predictions(model: LatentWorldModel, states, actions, dts):
    """Return (z_tf, z_ar): teacher-forced and autoregressive next-state predictions,
    both [B,T,D], mirroring V-JEPA 2-AC's forward_predictions. z_ar predicts from the
    model's OWN outputs (rolls z_1 forward T-1 steps)."""
    B, T, D = states.shape
    z_tf = model.forward(states, actions, dts)                       # [B,T,D]
    # autoregressive: start from the real first state, then feed predictions
    seq = states[:, :1, :]                                           # [B,1,D]
    for t in range(T):
        nxt = model.forward(seq, actions[:, : t + 1, :], dts[:, : t + 1])[:, -1:, :]
        seq = torch.cat([seq, nxt], dim=1)
    z_ar = seq[:, 1:, :]                                             # predicted z_{2..T+1}
    return z_tf, z_ar


def wm_loss(z_pred, z_target, loss_exp: float = 1.0):
    """V-JEPA 2-AC feature-regression loss: mean |pred - target|^exp / exp (L1 at exp=1)."""
    return torch.mean(torch.abs(z_pred - z_target) ** loss_exp) / loss_exp


def _make_synthetic(B, T, D, A, seed=0):
    """Synthetic dynamics with a REAL, action-dependent effect: Δz = f(action) + small
    noise. A model that ignores the action cannot beat persistence; a model that drifts
    on rollout cannot beat teacher-forcing. Held-out split returned for an honest gate."""
    g = torch.Generator().manual_seed(seed)
    W = torch.randn(A, D, generator=g) * 0.10                       # action -> Δz map (first 4 dims used)
    z0 = torch.randn(B, D, generator=g)
    actions = torch.zeros(B, T, A)
    pick = torch.randint(0, 4, (B, T), generator=g)
    actions[torch.arange(B)[:, None], torch.arange(T)[None], pick] = 1.0
    dts = torch.rand(B, T, generator=g) * 24 + 1
    z = [z0]
    for t in range(T):
        dz = actions[:, t] @ W + 0.01 * torch.randn(B, D, generator=g)
        z.append(z[-1] + dz)
    states = torch.stack(z[:-1], dim=1)                             # z_1..z_T   [B,T,D]
    targets = torch.stack(z[1:], dim=1)                             # z_2..z_{T+1}
    return states, actions, dts, targets


if __name__ == "__main__":
    # Smoke test: prove wiring + that the model LEARNS action-conditioned dynamics
    # and that the autoregressive rollout beats persistence / mean-Δ on a held-out
    # split. Uses a reduced state_dim so it trains to convergence fast on CPU; the
    # real cohort trainer (train_wm.py, P1) uses the full D=768 CLMBR latents.
    torch.manual_seed(0)
    B, T, D, A = 96, 5, 64, 34
    model = LatentWorldModel(state_dim=D, action_dim=A, hidden=128, depth=3, heads=8)
    states, actions, dts, targets = _make_synthetic(B, T, D, A, seed=0)
    # held-out sequences: the multi-step gate is measured on data not trained on
    tr, va = slice(0, 64), slice(64, 96)

    opt = torch.optim.Adam(model.parameters(), lr=3e-3)
    for ep in range(400):
        model.train()
        z_tf, z_ar = rollout_predictions(model, states[tr], actions[tr], dts[tr])
        loss = wm_loss(z_tf, targets[tr]) + wm_loss(z_ar, targets[tr])     # TF + rollout (Eq.4)
        opt.zero_grad(); loss.backward(); opt.step()

    model.eval()
    with torch.no_grad():
        z_tf, z_ar = rollout_predictions(model, states[va], actions[va], dts[va])
        mse_tf = F.mse_loss(z_tf, targets[va]).item()
        mse_ar = F.mse_loss(z_ar, targets[va]).item()              # multi-step (the honest gate)
        mse_persist = F.mse_loss(states[va], targets[va]).item()   # Δz=0
        mean_dz = (targets[tr] - states[tr]).mean((0, 1))          # global mean Δ fit on TRAIN
        mse_meandz = F.mse_loss(states[va] + mean_dz, targets[va]).item()
        roll = model.rollout(states[va][:, 0], actions[va], dts[va])
    print(f"smoke OK — final loss {float(loss.detach()):.4f}  (val split, held-out)")
    print(f"  multi-step AR   MSE {mse_ar:.4f}")
    print(f"  teacher-forced  MSE {mse_tf:.4f}")
    print(f"  persistence     MSE {mse_persist:.4f}  (Δz=0 baseline)")
    print(f"  mean-Δ          MSE {mse_meandz:.4f}  (global mean baseline)")
    print(f"  rollout shape   {tuple(roll.shape)} | params {sum(p.numel() for p in model.parameters()):,}")
    beats = mse_ar < mse_persist and mse_ar < mse_meandz
    print(f"  EXIT GATE (AR beats persistence AND mean-Δ): {'PASS' if beats else 'FAIL'}")
