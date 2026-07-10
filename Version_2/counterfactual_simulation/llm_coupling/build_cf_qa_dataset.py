"""build_cf_qa_dataset.py — training/eval data for the LATENT-injection route (Route B).

For TRAIN + VAL: generate family-B and family-C questions (single-patient; where the world model
applies) with observed/known-arrow labels, and attach a raw-latent pack per question. For TEST: attach
packs to the EXISTING cf_questions.jsonl (keyed by qid) so latent arms evaluate the same items as
vanilla/text. Family A (attribution, two-patient) is text-only; latent packs are single-patient.

Anti-circularity unchanged: labels are observed reality / literature (from build_cf_questions), the world
model supplies only INPUT latents. Split wall: train/val packs from train/val patients, eval on test.

Outputs (in outputs/): cf_qa_{train,val}.jsonl  +  cf_qa_{train,val,test}_packs.pt  ({qid: pack}).
Run (GPU batch): simr python build_cf_qa_dataset.py --train_cap 900 --val_cap 180
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import torch

BASE = Path("/scratch/users/karun09/Version_2/counterfactual_simulation")
HERE = Path(__file__).resolve().parent
for p in (str(BASE), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import rollout_api as R  # noqa: E402
from eval_simulator_benchmarkB import lab_series, ref_ranges  # noqa: E402
import build_cf_questions as BQ  # noqa: E402

OUT = HERE / "outputs"


def _packs_for(engine, recs, sub_by_pid, horizon):
    packs = {}
    for r in recs:
        cc = r["candidate_context"]
        pid = cc["patient_id"]
        e = sub_by_pid[pid]
        tz = int(cc.get("tz_index", 0))
        pack = R.build_latent_pack(engine, e, tz_index=tz, horizon=horizon)
        packs[r["qid"]] = pack
    return packs


def _gen_split(subtest, series, refs, rng, cap):
    """family B + C records for a split (no A — latent packs are single-patient)."""
    recs = BQ.build_B(subtest, series, refs, rng, cap) + BQ.build_C(subtest, series, rng, cap)
    for k, r in enumerate(recs):
        r["qid"] = f"{r['family']}_{k:05d}"
    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train_cap", type=int, default=900)
    ap.add_argument("--val_cap", type=int, default=180)
    ap.add_argument("--horizon", type=int, default=3)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)

    sub = pickle.load(open(BASE / "data/train_substrate.pkl", "rb"))
    traj = pickle.load(open(BASE / "data/trajectories.pkl", "rb"))
    sp = json.loads((BASE / "data/splits.json").read_text())["splits"]
    series = lab_series(traj)
    refs = ref_ranges()
    sub_by_pid = {int(e["patient_id"]): e for e in sub}
    engine = R.load_engine()
    print(f"engine on {R.DEV}; horizon={args.horizon}")

    OUT.mkdir(parents=True, exist_ok=True)
    # ---- train / val: generate + pack ----
    for split, cap in (("train", args.train_cap), ("val", args.val_cap)):
        subset = [e for e in sub if int(e["patient_id"]) in set(sp[split])]
        recs = _gen_split(subset, series, refs, rng, cap)
        packs = _packs_for(engine, recs, sub_by_pid, args.horizon)
        with open(OUT / f"cf_qa_{split}.jsonl", "w") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")
        torch.save(packs, OUT / f"cf_qa_{split}_packs.pt")
        dist = {fam: dict(Counter(r["answer"] for r in recs if r["family"] == fam)) for fam in "BC"}
        print(f"[{split}] {len(recs)} recs (B/C), packs={len(packs)}  dist={dist}")

    # ---- test: attach packs to existing eval questions (B/C only) ----
    test_recs = [json.loads(l) for l in open(OUT / "cf_questions.jsonl")]
    bc = [r for r in test_recs if r["family"] in ("B", "C")]
    packs = _packs_for(engine, bc, sub_by_pid, args.horizon)
    torch.save(packs, OUT / "cf_qa_test_packs.pt")
    print(f"[test] packs for {len(packs)} B/C eval questions")
    print("DONE")


if __name__ == "__main__":
    main()
