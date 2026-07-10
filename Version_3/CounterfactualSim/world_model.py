#!/usr/bin/env python3
"""
Action-conditioned latent world model — the PREDICTOR half of the CF-sim engine.

Adapted from V-JEPA2's action-conditioned predictor
(Version_3/vjepa2/src/models/ac_predictor.py) to a 1-D TEMPORAL patient-state sequence
instead of a 3-D video token grid:

  - input  : per-timestep state embeddings z_t  (from CLMBR encoder), shape [B, T, D]
  - action : per-timestep intervention vector a_t, shape [B, T, A]  (e.g. one-hot family +
             dose/flow features) — the "arm" applied at each step
  - the predictor prepends an action token to each timestep, runs a TIME-CAUSAL transformer,
    and predicts the next-step latent  z_{t+1}. Autoregressive rollout under a chosen action
    sequence = "simulate the counterfactual future under this intervention."

Objective (JEPA, from vjepa2/app/vjepa_droid/train.py): teacher-student feature regression
between predicted and (EMA-teacher) target latents, summed over teacher-forced + rollout.

STATUS: SCAFFOLD, cluster-trainable (needs torch). Small enough to train standalone; on the
cluster you may instead import vjepa2's VisionTransformerPredictorAC with a 1-D mask.
"""
from __future__ import annotations

import copy

import torch
import torch.nn as nn


class ActionConditionedWorldModel(nn.Module):
    def __init__(self, state_dim: int = 768, action_dim: int = 8, hidden: int = 512,
                 depth: int = 6, heads: int = 8, mlp_ratio: float = 4.0):
        super().__init__()
        self.state_in = nn.Linear(state_dim, hidden)
        self.action_in = nn.Linear(action_dim, hidden)         # action token per timestep
        self.pos = nn.Embedding(4096, hidden)                  # 1-D temporal positions
        layer = nn.TransformerEncoderLayer(hidden, heads, int(hidden * mlp_ratio),
                                           batch_first=True, activation="gelu")
        self.blocks = nn.TransformerEncoder(layer, depth)
        self.state_out = nn.Linear(hidden, state_dim)          # predict next-step latent

    @staticmethod
    def _causal_mask(n, device):
        # each token attends to itself + earlier tokens (time-causal)
        return torch.triu(torch.full((n, n), float("-inf"), device=device), diagonal=1)

    def forward(self, states: torch.Tensor, actions: torch.Tensor) -> torch.Tensor:
        """states [B,T,D], actions [B,T,A] -> predicted next-state latents [B,T,D].
        Interleave [action_t, state_t] per timestep, causal-attend, read state slots."""
        B, T, _ = states.shape
        s = self.state_in(states)
        a = self.action_in(actions)
        tok = torch.stack([a, s], dim=2).reshape(B, 2 * T, -1)          # [B, 2T, H]
        idx = torch.arange(2 * T, device=states.device)
        tok = tok + self.pos(idx)[None]
        tok = self.blocks(tok, mask=self._causal_mask(2 * T, states.device))
        s_hat = tok[:, 1::2, :]                                          # state slots
        return self.state_out(s_hat)                                    # predicted z_{t+1}

    @torch.no_grad()
    def rollout(self, z0: torch.Tensor, action_seq: torch.Tensor) -> torch.Tensor:
        """Autoregressive counterfactual rollout: from state z0 [B,1,D], apply the action
        sequence [B,K,A] step by step, returning predicted latents [B,K,D]."""
        self.eval()
        states = z0
        outs = []
        for t in range(action_seq.shape[1]):
            acts = action_seq[:, : t + 1, :]
            pred = self.forward(states, acts)[:, -1:, :]                # next latent
            outs.append(pred)
            states = torch.cat([states, pred], dim=1)
        return torch.cat(outs, dim=1)


class EMATeacher:
    """EMA copy of a module (no grad) — the JEPA target encoder/predictor."""
    def __init__(self, model: nn.Module, momentum: float = 0.998):
        self.teacher = copy.deepcopy(model)
        for p in self.teacher.parameters():
            p.requires_grad_(False)
        self.m = momentum

    @torch.no_grad()
    def update(self, model: nn.Module):
        for tp, p in zip(self.teacher.parameters(), model.parameters()):
            tp.mul_(self.m).add_(p, alpha=1 - self.m)


def jepa_loss(pred: torch.Tensor, target: torch.Tensor, exp: float = 1.0) -> torch.Tensor:
    """Feature-regression loss (vjepa2): mean |pred - target|^exp / exp."""
    return torch.mean(torch.abs(pred - target) ** exp) / exp


ACTION_FAMILIES = ["none", "dialysis", "transfusion", "ventilation"]   # one-hot + extra feats


def build_action_vector(family: str, extra: list[float] | None = None, action_dim: int = 8):
    v = [0.0] * action_dim
    if family in ACTION_FAMILIES:
        v[ACTION_FAMILIES.index(family)] = 1.0
    for i, x in enumerate(extra or []):
        if 4 + i < action_dim:
            v[4 + i] = float(x)
    return v


if __name__ == "__main__":
    m = ActionConditionedWorldModel()
    B, T, D, A = 2, 5, 768, 8
    z = torch.randn(B, T, D); acts = torch.randn(B, T, A)
    pred = m(z, acts)
    roll = m.rollout(z[:, :1, :], acts)
    print("world model OK — pred", tuple(pred.shape), "rollout", tuple(roll.shape),
          "params", sum(p.numel() for p in m.parameters()))
