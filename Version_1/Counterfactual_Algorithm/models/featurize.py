"""Tokenize patient trajectories into tensors for the GRU encoder.

Each event becomes (code_id, type_id, value_norm). The code vocabulary is frequency-capped;
rare codes -> <UNK>. Lab values are z-scored per code (stats gathered at vocab-build time).

This featurization backs the *from-scratch* GRU encoder. The CLMBR path bypasses it entirely
(femr tokenizes OMOP/SNOMED codes with its own pretrained dictionary).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import List

import numpy as np
import torch
from torch.utils.data import Dataset

PAD, UNK = "<pad>", "<unk>"
EVENT_TYPES = ["admission", "discharge", "diagnosis", "procedure", "drug", "lab"]
TYPE_ID = {t: i + 1 for i, t in enumerate(EVENT_TYPES)}  # 0 = pad


class CodeVocab:
    def __init__(self, code2id: dict, value_stats: dict):
        self.code2id = code2id
        self.value_stats = value_stats           # code -> (mean, std)
        self.id2code = {i: c for c, i in code2id.items()}

    @property
    def size(self) -> int:
        return len(self.code2id)

    def cid(self, code: str) -> int:
        return self.code2id.get(code, self.code2id[UNK])

    def value_norm(self, code: str, value) -> float:
        if value is None:
            return 0.0
        mean, std = self.value_stats.get(code, (0.0, 1.0))
        std = std if std > 1e-6 else 1.0
        return float((value - mean) / std)

    def state_dict(self) -> dict:
        return {"code2id": self.code2id, "value_stats": self.value_stats}

    @classmethod
    def load(cls, d: dict) -> "CodeVocab":
        return cls(d["code2id"], {k: tuple(v) for k, v in d["value_stats"].items()})


def build_vocab(trajectories: List[dict], max_vocab: int = 20000) -> CodeVocab:
    freq = Counter()
    vals = defaultdict(list)
    for t in trajectories:
        for e in t["events"]:
            freq[e["code"]] += 1
            if e.get("value") is not None:
                vals[e["code"]].append(e["value"])
    code2id = {PAD: 0, UNK: 1}
    for code, _ in freq.most_common(max_vocab):
        code2id[code] = len(code2id)
    value_stats = {}
    for code, vlist in vals.items():
        arr = np.asarray(vlist, dtype=np.float64)
        value_stats[code] = (float(arr.mean()), float(arr.std()))
    return CodeVocab(code2id, value_stats)


def trajectory_to_arrays(traj: dict, vocab: CodeVocab):
    code_ids, type_ids, values = [], [], []
    for e in traj["events"]:
        code_ids.append(vocab.cid(e["code"]))
        type_ids.append(TYPE_ID.get(e["type"], 0))
        values.append(vocab.value_norm(e["code"], e.get("value")))
    return (np.asarray(code_ids, dtype=np.int64),
            np.asarray(type_ids, dtype=np.int64),
            np.asarray(values, dtype=np.float32))


class TrajectoryDataset(Dataset):
    """Yields per-patient sequences for next-event SSL. Trajectories shorter than 2 are dropped."""

    def __init__(self, trajectories: List[dict], vocab: CodeVocab, max_len: int = 512):
        self.vocab = vocab
        self.max_len = max_len
        self.items = [t for t in trajectories if len(t["events"]) >= 2]

    def __len__(self):
        return len(self.items)

    def __getitem__(self, idx):
        t = self.items[idx]
        c, ty, v = trajectory_to_arrays(t, self.vocab)
        if len(c) > self.max_len:
            c, ty, v = c[: self.max_len], ty[: self.max_len], v[: self.max_len]
        return {"code": torch.from_numpy(c), "type": torch.from_numpy(ty),
                "value": torch.from_numpy(v), "length": len(c),
                "patient_id": t["patient_id"]}


def collate(batch: list) -> dict:
    """Right-pad a batch to the max length; build a next-code target shifted by one step."""
    B = len(batch)
    L = max(b["length"] for b in batch)
    code = torch.zeros(B, L, dtype=torch.long)
    typ = torch.zeros(B, L, dtype=torch.long)
    val = torch.zeros(B, L, dtype=torch.float)
    target = torch.full((B, L), -100, dtype=torch.long)   # -100 ignored by cross-entropy
    lengths = torch.zeros(B, dtype=torch.long)
    pids = []
    for i, b in enumerate(batch):
        n = b["length"]
        code[i, :n] = b["code"]
        typ[i, :n] = b["type"]
        val[i, :n] = b["value"]
        # next-event target: predict code[t+1] from state at t
        if n >= 2:
            target[i, : n - 1] = b["code"][1:n]
        lengths[i] = n
        pids.append(b["patient_id"])
    mask = torch.arange(L)[None, :] < lengths[:, None]
    return {"code": code, "type": typ, "value": val, "target": target,
            "mask": mask, "length": lengths, "patient_id": pids}
