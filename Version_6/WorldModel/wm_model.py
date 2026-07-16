#!/usr/bin/env python3
"""
V6 hourly encoder + action-conditioned lab predictor -- ESSENTIALS ONLY.

  TokenEncoder : grid [B,H,C,4] (+active mask, +static) -> patient state z [B,d]
  WorldModel   : z --FiLM(action)--> trunk --> post-window lab prediction [B,n_labs]

No CRN adversary, no IPW, no matched-contrast, no GRU-D decay -- just the encoder,
the action conditioning, and the lab head.
"""
import copy
import torch
import torch.nn as nn


class HourlyEncoder(nn.Module):
    def __init__(self, C, n_static, d=128, feat=4, gru_layers=2, dropout=0.1, H=48):
        super().__init__()
        self.channel_emb = nn.Embedding(C, d)          # learned per-channel identity
        self.feat_proj = nn.Linear(feat, d)            # learned projection of cell features
        self.pos_emb = nn.Embedding(H, d)              # learned hour position
        self.norm_hour = nn.LayerNorm(d)
        self.gru = nn.GRU(d, d, num_layers=gru_layers, batch_first=True,
                          dropout=dropout if gru_layers > 1 else 0.0)
        self.static_mlp = nn.Sequential(nn.Linear(n_static, d), nn.GELU())
        self.norm_out = nn.LayerNorm(d)
        self.d, self.C, self.H = d, C, H

    def forward(self, grid, active, static):
        # grid [B,H,C,4]  active [B,H,C]  static [B,n_static]
        B, H, C, _ = grid.shape
        cell = self.feat_proj(grid) + self.channel_emb.weight[None, None]      # [B,H,C,d]
        cell = cell * active.unsqueeze(-1)
        s = cell.sum(dim=2) / active.sum(dim=2, keepdim=True).clamp(min=1.0)   # masked mean -> [B,H,d]
        s = self.norm_hour(s + self.pos_emb.weight[None, :H])
        out, _ = self.gru(s)                                                   # [B,H,d]
        z = out[:, -1] + self.static_mlp(static)
        return self.norm_out(z)


class WorldModel(nn.Module):
    """Encode pre-anchor state -> z; FiLM(action) sets the anchor hidden state; a decoder
    GRU rolls forward post_h hours, decoding the labs each hour. The recurrence h_t->h_{t+1}
    is the transition function you unroll for multi-step counterfactual rollout.
    Output: [B, post_h, n_labs] standardized hourly trajectory."""
    def __init__(self, C, n_static, n_labs=4, action_dim=4, d=128, dropout=0.1, H=48, post_h=72):
        super().__init__()
        self.encoder = HourlyEncoder(C, n_static, d=d, dropout=dropout, H=H)
        self.film = nn.Linear(action_dim, 2 * d)
        nn.init.zeros_(self.film.weight); nn.init.zeros_(self.film.bias)       # start as identity
        self.action_proj = nn.Linear(action_dim, d)       # action drives each decoder step
        self.pos_emb = nn.Embedding(post_h, d)            # which post-hour we're decoding
        self.decoder = nn.GRU(d, d, batch_first=True)     # the hourly transition function
        self.head = nn.Sequential(nn.LayerNorm(d), nn.GELU(), nn.Dropout(dropout),
                                  nn.Linear(d, n_labs))
        self.d, self.post_h = d, post_h

    def forward(self, grid, active, static, action):
        z = self.encoder(grid, active, static)                              # [B, d]
        gamma, beta = self.film(action).chunk(2, dim=-1)
        h0 = ((1.0 + gamma) * z + beta).unsqueeze(0).contiguous()           # [1, B, d] anchor state
        steps = self.action_proj(action).unsqueeze(1) + self.pos_emb.weight[None, :self.post_h]  # [B, post_h, d]
        out, _ = self.decoder(steps, h0)                                    # [B, post_h, d]
        return self.head(out)                                               # [B, post_h, n_labs]


