"""Stage 5 (engine) — trajectory rollout in the learned latent world model.

Given an initial state s_0 and an intervention sequence [a_0, ..., a_{T-1}] (with optional Δt per
step), roll the world model forward to produce [s_0, s_1, ..., s_T]. Supports branching rollouts
and counterfactual-pair comparison (same s_0, different action sequences).

CAVEAT: rollouts are *learned simulations from observational data*, not validated counterfactuals.
"""
from __future__ import annotations

from typing import List, Optional, Sequence

import torch

from models.world_model import WorldModel


class Simulator:
    def __init__(self, world_model: WorldModel, default_dt: float = 24.0, device: str = "cpu"):
        self.wm = world_model.to(device).eval()
        self.device = device
        self.default_dt = default_dt

    def _dt(self, dt, T):
        if dt is None:
            return [self.default_dt] * T
        if isinstance(dt, (int, float)):
            return [float(dt)] * T
        return list(dt)

    @torch.no_grad()
    def rollout(self, s0: torch.Tensor, actions: Sequence[int],
                dt: Optional[Sequence[float]] = None, sample: bool = False) -> torch.Tensor:
        """Single rollout. Returns states [T+1, latent_dim] including s0."""
        s = s0.to(self.device).float().view(-1)
        dts = self._dt(dt, len(actions))
        traj = [s]
        for a, d in zip(actions, dts):
            a_t = torch.tensor([int(a)], device=self.device)
            d_t = torch.tensor([float(d)], device=self.device)
            s = self.wm.step(s.unsqueeze(0), a_t, d_t, sample=sample).view(-1)
            traj.append(s)
        return torch.stack(traj)

    @torch.no_grad()
    def branch(self, s0: torch.Tensor, action_options: List[Sequence[int]],
               dt: Optional[Sequence[float]] = None, sample: bool = False) -> List[torch.Tensor]:
        """Branching simulation: one rollout per action sequence from the SAME s0."""
        return [self.rollout(s0, acts, dt=dt, sample=sample) for acts in action_options]

    @torch.no_grad()
    def counterfactual_pair(self, s0: torch.Tensor, actions_a: Sequence[int],
                            actions_b: Sequence[int], dt: Optional[Sequence[float]] = None,
                            sample: bool = False):
        """Two rollouts from the same s0 under different interventions (e.g. PCI vs CABG)."""
        ta = self.rollout(s0, actions_a, dt=dt, sample=sample)
        tb = self.rollout(s0, actions_b, dt=dt, sample=sample)
        return ta, tb


def constant_action_seq(action_id: int, horizon: int) -> List[int]:
    return [int(action_id)] * horizon
