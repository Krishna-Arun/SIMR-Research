#!/usr/bin/env python3
"""
Train the counterfactual-simulation world model (CLUSTER entry, SLURM-ready).

Dataset: cohort patients (Longitudinal/cohort_data + longitudinal_contexts.json).
For each patient:
  - CLMBR-encode the event timeline -> state sequence z_1..z_T  (clmbr_encoder)
  - action_t = intervention family applied at t (build_action_vector)
  - self-supervised JEPA target: EMA-teacher next-state latent
  - supervised readout targets: post-intervention lab directions (from B_trajectory) +
    outcome (A2_outcome) at the anchor step

Objective = jepa_loss(next-state) + CE(direction) + BCE(mortality/readmission).

STATUS: SCAFFOLD. `--smoke` trains a few steps on synthetic tensors to prove the wiring
locally (no CLMBR/cohort needed). The real run (CLMBR backend + cohort) is a cluster job.

Run (cluster):  python train_worldmodel.py --epochs 20 --device cuda
Run (laptop):   python train_worldmodel.py --smoke
"""
from __future__ import annotations

import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _smoke(steps: int = 5):
    import torch
    from world_model import ActionConditionedWorldModel, EMATeacher, jepa_loss
    from readout import ReadoutHeads
    wm = ActionConditionedWorldModel(state_dim=768, action_dim=8)
    heads = ReadoutHeads(state_dim=768, core_labs=["Creatinine", "Potassium", "Hemoglobin"])
    teacher = EMATeacher(wm)
    opt = torch.optim.AdamW(list(wm.parameters()) + list(heads.parameters()), lr=1e-4)
    for i in range(steps):
        B, T, D, A = 4, 6, 768, 8
        z = torch.randn(B, T, D); acts = torch.randn(B, T, A)
        with torch.no_grad():
            tgt = teacher.teacher(z, acts)          # EMA-teacher target latents
        pred = wm(z, acts)
        readout = heads(pred[:, -1, :])
        dir_tgt = torch.randint(0, 3, (B, len(heads.core_labs)))
        mort_tgt = torch.randint(0, 2, (B,)).float()
        loss = (jepa_loss(pred, tgt)
                + torch.nn.functional.cross_entropy(
                    readout["direction_logits"].reshape(-1, 3), dir_tgt.reshape(-1))
                + torch.nn.functional.binary_cross_entropy(readout["mortality_risk"], mort_tgt))
        opt.zero_grad(); loss.backward(); opt.step(); teacher.update(wm)
        print(f"  step {i}: loss={loss.item():.4f}")
    ckpt = HERE / "checkpoints"; ckpt.mkdir(exist_ok=True)
    torch.save({"world_model": wm.state_dict(), "readout": heads.state_dict(),
                "core_labs": heads.core_labs}, ckpt / "worldmodel_smoke.pt")
    print(f"smoke train OK -> {ckpt/'worldmodel_smoke.pt'}")


from datetime import datetime


def _parse_dt(s: str):
    """Parse ISO timestamps that use either 'T' or space as the date/time separator."""
    s = s.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return datetime.fromisoformat(s.replace(" ", "T"))


def _load_cohort():
    import json
    ctx = json.load(open(HERE.parent / "Longitudinal" / "longitudinal_contexts.json"))["contexts"]
    ctx_by_id = {str(c["subject_id"]): c for c in ctx}
    idx = json.load(open(HERE / "embeddings" / "index.json"))
    emb = idx["patients"]
    split = json.load(open(HERE.parent / "Longitudinal" / "cohort_data" / "cohort_split.json"))["by_subject"]
    return ctx_by_id, emb, split


def _build_core_labs(ctx_by_id, train_ids, top_k=20):
    """Top-k most frequent B_trajectory lab names across train contexts."""
    from collections import Counter
    cnt = Counter()
    for sid in train_ids:
        c = ctx_by_id.get(sid)
        if not c:
            continue
        for t in c.get("B_trajectory", {}).get("targets", []) or []:
            cnt[t["lab"]] += 1
    return [lab for lab, _ in cnt.most_common(top_k)]


