"""Decoder / outcome probe — maps a latent state s_t to observable proxy outcomes.

Used by (a) the benchmark, to measure *decoded outcome divergence* between counterfactual rollouts,
and (b) the RL environment, to compute the proxy reward. Outcomes are coarse research proxies
derived in Stage 1 (`outcomes` dict): in-hospital mortality, ICU admission, length-of-stay.

This is a linear/MLP probe on the (frozen-at-RL-time) latent space — NOT a calibrated clinical
predictor.
"""
from __future__ import annotations

import torch
import torch.nn as nn

# Proxy outcome channels decoded from a state.
OUTCOME_KEYS = ["mortality", "icu", "los_norm"]   # 2 binary logits + 1 regression


class OutcomeDecoder(nn.Module):
    def __init__(self, latent_dim: int, hidden_dim: int = 128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(latent_dim, hidden_dim), nn.ReLU(),
            nn.Linear(hidden_dim, len(OUTCOME_KEYS)),
        )

    def forward(self, s: torch.Tensor) -> torch.Tensor:
        return self.net(s)                          # [..., 3]: mortality_logit, icu_logit, los_norm

    def predict(self, s: torch.Tensor) -> dict:
        out = self.forward(s)
        return {
            "mortality": torch.sigmoid(out[..., 0]),
            "icu": torch.sigmoid(out[..., 1]),
            "los_norm": out[..., 2],
        }


def outcome_targets(outcomes: dict) -> torch.Tensor:
    """Map a Stage-1 outcomes dict -> target vector [mortality, icu, los_norm]."""
    icu = 1.0 if outcomes.get("n_icu_stays", 0) > 0 else 0.0
    los = float(outcomes.get("max_los_days", 0.0))
    los_norm = los / 10.0                           # ~O(1) scaling; LOS in days
    return torch.tensor([float(outcomes.get("mortality", 0)), icu, los_norm], dtype=torch.float32)
