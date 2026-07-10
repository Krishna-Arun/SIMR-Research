"""Deconfounding components for counterfactual dynamics.

Turns the conditional dynamics model E[s_{t+1} | s_t, a_t] into a *counterfactual* estimate
E[s_{t+1} | s_t, do(a_t)] under sequential ignorability (treatment ⫫ potential next-state | s_t),
using two standard, complementary mechanisms:

  * Stabilized IPW  — reweight transitions by  P(a) / P(a | s_t)  so the effective action
                      distribution is marginal (as if randomized given s_t). Corrects the biased
                      (state, action) sampling of observational data.
  * Adversarial balancing (CRN-style) — a gradient-reversal treatment classifier on a learned
                      adapter of s_t, pushing the dynamics input to be treatment-INVARIANT
                      (removes the history↔treatment association that drives confounding bias).

DIAGNOSTIC (this is where the foundation-model question lives): `treatment_predictability` measures
how well treatment can be predicted from the state. A frozen CLMBR state is pretrained for
next-event prediction and is therefore *intentionally* treatment-predictive and cannot be retrained
to be balanced — so balancing must happen in the adapter, and the residual predictability quantifies
how much confounding the frozen representation still carries. (See CRN, Bica 2020; FAST-Q 2025.)

These mechanisms are established; the contribution here is empirical (frozen CLMBR vs GRU) — not a
new algorithm. Caveat: ignorability/overlap are untestable on observational data; deconfounding
reduces but cannot certify removal of bias.
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


# --- gradient reversal (DANN) ---------------------------------------------------------------
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


# --- propensity model  π(a | s)  ------------------------------------------------------------
class PropensityNet(nn.Module):
    def __init__(self, latent_dim: int, n_actions: int, hidden: int = 256):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(latent_dim, hidden), nn.ReLU(),
                                 nn.Linear(hidden, n_actions))

    def forward(self, s):
        return self.net(s)


def fit_propensity(states: torch.Tensor, actions: torch.Tensor, n_actions: int,
                   device: str, epochs: int = 30, lr: float = 1e-3) -> PropensityNet:
    model = PropensityNet(states.shape[1], n_actions).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    S, A = states.to(device), actions.to(device)
    bs = 4096
    for _ in range(epochs):
        perm = torch.randperm(len(S), device=device)
        for i in range(0, len(S), bs):
            idx = perm[i:i + bs]
            loss = F.cross_entropy(model(S[idx]), A[idx])
            opt.zero_grad(); loss.backward(); opt.step()
    return model


@torch.no_grad()
def stabilized_ipw(prop: PropensityNet, states: torch.Tensor, actions: torch.Tensor,
                   n_actions: int, device: str, clip: float = 10.0) -> torch.Tensor:
    """w_i = P(a_i) / P(a_i | s_i), clipped to [1/clip, clip] and normalized to mean 1."""
    S, A = states.to(device), actions.to(device)
    marginal = torch.bincount(A, minlength=n_actions).float()
    marginal = (marginal / marginal.sum()).clamp(min=1e-6)
    probs = F.softmax(prop(S), dim=-1).clamp(min=1e-6)
    p_a_given_s = probs.gather(1, A.view(-1, 1)).squeeze(1)
    w = marginal[A] / p_a_given_s
    w = w.clamp(1.0 / clip, clip)
    w = w / w.mean()
    return w.cpu()


def treatment_predictability(states: torch.Tensor, actions: torch.Tensor, n_actions: int,
                             device: str, epochs: int = 30) -> dict:
    """Train a fresh probe to predict treatment from the (possibly balanced) state.

    Reports top-1 accuracy vs the majority-class baseline. Lower-than-trivial separation ⇒ the
    representation is balanced (treatment-invariant). This is the deconfounding diagnostic.
    """
    probe = fit_propensity(states, actions, n_actions, device, epochs=epochs)
    with torch.no_grad():
        pred = probe(states.to(device)).argmax(-1).cpu()
    acc = float((pred == actions).float().mean())
    majority = float(torch.bincount(actions, minlength=n_actions).max()) / len(actions)
    return {"probe_accuracy": round(acc, 4), "majority_baseline": round(majority, 4),
            "excess_over_majority": round(acc - majority, 4)}