def _build_example(sid, ctx_by_id, emb, core_labs, max_len, ACTION_FAMILIES,
                   build_action_vector, DIRECTIONS, np, torch):
    """Return (states[T,768], actions[T,8], anchor_idx, dir_tgt[n], mort, readm) or None."""
    import os
    c = ctx_by_id.get(sid)
    e = emb.get(sid)
    if c is None or e is None:
        return None
    npy = HERE / "embeddings" / os.path.basename(e["path"])
    if not npy.exists():
        return None
    states = np.load(npy).astype("float32")
    T = states.shape[0]
    ev = e["event_times"]
    if len(ev) != T:
        T = min(T, len(ev))
        states = states[:T]
        ev = ev[:T]
    if T == 0:
        return None
    anchor_time = _parse_dt(e["anchor_time"])
    family = c["anchor"]["family"]
    ev_dt = [_parse_dt(x) for x in ev]
    # action per row: "none" before anchor, intervention family from anchor onward
    acts = np.zeros((T, 8), dtype="float32")
    for i, dt in enumerate(ev_dt):
        fam = "none" if dt < anchor_time else family
        acts[i] = build_action_vector(fam)
    # anchor step = last row whose event_time <= anchor_time (pre-intervention state)
    pre = [i for i, dt in enumerate(ev_dt) if dt <= anchor_time]
    anchor_idx = pre[-1] if pre else T - 1
    # truncate to a window that always includes the anchor row (bound compute)
    if T > max_len:
        start = max(0, min(anchor_idx - max_len + 1, T - max_len))
        states = states[start:start + max_len]
        acts = acts[start:start + max_len]
        anchor_idx -= start
        T = states.shape[0]
    # direction targets over fixed core-lab vocab; missing labs masked with -100
    lab_index = {l: i for i, l in enumerate(core_labs)}
    dir_tgt = np.full(len(core_labs), -100, dtype="int64")
    for t in c.get("B_trajectory", {}).get("targets", []) or []:
        j = lab_index.get(t["lab"])
        if j is not None and t.get("direction") in DIRECTIONS:
            dir_tgt[j] = DIRECTIONS.index(t["direction"])
    out = c.get("A2_outcome", {}) or {}
    mort = float(bool(out.get("mortality_1y")))
    readm = float(bool(out.get("readmission_30d")))
    return (torch.from_numpy(states), torch.from_numpy(acts), anchor_idx,
            torch.from_numpy(dir_tgt), mort, readm)


def _collate(batch, torch):
    """Pad variable-length sequences; return padded tensors + valid-length mask."""
    maxT = max(b[0].shape[0] for b in batch)
    B = len(batch)
    D = batch[0][0].shape[1]
    A = batch[0][1].shape[1]
    states = torch.zeros(B, maxT, D)
    acts = torch.zeros(B, maxT, A)
    mask = torch.zeros(B, maxT, dtype=torch.bool)
    anchors = torch.zeros(B, dtype=torch.long)
    n = batch[0][3].shape[0]
    dir_tgt = torch.full((B, n), -100, dtype=torch.long)
    mort = torch.zeros(B)
    readm = torch.zeros(B)
    for i, (s, a, ai, dt, mo, re) in enumerate(batch):
        t = s.shape[0]
        states[i, :t] = s
        acts[i, :t] = a
        mask[i, :t] = True
        anchors[i] = ai
        dir_tgt[i] = dt
        mort[i] = mo
        readm[i] = re
    return states, acts, mask, anchors, dir_tgt, mort, readm