class LatentWorldModel(nn.Module):
    """LATENT variant: evolve a richer latent state autoregressively under the action
    (s_{t+1} = GRUCell(action, s_t) + residual dynamics), decode observables each step.
    The state carries the rollout in latent space (no positional crutch) and is larger /
    more expressive than the observable decoder -- 'evolve the state to make it complex'."""
    def __init__(self, C, n_static, n_labs=4, action_dim=4, d=128, d_lat=192, dropout=0.1, H=48, post_h=72):
        super().__init__()
        self.encoder = HourlyEncoder(C, n_static, d=d, dropout=dropout, H=H)
        self.to_lat = nn.Linear(d, d_lat)
        self.film = nn.Linear(action_dim, 2 * d_lat)
        nn.init.zeros_(self.film.weight); nn.init.zeros_(self.film.bias)
        self.act_emb = nn.Linear(action_dim, d_lat)
        self.cell = nn.GRUCell(d_lat, d_lat)                                # latent transition
        self.dyn = nn.Sequential(nn.Linear(d_lat, d_lat), nn.LayerNorm(d_lat), nn.GELU(),
                                 nn.Dropout(dropout), nn.Linear(d_lat, d_lat))
        self.norm = nn.LayerNorm(d_lat)
        self.head = nn.Sequential(nn.LayerNorm(d_lat), nn.GELU(), nn.Dropout(dropout),
                                  nn.Linear(d_lat, n_labs))
        self.post_h = post_h

    def forward(self, grid, active, static, action):
        z = self.encoder(grid, active, static)
        s = self.to_lat(z)
        gamma, beta = self.film(action).chunk(2, dim=-1)
        s = (1.0 + gamma) * s + beta                                        # anchor latent
        a = self.act_emb(action)
        preds = []
        for _ in range(self.post_h):
            s = self.cell(a, s)                                             # evolve latent under action
            s = self.norm(s + self.dyn(s))                                  # residual richer dynamics
            preds.append(self.head(s))
        return torch.stack(preds, dim=1)                                    # [B, post_h, n_labs]


class JepaAC(nn.Module):
    """Full action-conditioned JEPA (adapted from V3 world_model.py).

    - context encoder (grid) -> anchor latent
    - action-conditioned latent rollout predicts, for each post-hour, the TARGET latent
      of that hour's observation
    - target latents come from an EMA target encoder over the observed labs (stop-grad)
    - anti-collapse: an online obs-encoder + decoder autoencoder grounds the latent space;
      EMA + stop-grad on the target (BYOL/JEPA style)
    - a shared decoder reads any latent -> labs, so the predicted-latent rollout is decodable
      to observables for the SAME eval metrics as the other models.
    """
    def __init__(self, C, n_static, n_labs=4, action_dim=4, d=128, d_lat=192,
                 dropout=0.1, H=48, post_h=72, ema_m=0.99):
        super().__init__()
        self.context = HourlyEncoder(C, n_static, d=d, dropout=dropout, H=H)
        self.to_lat = nn.Linear(d, d_lat)
        self.film = nn.Linear(action_dim, 2 * d_lat)
        nn.init.zeros_(self.film.weight); nn.init.zeros_(self.film.bias)
        self.act_emb = nn.Linear(action_dim, d_lat)
        self.cell = nn.GRUCell(d_lat, d_lat)
        self.dyn = nn.Sequential(nn.Linear(d_lat, d_lat), nn.LayerNorm(d_lat), nn.GELU(),
                                 nn.Dropout(dropout), nn.Linear(d_lat, d_lat))
        self.norm = nn.LayerNorm(d_lat)
        self.pred_head = nn.Linear(d_lat, d_lat)                 # predicted target latent
        self.obs_enc = nn.Sequential(nn.Linear(n_labs * 2, d_lat), nn.GELU(), nn.Linear(d_lat, d_lat))
        self.obs_dec = nn.Sequential(nn.LayerNorm(d_lat), nn.GELU(), nn.Linear(d_lat, n_labs))
        self.obs_enc_ema = copy.deepcopy(self.obs_enc)
        for p in self.obs_enc_ema.parameters():
            p.requires_grad_(False)
        self.ema_m, self.post_h, self.n_labs = ema_m, post_h, n_labs

    def rollout_latents(self, grid, active, static, action):
        z = self.context(grid, active, static)
        s = self.to_lat(z)
        gamma, beta = self.film(action).chunk(2, dim=-1)
        s = (1.0 + gamma) * s + beta
        a = self.act_emb(action)
        lat = []
        for _ in range(self.post_h):
            s = self.cell(a, s)
            s = self.norm(s + self.dyn(s))
            lat.append(self.pred_head(s))
        return torch.stack(lat, dim=1)                          # [B, post_h, d_lat]

    def forward(self, grid, active, static, action):
        return self.obs_dec(self.rollout_latents(grid, active, static, action))   # [B, post_h, n_labs]

    def obs_target(self, labs, mask):                           # EMA target latent (stop-grad)
        with torch.no_grad():
            return self.obs_enc_ema(torch.cat([labs, mask], dim=-1))

    def obs_online(self, labs, mask):                           # online latent + reconstruction
        e = self.obs_enc(torch.cat([labs, mask], dim=-1))
        return e, self.obs_dec(e)

    @torch.no_grad()
    def ema_update(self):
        for tp, p in zip(self.obs_enc_ema.parameters(), self.obs_enc.parameters()):
            tp.mul_(self.ema_m).add_(p, alpha=1 - self.ema_m)
