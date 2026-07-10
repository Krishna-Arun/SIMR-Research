#!/usr/bin/env python3
"""
Readout heads — decode a predicted world-model latent into INTERPRETABLE predictions
that the LLM can use. This is what makes simulate() useful (vs an opaque embedding).

Given a predicted future latent z_hat [B, D] (from world_model.rollout), produce:
  - per-core-lab direction logits (Rising / Falling / Stable) + a value estimate
  - an outcome-risk head (mortality_1y, readmission_30d) probabilities

STATUS: SCAFFOLD, cluster-trained jointly with (or on top of) the world model. Lab heads
are keyed by a fixed core-lab vocabulary built from the cohort.
"""
from __future__ import annotations

import torch
import torch.nn as nn

DIRECTIONS = ["Rising", "Falling", "Stable"]


class ReadoutHeads(nn.Module):
    def __init__(self, state_dim: int = 768, core_labs: list[str] | None = None):
        super().__init__()
        self.core_labs = core_labs or []
        self.lab_index = {l: i for i, l in enumerate(self.core_labs)}
        n = max(len(self.core_labs), 1)
        self.direction = nn.Linear(state_dim, n * 3)      # 3-way per lab
        self.value = nn.Linear(state_dim, n)              # regressed post value (z-scored)
        self.mortality = nn.Linear(state_dim, 1)
        self.readmission = nn.Linear(state_dim, 1)

    def forward(self, z_hat: torch.Tensor) -> dict:
        n = max(len(self.core_labs), 1)
        return {"direction_logits": self.direction(z_hat).view(-1, n, 3),
                "value": self.value(z_hat),
                "mortality_risk": torch.sigmoid(self.mortality(z_hat)).squeeze(-1),
                "readmission_risk": torch.sigmoid(self.readmission(z_hat)).squeeze(-1)}

    @torch.no_grad()
    def decode(self, z_hat: torch.Tensor) -> dict:
        """Human-readable prediction for the simulate() tool (single example)."""
        out = self.forward(z_hat.unsqueeze(0) if z_hat.dim() == 1 else z_hat)
        dirs = out["direction_logits"][0].argmax(-1).tolist()
        labs = {self.core_labs[i]: DIRECTIONS[d] for i, d in enumerate(dirs)} if self.core_labs else {}
        return {"predicted_lab_directions": labs,
                "mortality_1y_risk": round(float(out["mortality_risk"][0]), 3),
                "readmission_30d_risk": round(float(out["readmission_risk"][0]), 3)}


if __name__ == "__main__":
    heads = ReadoutHeads(core_labs=["Creatinine", "Potassium", "Hemoglobin"])
    z = torch.randn(768)
    print("readout OK —", heads.decode(z))