def train_real(args):
    import sys
    sys.path.insert(0, str(HERE))
    import time
    import numpy as np
    import torch
    import torch.nn.functional as F
    from world_model import (ActionConditionedWorldModel, EMATeacher, jepa_loss,
                             build_action_vector, ACTION_FAMILIES)
    from readout import ReadoutHeads, DIRECTIONS

    torch.manual_seed(0)
    device = torch.device(args.device)
    print(f"[train_real] device={device}")

    ctx_by_id, emb, split = _load_cohort()
    train_ids = [str(x) for x in split["train"]]
    val_ids = [str(x) for x in split["val"]]

    core_labs = _build_core_labs(ctx_by_id, train_ids, top_k=20)
    print(f"[train_real] core-lab vocab ({len(core_labs)}): {core_labs}")

    def build_split(ids):
        out = []
        for sid in ids:
            ex = _build_example(sid, ctx_by_id, emb, core_labs, args.max_len,
                                ACTION_FAMILIES, build_action_vector, DIRECTIONS, np, torch)
            if ex is not None:
                out.append(ex)
        return out

    train_set = build_split(train_ids)
    val_set = build_split(val_ids)
    print(f"[train_real] usable train={len(train_set)} val={len(val_set)}")
    if not train_set:
        raise RuntimeError("no usable training examples (embeddings/contexts missing)")

    state_dim, action_dim = 768, 8
    wm = ActionConditionedWorldModel(state_dim=state_dim, action_dim=action_dim).to(device)
    heads = ReadoutHeads(state_dim=state_dim, core_labs=core_labs).to(device)
    teacher = EMATeacher(wm)
    teacher.teacher.to(device)
    opt = torch.optim.AdamW(list(wm.parameters()) + list(heads.parameters()), lr=args.lr)

    lambda_dir, lambda_out = 1.0, 0.5
    bs = args.batch_size
    t0 = time.time()

    def run_val():
        wm.eval(); heads.eval()
        dir_correct = dir_total = 0
        mort_scores, mort_labels = [], []
        with torch.no_grad():
            for i in range(0, len(val_set), bs):
                batch = val_set[i:i + bs]
                states, acts, mask, anchors, dir_tgt, mort, readm = _collate(batch, torch)
                states, acts = states.to(device), acts.to(device)
                pred = wm(states, acts)
                z_anchor = pred[torch.arange(len(batch)), anchors]  # [B,768]
                r = heads(z_anchor)
                dl = r["direction_logits"]  # [B,n,3]
                dp = dl.argmax(-1).cpu()
                valid = dir_tgt != -100
                dir_correct += int((dp[valid] == dir_tgt[valid]).sum())
                dir_total += int(valid.sum())
                mort_scores.extend(r["mortality_risk"].cpu().tolist())
                mort_labels.extend(mort.tolist())
        dir_acc = dir_correct / max(dir_total, 1)
        auc = _auc(mort_scores, mort_labels)
        return dir_acc, auc, mort_scores, mort_labels

    for epoch in range(args.epochs):
        wm.train(); heads.train()
        perm = torch.randperm(len(train_set)).tolist()
        ep_loss = ep_jepa = ep_dir = ep_out = 0.0
        nb = 0
        for i in range(0, len(train_set), bs):
            batch = [train_set[j] for j in perm[i:i + bs]]
            states, acts, mask, anchors, dir_tgt, mort, readm = _collate(batch, torch)
            states, acts, mask = states.to(device), acts.to(device), mask.to(device)
            dir_tgt, mort, readm = dir_tgt.to(device), mort.to(device), readm.to(device)
            with torch.no_grad():
                tgt = teacher.teacher(states, acts)
            pred = wm(states, acts)
            m = mask.unsqueeze(-1)
            l_jepa = jepa_loss(pred * m, tgt * m)
            z_anchor = pred[torch.arange(len(batch)), anchors]
            r = heads(z_anchor)
            l_dir = F.cross_entropy(r["direction_logits"].reshape(-1, 3),
                                    dir_tgt.reshape(-1), ignore_index=-100)
            if torch.isnan(l_dir):
                l_dir = torch.zeros((), device=device)
            l_out = (F.binary_cross_entropy(r["mortality_risk"], mort)
                     + F.binary_cross_entropy(r["readmission_risk"], readm))
            loss = l_jepa + lambda_dir * l_dir + lambda_out * l_out
            opt.zero_grad(); loss.backward(); opt.step(); teacher.update(wm)
            ep_loss += float(loss); ep_jepa += float(l_jepa)
            ep_dir += float(l_dir); ep_out += float(l_out); nb += 1
        el = time.time() - t0
        print(f"epoch {epoch+1:2d}/{args.epochs}  loss={ep_loss/nb:.4f} "
              f"(jepa={ep_jepa/nb:.4f} dir={ep_dir/nb:.4f} out={ep_out/nb:.4f})  "
              f"[{el:.0f}s]")
        if el > args.max_seconds:
            print(f"[train_real] hit time budget ({args.max_seconds}s), stopping.")
            break

    dir_acc, auc, _, _ = run_val()
    print(f"[val] direction_accuracy={dir_acc:.4f}  mortality_AUC={auc:.4f}")

    ckpt_dir = HERE / "checkpoints"; ckpt_dir.mkdir(exist_ok=True)
    out_path = ckpt_dir / "worldmodel.pt"
    torch.save({
        "world_model": wm.state_dict(),
        "readout": heads.state_dict(),
        "core_labs": core_labs,
        "action_dim": action_dim,
        "state_dim": state_dim,
        "config": {"epochs": args.epochs, "lr": args.lr, "batch_size": bs,
                   "max_len": args.max_len, "lambda_dir": lambda_dir,
                   "lambda_out": lambda_out, "action_families": ACTION_FAMILIES,
                   "directions": DIRECTIONS, "device": str(device),
                   "val_direction_accuracy": dir_acc, "val_mortality_auc": auc},
    }, out_path)
    print(f"[train_real] saved -> {out_path} ({out_path.stat().st_size/1e6:.2f} MB)")


def _auc(scores, labels):
    """ROC-AUC via rank statistic (Mann-Whitney U). Returns nan if single class."""
    pos = [s for s, y in zip(scores, labels) if y == 1]
    neg = [s for s, y in zip(scores, labels) if y == 0]
    if not pos or not neg:
        return float("nan")
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j < len(order) and scores[order[j]] == scores[order[i]]:
            j += 1
        avg = (i + j - 1) / 2.0 + 1.0
        for k in range(i, j):
            ranks[order[k]] = avg
        i = j
    rank_pos = sum(ranks[i] for i in range(len(scores)) if labels[i] == 1)
    n_pos, n_neg = len(pos), len(neg)
    return (rank_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="tiny synthetic train to verify wiring")
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--batch_size", type=int, default=4)
    ap.add_argument("--max_len", type=int, default=512)
    ap.add_argument("--max_seconds", type=float, default=900.0)
    args = ap.parse_args()
    if args.smoke:
        import sys
        sys.path.insert(0, str(HERE))
        _smoke()
    else:
        train_real(args)
