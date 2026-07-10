"""
build_split.py — the ONE canonical patient-level split (anti-circularity wall).

Every downstream stage draws from disjoint slices of this file:
  train — world-model training + (later) LLM training
  val   — world-model tuning / early stopping
  test  — held-out for the benchmark eval (A/B/C) and the final Δ measurement

Patient-level (subject_id), NOT admission-level — so no patient leaks across splits. Stratified by
treatment arm (PCI / CABG / medical) so each split keeps the arm balance. Seeded once, checked in.
Reads trajectories.pkl (has patient_id + outcomes.arm). Output: splits.json.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path
import numpy as np

BASE = Path("/scratch/users/karun09/Version_2/counterfactual_simulation")
TRAJ = BASE / "data/trajectories.pkl"
OUT = BASE / "data/splits.json"
SEED = 0
FRACS = {"train": 0.70, "val": 0.10, "test": 0.20}


def main():
    traj = pickle.load(open(TRAJ, "rb"))
    # patient_id -> arm (one arm per patient; patient-level dedup)
    pid_arm = {}
    for t in traj:
        pid_arm[int(t["patient_id"])] = t["outcomes"].get("arm", "unknown")
    pids = np.array(sorted(pid_arm))
    arms = np.array([pid_arm[p] for p in pids])
    print(f"{len(pids)} patients; arm counts: "
          + ", ".join(f"{a}={int((arms==a).sum())}" for a in sorted(set(arms))))

    rng = np.random.default_rng(SEED)
    split = {"train": [], "val": [], "test": []}
    # stratify: split WITHIN each arm so proportions hold in every split
    for a in sorted(set(arms)):
        grp = pids[arms == a].copy()
        rng.shuffle(grp)
        n = len(grp)
        n_tr = int(round(n * FRACS["train"]))
        n_va = int(round(n * FRACS["val"]))
        split["train"] += grp[:n_tr].tolist()
        split["val"] += grp[n_tr:n_tr + n_va].tolist()
        split["test"] += grp[n_tr + n_va:].tolist()

    for k in split:
        split[k] = sorted(int(x) for x in split[k])

    # ---- integrity checks ----
    sets = {k: set(v) for k, v in split.items()}
    assert not (sets["train"] & sets["val"]), "train/val overlap!"
    assert not (sets["train"] & sets["test"]), "train/test overlap!"
    assert not (sets["val"] & sets["test"]), "val/test overlap!"
    total = sum(len(v) for v in split.values())
    assert total == len(pids), f"lost patients: {total} != {len(pids)}"

    def arm_mix(v):
        aa = np.array([pid_arm[p] for p in v])
        return {a: int((aa == a).sum()) for a in sorted(set(arms))}

    out = {"seed": SEED, "fracs": FRACS, "n_total": len(pids),
           "counts": {k: len(v) for k, v in split.items()},
           "arm_mix": {k: arm_mix(v) for k, v in split.items()},
           "splits": split}
    OUT.write_text(json.dumps(out, indent=2))

    print("\nsplit sizes + arm balance:")
    for k in ("train", "val", "test"):
        mix = out["arm_mix"][k]
        print(f"  {k:5s}: {len(split[k]):4d}  ({', '.join(f'{a}={n}' for a,n in mix.items())})")
    print("\nintegrity: no overlap across splits, all patients accounted for  ✓")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
