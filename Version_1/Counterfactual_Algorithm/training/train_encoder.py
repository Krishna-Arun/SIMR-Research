"""Stage 2a — train the GRU encoder with a next-event SSL objective, then encode every patient.

Outputs:
  data/encoder_gru.pt        — encoder weights + config
  data/code_vocab.json       — code vocabulary + value stats
  data/encoded_states.pkl    — per-patient {patient_id, s:[T,H], action_ids:[T], hours:[T], outcomes}
                               (the substrate for the world model / simulator / RL)

Run:  python training/train_encoder.py [config.yaml]
Research environment only — not a clinical tool.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, random_split

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.common import load_config, get_logger, set_seed, save_pickle, load_pickle
from models.featurize import (CodeVocab, build_vocab, TrajectoryDataset, collate,
                              trajectory_to_arrays)
from models.encoder import GRUEncoder

log = get_logger("train_encoder")


def run_epoch(model, loader, opt, device, train: bool):
    model.train(train)
    tot_loss, tot_tok = 0.0, 0
    for batch in loader:
        code = batch["code"].to(device)
        typ = batch["type"].to(device)
        val = batch["value"].to(device)
        target = batch["target"].to(device)
        b = {"code": code, "type": typ, "value": val}
        _, logits = model(b)
        loss = F.cross_entropy(logits.reshape(-1, logits.size(-1)),
                               target.reshape(-1), ignore_index=-100)
        if train:
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
        ntok = int((target != -100).sum().item())
        tot_loss += loss.item() * max(ntok, 1)
        tot_tok += max(ntok, 1)
    return tot_loss / max(tot_tok, 1)


def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "configs", "default.yaml")
    cfg = load_config(cfg_path)
    set_seed(cfg.get("seed", 0))
    out_dir = cfg["data"]["out_dir"]
    device = cfg["train"]["device"] if torch.cuda.is_available() else "cpu"
    log.info("device=%s", device)

    trajectories = load_pickle(os.path.join(out_dir, "trajectories.pkl"))
    log.info("loaded %d trajectories", len(trajectories))

    vocab = build_vocab(trajectories, max_vocab=cfg["encoder"]["gru"]["max_vocab"])
    log.info("vocab size=%d", vocab.size)
    with open(os.path.join(out_dir, "code_vocab.json"), "w") as f:
        json.dump(vocab.state_dict(), f)

    ds = TrajectoryDataset(trajectories, vocab)
    n_val = max(1, int(len(ds) * cfg["train"]["val_frac"]))
    n_tr = len(ds) - n_val
    g = torch.Generator().manual_seed(cfg.get("seed", 0))
    tr, va = random_split(ds, [n_tr, n_val], generator=g)
    bs = cfg["train"]["batch_size"]
    tr_loader = DataLoader(tr, batch_size=bs, shuffle=True, collate_fn=collate)
    va_loader = DataLoader(va, batch_size=bs, shuffle=False, collate_fn=collate)

    model = GRUEncoder(vocab.size, cfg).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=cfg["train"]["lr"])
    log.info("GRU encoder params=%.2fM", sum(p.numel() for p in model.parameters()) / 1e6)

    history = []
    best_val = float("inf")
    for ep in range(cfg["train"]["epochs"]):
        tr_loss = run_epoch(model, tr_loader, opt, device, train=True)
        with torch.no_grad():
            va_loss = run_epoch(model, va_loader, opt, device, train=False)
        history.append({"epoch": ep, "train_nll": round(tr_loss, 4), "val_nll": round(va_loss, 4)})
        log.info("epoch %2d  train_nll=%.4f  val_nll=%.4f", ep, tr_loss, va_loss)
        best_val = min(best_val, va_loss)

    torch.save({"state_dict": model.state_dict(), "vocab_size": vocab.size,
                "cfg": cfg, "history": history},
               os.path.join(out_dir, "encoder_gru.pt"))

    # ---- encode every patient -> states substrate ----
    log.info("encoding %d patients -> encoded_states.pkl", len(trajectories))
    encoded = []
    model.eval()
    with torch.no_grad():
        for t in trajectories:
            if len(t["events"]) < 2:
                continue
            c, ty, v = trajectory_to_arrays(t, vocab)
            s = model.encode(torch.from_numpy(c), torch.from_numpy(ty),
                             torch.from_numpy(v)).cpu().numpy().astype(np.float32)
            action_ids = np.asarray([e["action_id"] for e in t["events"]], dtype=np.int64)
            hours = np.asarray([e["hours"] for e in t["events"]], dtype=np.float32)
            encoded.append({"patient_id": t["patient_id"], "s": s,
                            "action_ids": action_ids, "hours": hours,
                            "outcomes": t["outcomes"]})
    save_pickle(encoded, os.path.join(out_dir, "encoded_states.pkl"))

    # success criteria: loss decreased, states have right shape
    assert history[-1]["train_nll"] < history[0]["train_nll"] + 1e-6, "train NLL did not improve"
    assert encoded and encoded[0]["s"].shape[1] == model.latent_dim
    log.info("STAGE2_OK: best_val_nll=%.4f, latent_dim=%d, n_encoded=%d",
             best_val, model.latent_dim, len(encoded))


if __name__ == "__main__":
    main()
