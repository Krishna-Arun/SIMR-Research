"""Stage 3 — fit the latent world model f(s_t, a_t, Δt) -> s_{t+1} and the outcome decoder.

Reads data/encoded_states.pkl (from train_encoder.py). Builds transition triples, trains the
world model, and trains the outcome decoder on per-patient terminal states. Success criterion:
held-out 1-step MSE must beat the persistence baseline (s_{t+1} = s_t).

Outputs: data/world_model.pt, data/decoder.pt, data/world_model_metrics.json
Run:  python training/train_world_model.py [config.yaml]
Research environment only — not a clinical tool.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.common import load_config, get_logger, set_seed, load_pickle, save_json, states_path
from models.world_model import WorldModel
from models.decoder import OutcomeDecoder, outcome_targets
from models.deconfound import fit_propensity, stabilized_ipw, treatment_predictability
from preprocessing.actions import ActionVocab

log = get_logger("train_wm")


def build_triples(encoded: list):
    """Return tensors S[N,H], A[N], DT[N], SN[N,H] and a patient-id index for splitting."""
    S, A, DT, SN, PID = [], [], [], [], []
    for rec in encoded:
        s, act, hrs = rec["s"], rec["action_ids"], rec["hours"]
        T = len(s)
        if T < 2:
            continue
        S.append(s[:-1]); SN.append(s[1:])
        A.append(act[1:])                       # action driving the transition into t+1
        DT.append(np.maximum(hrs[1:] - hrs[:-1], 0.0))
        PID.append(np.full(T - 1, rec["patient_id"], dtype=np.int64))
    S = np.concatenate(S); SN = np.concatenate(SN)
    A = np.concatenate(A); DT = np.concatenate(DT); PID = np.concatenate(PID)
    return (torch.from_numpy(S), torch.from_numpy(A).long(),
            torch.from_numpy(DT).float(), torch.from_numpy(SN), torch.from_numpy(PID))


def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "configs", "default.yaml")
    cfg = load_config(cfg_path)
    set_seed(cfg.get("seed", 0))
    out_dir = cfg["data"]["out_dir"]
    device = cfg["train"]["device"] if torch.cuda.is_available() else "cpu"

    encoded = load_pickle(states_path(cfg))
    latent_dim = encoded[0]["s"].shape[1]
    n_actions = ActionVocab().n_actions
    log.info("latent_dim=%d n_actions=%d patients=%d", latent_dim, n_actions, len(encoded))

    S, A, DT, SN, PID = build_triples(encoded)
    log.info("built %d transition triples", len(S))

    # split by patient
    pids = np.array(sorted({int(p) for p in PID.tolist()}))
    rng = np.random.RandomState(cfg.get("seed", 0))
    rng.shuffle(pids)
    n_val = max(1, int(len(pids) * cfg["train"]["val_frac"]))
    val_pids = set(pids[:n_val].tolist())
    val_mask = torch.tensor([int(p) in val_pids for p in PID.tolist()])
    tr_idx = (~val_mask).nonzero(as_tuple=True)[0]
    va_idx = val_mask.nonzero(as_tuple=True)[0]

    # ---- deconfounding: stabilized IPW weights + pre-balancing diagnostic ----
    dc = cfg.get("deconfound", {}) or {}
    W = torch.ones(len(S))
    deconf_metrics = {"enabled": bool(dc.get("enabled", False))}
    if dc.get("enabled", False):
        log.info("deconfounding ON: fitting propensity model pi(a|s) on train transitions")
        prop = fit_propensity(S[tr_idx], A[tr_idx], n_actions, device,
                              epochs=dc.get("propensity_epochs", 30))
        if dc.get("use_ipw", True):
            W = stabilized_ipw(prop, S, A, n_actions, device, clip=dc.get("ipw_clip", 10.0))
            log.info("stabilized IPW weights: mean=%.3f min=%.3f max=%.3f",
                     float(W.mean()), float(W.min()), float(W.max()))
        pre = treatment_predictability(S[va_idx], A[va_idx], n_actions, device)
        deconf_metrics["treatment_predictability_raw_state"] = pre
        log.info("pre-balance treatment predictability (raw state): %s", pre)

    def loader(idx, shuffle):
        ds = TensorDataset(S[idx], A[idx], DT[idx], SN[idx], W[idx])
        return DataLoader(ds, batch_size=cfg["train"]["batch_size"], shuffle=shuffle)

    tr_loader, va_loader = loader(tr_idx, True), loader(va_idx, False)

    # persistence baseline (Δs = 0) on val
    persist_mse = F.mse_loss(S[va_idx], SN[va_idx]).item()

    wm = WorldModel(latent_dim, n_actions, cfg).to(device)
    opt = torch.optim.Adam(wm.parameters(), lr=cfg["train"]["lr"])
    log.info("world model (%s) params=%.2fM", wm.kind,
             sum(p.numel() for p in wm.parameters()) / 1e6)

    history = []
    for ep in range(cfg["train"]["epochs"]):
        wm.train()
        for s, a, dt, sn, w in tr_loader:
            s, a, dt, sn, w = (s.to(device), a.to(device), dt.to(device),
                               sn.to(device), w.to(device))
            loss = wm.loss(s, a, dt, sn, weight=w) + wm.balance_loss(s, a)
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(wm.parameters(), 1.0); opt.step()
        # val 1-step MSE (unweighted, factual predictive check)
        wm.eval(); se, n = 0.0, 0
        with torch.no_grad():
            for s, a, dt, sn, _w in va_loader:
                s, a, dt, sn = s.to(device), a.to(device), dt.to(device), sn.to(device)
                pred = wm(s, a, dt)
                se += F.mse_loss(pred, sn, reduction="sum").item(); n += sn.numel()
        val_mse = se / n
        history.append({"epoch": ep, "val_mse": round(val_mse, 5)})
        log.info("epoch %2d  val_mse=%.5f  (persistence=%.5f)", ep, val_mse, persist_mse)

    # post-balancing diagnostic: how treatment-predictable is the adapter representation now?
    if dc.get("enabled", False) and wm.balance:
        with torch.no_grad():
            z_val = wm._state_rep(S[va_idx].to(device)).cpu()
        post = treatment_predictability(z_val, A[va_idx], n_actions, device)
        deconf_metrics["treatment_predictability_balanced_state"] = post
        log.info("post-balance treatment predictability (adapter z): %s", post)

    torch.save({"state_dict": wm.state_dict(), "latent_dim": latent_dim,
                "n_actions": n_actions, "cfg": cfg, "history": history},
               os.path.join(out_dir, "world_model.pt"))

    # ---- outcome decoder on terminal states ----
    dec = OutcomeDecoder(latent_dim).to(device)
    dopt = torch.optim.Adam(dec.parameters(), lr=1e-3)
    term_s = torch.stack([torch.from_numpy(r["s"][-1]) for r in encoded]).to(device)
    term_y = torch.stack([outcome_targets(r["outcomes"]) for r in encoded]).to(device)
    for ep in range(50):
        dec.train()
        out = dec(term_s)
        loss = (F.binary_cross_entropy_with_logits(out[:, 0], term_y[:, 0])
                + F.binary_cross_entropy_with_logits(out[:, 1], term_y[:, 1])
                + F.mse_loss(out[:, 2], term_y[:, 2]))
        dopt.zero_grad(); loss.backward(); dopt.step()
    torch.save({"state_dict": dec.state_dict(), "latent_dim": latent_dim},
               os.path.join(out_dir, "decoder.pt"))

    metrics = {"persistence_val_mse": round(persist_mse, 5),
               "world_model_val_mse": round(history[-1]["val_mse"], 5),
               "beats_persistence": bool(history[-1]["val_mse"] < persist_mse),
               "kind": wm.kind, "history": history,
               "decoder_final_loss": round(float(loss.item()), 4),
               "deconfounding": deconf_metrics}
    save_json(metrics, os.path.join(out_dir, "world_model_metrics.json"))
    log.info("metrics: %s", {k: v for k, v in metrics.items() if k != "history"})

    assert metrics["beats_persistence"], \
        f"world model val_mse {history[-1]['val_mse']} did not beat persistence {persist_mse}"
    log.info("STAGE3_OK: val_mse=%.5f < persistence=%.5f", history[-1]["val_mse"], persist_mse)


if __name__ == "__main__":
    main()
