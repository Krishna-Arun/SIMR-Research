"""Stage 4 (core) — intervention-conditioned latent dynamics.

    s_{t+1} = f(s_t, a_t, Δt)

Predicts a residual Δs (s_{t+1} = s_t + Δs), which stabilizes multi-step rollouts. Three heads
behind one module:

  * deterministic : MLP -> Δs.                         (default; trains today)
  * gaussian      : MLP -> (Δs mean, log-var); NLL.    (stochastic; trains today)
  * mdn           : mixture-density head.              (scaffold — structure only)

CAVEAT: this is a learned dynamics model fit to observational transitions. It does NOT recover
true causal effects; rollouts are simulations conditioned on the action embedding, to be judged on
stability/consistency, not clinical validity.
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from models.deconfound import grad_reverse


def dt_features(dt_hours: torch.Tensor) -> torch.Tensor:
    """Cheap, bounded time-gap features from Δt in hours."""
    dt = dt_hours.clamp(min=0).float()
    return torch.stack([torch.log1p(dt), (dt / 24.0).clamp(max=30.0)], dim=-1)


class WorldModel(nn.Module):
    def __init__(self, latent_dim: int, n_actions: int, cfg: dict):
        super().__init__()
        wm = cfg["world_model"]
        self.kind = wm["kind"]
        self.latent_dim = latent_dim
        a_dim = wm["action_embed_dim"]
        d_dim = wm["dt_embed_dim"]
        self.action_emb = nn.Embedding(n_actions, a_dim)
        self.dt_proj = nn.Sequential(nn.Linear(2, d_dim), nn.ReLU())

        # Optional CRN-style balancing adapter (deconfounding). Off by default => identical to the
        # plain conditional dynamics model, so prior runs are unaffected.
        dc = cfg.get("deconfound", {}) or {}
        self.balance = bool(dc.get("enabled", False))
        self.adv_lambda = float(dc.get("adv_lambda", 0.5))
        if self.balance:
            bdim = int(dc.get("balance_dim", 128))
            self.adapter = nn.Sequential(nn.Linear(latent_dim, bdim), nn.ReLU())
            self.treat_head = nn.Linear(bdim, n_actions)   # adversary (via gradient reversal)
            state_in = bdim
        else:
            state_in = latent_dim

        in_dim = state_in + a_dim + d_dim
        layers, h = [], wm["hidden_dim"]
        d = in_dim
        for _ in range(wm["num_layers"]):
            layers += [nn.Linear(d, h), nn.LayerNorm(h), nn.ReLU()]
            d = h
        self.trunk = nn.Sequential(*layers)

        if self.kind == "deterministic":
            self.head = nn.Linear(h, latent_dim)
        elif self.kind == "gaussian":
            self.head_mu = nn.Linear(h, latent_dim)
            self.head_logvar = nn.Linear(h, latent_dim)
        elif self.kind == "mdn":
            self.K = wm.get("mdn_components", 5)
            self.head_pi = nn.Linear(h, self.K)
            self.head_mu = nn.Linear(h, self.K * latent_dim)
            self.head_logvar = nn.Linear(h, self.K * latent_dim)
        else:
            raise ValueError(f"unknown world_model.kind={self.kind!r}")

    def _state_rep(self, s):
        """Balanced adapter output if deconfounding, else the raw state."""
        return self.adapter(s) if self.balance else s

    def _trunk(self, s, a, dt):
        z = self._state_rep(s)
        x = torch.cat([z, self.action_emb(a), self.dt_proj(dt_features(dt))], dim=-1)
        return self.trunk(x)

    def balance_loss(self, s, a):
        """Adversarial (gradient-reversed) treatment-classification loss on the adapter.

        Minimizing total = dynamics_loss + adv_lambda * balance_loss pushes the adapter to be
        treatment-INVARIANT while the classifier still tries to predict treatment. Returns 0 if
        deconfounding is disabled.
        """
        if not self.balance:
            return torch.zeros((), device=s.device)
        z = grad_reverse(self.adapter(s), self.adv_lambda)
        return F.cross_entropy(self.treat_head(z), a)

    def forward(self, s, a, dt):
        """Return predicted next state (mean). Deterministic for det/gaussian; mean-of-mixture for mdn."""
        z = self._trunk(s, a, dt)
        if self.kind == "deterministic":
            return s + self.head(z)
        if self.kind == "gaussian":
            return s + self.head_mu(z)
        if self.kind == "mdn":
            pi = F.softmax(self.head_pi(z), dim=-1)              # [B,K]
            mu = self.head_mu(z).view(-1, self.K, self.latent_dim)
            return s + (pi.unsqueeze(-1) * mu).sum(dim=1)

    def loss(self, s, a, dt, s_next, weight=None):
        """Training loss for the configured head. ``weight`` (per-sample, e.g. stabilized IPW)
        reweights transitions so the dynamics are fit as if treatment were randomized given s_t."""
        z = self._trunk(s, a, dt)
        target = s_next - s                                       # residual

        def _reduce(per_sample):                                  # per_sample: [B]
            if weight is None:
                return per_sample.mean()
            w = weight.to(per_sample.device)
            return (per_sample * w).sum() / w.sum()

        if self.kind == "deterministic":
            per = ((self.head(z) - target) ** 2).mean(dim=-1)
            return _reduce(per)
        if self.kind == "gaussian":
            mu, logvar = self.head_mu(z), self.head_logvar(z).clamp(-8, 8)
            per = (0.5 * (logvar + (target - mu) ** 2 / logvar.exp())).mean(dim=-1)
            return _reduce(per)
        if self.kind == "mdn":
            pi = F.log_softmax(self.head_pi(z), dim=-1)            # [B,K]
            mu = self.head_mu(z).view(-1, self.K, self.latent_dim)
            logvar = self.head_logvar(z).view(-1, self.K, self.latent_dim).clamp(-8, 8)
            t = target.unsqueeze(1)                                # [B,1,D]
            comp = -0.5 * (logvar + (t - mu) ** 2 / logvar.exp()).sum(-1)  # [B,K]
            per = -torch.logsumexp(pi + comp, dim=-1)
            return _reduce(per)

    @torch.no_grad()
    def step(self, s, a, dt, sample: bool = False):
        """One simulation step. If sample=True and head is stochastic, draw from the predictive dist."""
        z = self._trunk(s, a, dt)
        if self.kind == "deterministic" or not sample:
            return self.forward(s, a, dt)
        if self.kind == "gaussian":
            mu, logvar = self.head_mu(z), self.head_logvar(z).clamp(-8, 8)
            eps = torch.randn_like(mu)
            return s + mu + eps * (0.5 * logvar).exp()
        if self.kind == "mdn":
            pi = F.softmax(self.head_pi(z), dim=-1)
            k = torch.multinomial(pi, 1).squeeze(-1)
            mu = self.head_mu(z).view(-1, self.K, self.latent_dim)
            logvar = self.head_logvar(z).view(-1, self.K, self.latent_dim).clamp(-8, 8)
            idx = k.view(-1, 1, 1).expand(-1, 1, self.latent_dim)
            mu_k = mu.gather(1, idx).squeeze(1)
            lv_k = logvar.gather(1, idx).squeeze(1)
            return s + mu_k + torch.randn_like(mu_k) * (0.5 * lv_k).exp()
