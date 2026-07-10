"""Stage 6 — offline policy learning in the learned simulator.

Ships a Behavior-Cloning (BC) baseline: learn pi(a | s) from observed (state, clinician-action)
pairs, then evaluate it inside MimicLatentEnv against random / always-no-op baselines by mean
discounted return. A Conservative-Q-Learning (CQL) offline-RL agent is scaffolded (structure +
TODOs) as the documented upgrade path.

OFFLINE RL IN A LEARNED SIMULATOR — research only, not clinical deployment. Returns are proxy
rewards in a model that has its own error; "policy value" here measures behavior in the simulator,
not real clinical benefit.

Run:  python training/train_agent.py [config.yaml]
"""
from __future__ import annotations

import os
import sys

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.common import load_config, get_logger, set_seed, load_pickle, save_json, states_path
from models.world_model import WorldModel
from models.decoder import OutcomeDecoder
from preprocessing.actions import ActionVocab
from rl_env.mimic_env import MimicLatentEnv

log = get_logger("train_agent")


class BCPolicy(nn.Module):
    def __init__(self, latent_dim: int, n_actions: int, hidden: int = 256):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(latent_dim, hidden), nn.ReLU(),
                                 nn.Linear(hidden, n_actions))

    def forward(self, s):
        return self.net(s)

    @torch.no_grad()
    def act(self, s):
        return int(self.forward(s.unsqueeze(0)).argmax(-1).item())


class CQLAgent(nn.Module):
    """SCAFFOLD — Conservative Q-Learning for offline RL in the latent simulator.

    TODO: implement the CQL objective (Bellman error + conservative penalty pushing down OOD-action
    Q-values), target network, and offline replay over (s, a, r, s') tuples harvested from the world
    model. Left as the documented upgrade from BC; not trained in this stage.
    """
    def __init__(self, latent_dim: int, n_actions: int, hidden: int = 256):
        super().__init__()
        self.q = nn.Sequential(nn.Linear(latent_dim, hidden), nn.ReLU(),
                               nn.Linear(hidden, n_actions))

    def forward(self, s):
        return self.q(s)


def build_bc_dataset(encoded):
    S, A = [], []
    for r in encoded:
        s, act = r["s"], r["action_ids"]
        if len(s) < 2:
            continue
        S.append(s[:-1]); A.append(act[1:])
    return (torch.from_numpy(np.concatenate(S)).float(),
            torch.from_numpy(np.concatenate(A)).long())


def evaluate_policy(env, policy, n_episodes, gamma, kind="bc", n_actions=1, seed=0):
    rng = np.random.RandomState(seed)
    returns = []
    for _ in range(n_episodes):
        s = env.reset()
        G, disc, done = 0.0, 1.0, False
        while not done:
            if kind == "bc":
                a = policy.act(torch.tensor(s, device=env.device).float())
            elif kind == "random":
                a = rng.randint(n_actions)
            else:  # no_op
                a = 0
            s, r, done, _ = env.step(a)
            G += disc * r; disc *= gamma
        returns.append(G)
    return float(np.mean(returns)), float(np.std(returns))


def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "configs", "default.yaml")
    cfg = load_config(cfg_path)
    set_seed(cfg.get("seed", 0))
    out_dir = cfg["data"]["out_dir"]
    device = "cuda" if torch.cuda.is_available() else "cpu"

    encoded = load_pickle(states_path(cfg))
    latent_dim = encoded[0]["s"].shape[1]
    n_actions = ActionVocab().n_actions

    wm_ck = torch.load(os.path.join(out_dir, "world_model.pt"), map_location=device)
    wm = WorldModel(latent_dim, n_actions, wm_ck["cfg"]); wm.load_state_dict(wm_ck["state_dict"])
    dec = OutcomeDecoder(latent_dim)
    dec.load_state_dict(torch.load(os.path.join(out_dir, "decoder.pt"),
                                   map_location=device)["state_dict"])

    S0 = np.stack([r["s"][0] for r in encoded])
    env = MimicLatentEnv(wm, dec, S0, cfg, device=device, seed=cfg.get("seed", 0))

    # ---- behavior cloning ----
    S, A = build_bc_dataset(encoded)
    S, A = S.to(device), A.to(device)
    policy = BCPolicy(latent_dim, n_actions).to(device)
    opt = torch.optim.Adam(policy.parameters(), lr=1e-3)
    bs = 256
    for ep in range(30):
        perm = torch.randperm(len(S), device=device)
        tot = 0.0
        for i in range(0, len(S), bs):
            idx = perm[i:i + bs]
            loss = F.cross_entropy(policy(S[idx]), A[idx])
            opt.zero_grad(); loss.backward(); opt.step()
            tot += loss.item()
        if ep % 10 == 0:
            log.info("BC epoch %d  loss=%.4f", ep, tot / max(1, len(S) // bs))
    torch.save({"state_dict": policy.state_dict(), "latent_dim": latent_dim,
                "n_actions": n_actions}, os.path.join(out_dir, "agent_bc.pt"))

    # ---- evaluate in the learned simulator ----
    gamma = cfg["rl"]["gamma"]
    n_ep = 50
    bc_mean, bc_std = evaluate_policy(env, policy, n_ep, gamma, "bc", n_actions,
                                      seed=cfg.get("seed", 0))
    rnd_mean, rnd_std = evaluate_policy(env, None, n_ep, gamma, "random", n_actions,
                                        seed=cfg.get("seed", 0))
    noop_mean, noop_std = evaluate_policy(env, None, n_ep, gamma, "no_op", n_actions,
                                          seed=cfg.get("seed", 0))
    results = {
        "disclaimer": "Offline RL in a LEARNED simulator — proxy returns, not clinical benefit.",
        "n_episodes": n_ep, "horizon": cfg["simulation"]["max_steps"], "gamma": gamma,
        "bc_return": [round(bc_mean, 4), round(bc_std, 4)],
        "random_return": [round(rnd_mean, 4), round(rnd_std, 4)],
        "no_op_return": [round(noop_mean, 4), round(noop_std, 4)],
    }
    save_json(results, os.path.join(out_dir, "..", "outputs", "agent_results.json"))
    log.info("agent results: %s", results)
    # success: env runs end-to-end and BC returns a finite value
    assert np.isfinite(bc_mean), "BC return not finite"
    log.info("STAGE6_OK: bc_return=%.4f random=%.4f no_op=%.4f", bc_mean, rnd_mean, noop_mean)


if __name__ == "__main__":
    main()
