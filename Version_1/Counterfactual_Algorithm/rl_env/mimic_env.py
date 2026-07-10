"""Stage 6 — Gym-style environment wrapping the learned latent world model.

    obs = env.reset()                         -> s_0  (a real patient's initial encoded state)
    obs, reward, done, info = env.step(a)     -> latent dynamics step + proxy reward

State  = latent s_t (shape [latent_dim]).
Action = intervention id from the grouped ActionVocab.
Reward = proxy clinical outcome decoded from the (simulated) next state:
         survival proxy (1 - p_mortality)  - ICU-admission proxy  - length-of-stay proxy.

############################################################################################
# IMPORTANT: This is OFFLINE RL in a LEARNED SIMULATOR built from observational data.       #
# It is a research environment for studying policy learning under model error — NOT a       #
# clinical decision tool, and the reward is a coarse proxy, not a validated outcome model.  #
############################################################################################
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import torch

from models.world_model import WorldModel
from models.decoder import OutcomeDecoder
from preprocessing.actions import ActionVocab


class MimicLatentEnv:
    def __init__(self, world_model: WorldModel, decoder: OutcomeDecoder,
                 initial_states: np.ndarray, cfg: dict, device: str = "cpu",
                 default_dt: float = 24.0, seed: int = 0):
        self.wm = world_model.to(device).eval()
        self.dec = decoder.to(device).eval()
        self.S0 = np.asarray(initial_states, dtype=np.float32)
        self.vocab = ActionVocab()
        self.n_actions = self.vocab.n_actions
        self.latent_dim = self.S0.shape[1]
        self.device = device
        self.default_dt = default_dt
        self.max_steps = cfg["simulation"]["max_steps"]
        self.gamma = cfg["rl"]["gamma"]
        self.rng = np.random.RandomState(seed)
        self.s = None
        self.t = 0

    # ---- Gym-style API ----
    def reset(self, idx: Optional[int] = None) -> np.ndarray:
        i = self.rng.randint(len(self.S0)) if idx is None else idx
        self.s = torch.tensor(self.S0[i], device=self.device).float()
        self.t = 0
        return self.s.detach().cpu().numpy()

    @torch.no_grad()
    def step(self, action: int):
        a = torch.tensor([int(action)], device=self.device)
        dt = torch.tensor([self.default_dt], device=self.device)
        self.s = self.wm.step(self.s.unsqueeze(0), a, dt, sample=False).view(-1)
        self.t += 1
        reward = self._reward(self.s)
        done = self.t >= self.max_steps
        info = {"t": self.t, "outcome": self._decode(self.s)}
        return self.s.detach().cpu().numpy(), reward, done, info

    # ---- reward / decoding ----
    def _decode(self, s: torch.Tensor) -> dict:
        p = self.dec.predict(s)
        return {k: float(v) for k, v in p.items()}

    def _reward(self, s: torch.Tensor) -> float:
        o = self._decode(s)
        survival = 1.0 - o["mortality"]            # survival proxy
        return float(survival - 0.5 * o["icu"] - 0.1 * max(o["los_norm"], 0.0))

    # convenience
    @property
    def observation_dim(self) -> int:
        return self.latent_dim
