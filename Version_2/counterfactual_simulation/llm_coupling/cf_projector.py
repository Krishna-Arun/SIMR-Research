"""cf_projector.py — Route B: WorldModelProjector maps world-model latents into an LLM's embedding
space as a short, role-tagged sequence of virtual tokens (LLaVA/soft-prompt style).

Token 'sentence' (variable length, k<=16):
  [WM_BEGIN] [Z_now] [Z_hist ...] [CF_factual] [CF_notreat] [CF_alt] [CF_toggle x<=2] [WM_END]

- state stream  P_z    : 768         -> H   (z_now + history factual latents)
- rollout stream P_roll: 1536(mean++std) -> H   (per-candidate MC endpoint distribution)
- role embeddings tag each token (begin/now/hist/cf_*/end) so position is not load-bearing
- outputs are RMS-matched to the LLM token-embedding scale so a FROZEN LLM will attend to them

Only this module + LoRA are trained; the LLM backbone is frozen (arm 2b projector-only; arm 3b +LoRA).
"""
from __future__ import annotations

import torch
import torch.nn as nn

# role ids
R_BEGIN, R_NOW, R_HIST, R_CF_FACT, R_CF_NOTREAT, R_CF_ALT, R_CF_TOGGLE, R_END = range(8)
N_ROLES = 8
MAX_TOGGLES = 2
Z_DIM = 768
CF_DIM = 2 * Z_DIM  # mean ++ std


def _cf_role(name: str) -> int:
    if name == "factual":
        return R_CF_FACT
    if name == "no_treatment":
        return R_CF_NOTREAT
    if name.startswith("alt_arm"):
        return R_CF_ALT
    return R_CF_TOGGLE


class WorldModelProjector(nn.Module):
    def __init__(self, hidden: int, hist: int = 3, target_rms: float = 1.0):
        super().__init__()
        self.hidden = hidden
        self.hist = hist
        self.register_buffer("target_rms", torch.tensor(float(target_rms)))
        self.p_z = nn.Sequential(nn.Linear(Z_DIM, 2048), nn.GELU(), nn.LayerNorm(2048),
                                 nn.Linear(2048, hidden))
        self.p_roll = nn.Sequential(nn.Linear(CF_DIM, 2048), nn.GELU(), nn.LayerNorm(2048),
                                    nn.Linear(2048, hidden))
        self.role = nn.Embedding(N_ROLES, hidden)
        self.begin = nn.Parameter(torch.randn(hidden) * 0.02)
        self.end = nn.Parameter(torch.randn(hidden) * 0.02)

    def set_target_rms(self, rms: float):
        self.target_rms.fill_(float(rms))

    def _scale(self, x):
        # match the LLM embedding RMS so injected tokens live at the right magnitude
        cur = x.pow(2).mean(-1, keepdim=True).clamp_min(1e-8).sqrt()
        return x * (self.target_rms / cur)

    def encode_one(self, pack: dict, device=None) -> "tuple[torch.Tensor, torch.Tensor]":
        """pack: {z_now[768], z_hist[m,768], cf:{name:[1536]}} (numpy or tensors).
        Returns (emb[k,H], role_ids[k])."""
        dev = device or self.role.weight.device
        dt = self.role.weight.dtype

        def T(a):
            return torch.as_tensor(a, dtype=dt, device=dev)

        embs, roles = [], []
        # BEGIN
        embs.append(self.begin);            roles.append(R_BEGIN)
        # now
        embs.append(self.p_z(T(pack["z_now"])));  roles.append(R_NOW)
        # history (oldest -> newest), capped
        zh = pack.get("z_hist")
        if zh is not None and len(zh) > 0:
            zh = T(zh)[-self.hist:]
            for row in zh:
                embs.append(self.p_z(row)); roles.append(R_HIST)
        # candidate rollouts (fixed priority order; toggles capped)
        cf = pack["cf"]
        ordered = [n for n in ("factual", "no_treatment") if n in cf]
        ordered += [n for n in cf if n.startswith("alt_arm")]
        toggles = [n for n in cf if n not in ordered and (n.startswith("remove_") or n.startswith("add_"))]
        ordered += toggles[:MAX_TOGGLES]
        for name in ordered:
            embs.append(self.p_roll(T(cf[name]))); roles.append(_cf_role(name))
        # END
        embs.append(self.end);              roles.append(R_END)

        emb = torch.stack(embs, 0)                       # [k,H]
        role_ids = torch.tensor(roles, device=dev)
        emb = emb + self.role(role_ids)
        emb = self._scale(emb)
        return emb, role_ids

    def encode_batch(self, packs: list, device=None):
        """Returns list of (emb[k_i,H], role_ids[k_i]); the model handles padding/concatenation."""
        return [self.encode_one(p, device=device) for p in packs]
