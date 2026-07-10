"""grade_cf.py — score prediction files and compute the ablation deltas.

Reads outputs/preds_<arm>_<model>.jsonl (written by run_arm.py) and reports, per (model, arm):
  - per-family balanced accuracy (A: 2-class, B/C: 3-class) + overall
  - parse-failure rate
  - ECE (expected calibration error) from stated confidence
  - reliability-stratified accuracy (abnormal-baseline subset for family B)
And, across arms (paired by qid): Δ(arm − baseline) with a McNemar test + bootstrap 95% CI.
This is where Δ2 = arm2−arm1 and Δ3 = arm3−arm2, latent-vs-text, and the placebo check are read off.

Run: simr python grade_cf.py                      # grades every preds_*.jsonl found
     simr python grade_cf.py --delta text_frozen vanilla   # add a specific paired comparison
"""
from __future__ import annotations

import argparse
import glob
import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "outputs"
FAM_CLASSES = {"A": ["A", "B"], "B": ["Rising", "Falling", "Stable"], "C": ["Higher", "Lower", "Unchanged"]}
FNAME_RE = re.compile(r"preds_(?P<arm>.+)_(?P<model>[^_]+(?:-[^_]+)*)\.jsonl$")


def balacc(gold, pred, classes):
    gold = np.asarray(gold, dtype=object)
    pred = np.asarray(pred, dtype=object)
    accs = []
    for c in classes:
        m = gold == c
        if m.sum() > 0:
            accs.append(float((pred[m] == c).mean()))
    return float(np.mean(accs)) if accs else float("nan")


def ece(confs, corrects, n_bins=10):
    confs = np.asarray([c for c in confs], dtype=float)
    corrects = np.asarray(corrects, dtype=float)
    ok = ~np.isnan(confs)
    if ok.sum() == 0:
        return None
    confs, corrects = confs[ok], corrects[ok]
    bins = np.linspace(0, 1, n_bins + 1)
    e, n = 0.0, len(confs)
    for i in range(n_bins):
        m = (confs > bins[i]) & (confs <= bins[i + 1]) if i > 0 else (confs >= bins[i]) & (confs <= bins[i + 1])
        if m.sum() == 0:
            continue
        e += (m.sum() / n) * abs(corrects[m].mean() - confs[m].mean())
    return round(float(e), 4)


def load_preds(path):
    return [json.loads(l) for l in open(path)]


def grade_file(path):
    recs = load_preds(path)
    by_fam = defaultdict(list)
    for r in recs:
        by_fam[r["family"]].append(r)
    res = {"n": len(recs),
           "parse_fail": round(np.mean([r["pred"] is None for r in recs]), 3),
           "overall_raw_acc": round(np.mean([r["correct"] for r in recs]), 3)}
    fam_bal = []
    for fam, rs in sorted(by_fam.items()):
        ba = balacc([r["gold"] for r in rs], [r["pred"] for r in rs], FAM_CLASSES[fam])
        res[f"{fam}_balacc"] = round(ba, 3)
        res[f"{fam}_n"] = len(rs)
        fam_bal.append(ba)
    res["macro_balacc"] = round(float(np.nanmean(fam_bal)), 3) if fam_bal else None
    res["ece"] = ece([r.get("confidence") for r in recs], [r["correct"] for r in recs])
    # reliability-stratified: family-B abnormal baseline
    b_oor = [r for r in by_fam.get("B", []) if r.get("meta", {}).get("base_oor")]
    if b_oor:
        res["B_balacc_abnormal_baseline"] = round(
            balacc([r["gold"] for r in b_oor], [r["pred"] for r in b_oor], FAM_CLASSES["B"]), 3)
        res["B_n_abnormal_baseline"] = len(b_oor)
    return res, {r["qid"]: r for r in recs}


def mcnemar(base_map, arm_map):
    """paired discordance on shared qids: returns (b, c, n_shared) where b=base-only-correct,
    c=arm-only-correct, and an approx two-sided p (normal approx to the sign test on discordants)."""
    shared = set(base_map) & set(arm_map)
    b = c = 0
    for q in shared:
        bc, ac = base_map[q]["correct"], arm_map[q]["correct"]
        if bc and not ac:
            b += 1
        elif ac and not bc:
            c += 1
    from math import erf, sqrt
    disc = b + c
    if disc == 0:
        p = 1.0
    else:
        z = abs(b - c) / sqrt(disc)
        p = 2 * (1 - 0.5 * (1 + erf(z / sqrt(2))))
    return b, c, len(shared), round(float(p), 4)


def bootstrap_delta(base_map, arm_map, n_boot=2000, seed=0):
    """paired bootstrap 95% CI on Δ mean-accuracy (arm − base) over shared qids."""
    shared = sorted(set(base_map) & set(arm_map))
    if not shared:
        return None
    diffs = np.array([int(arm_map[q]["correct"]) - int(base_map[q]["correct"]) for q in shared], float)
    rng = np.random.default_rng(seed)
    boots = [diffs[rng.integers(0, len(diffs), len(diffs))].mean() for _ in range(n_boot)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return {"delta_mean": round(float(diffs.mean()), 3),
            "ci95": [round(float(lo), 3), round(float(hi), 3)], "n_paired": len(shared)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delta", nargs=2, action="append", metavar=("ARM", "BASELINE"),
                    help="add a paired comparison ARM vs BASELINE (repeatable)")
    ap.add_argument("--model", default=None, help="restrict deltas to one model")
    args = ap.parse_args()

    files = sorted(glob.glob(str(OUT / "preds_*.jsonl")))
    grades, maps = {}, {}
    print("=== per-file grades ===")
    for f in files:
        m = FNAME_RE.search(Path(f).name)
        if not m:
            continue
        arm, model = m.group("arm"), m.group("model")
        g, qmap = grade_file(f)
        grades[(model, arm)] = g
        maps[(model, arm)] = qmap
        print(f"\n[{model} | {arm}]  " + json.dumps(g))

    deltas = {}
    for arm, base in (args.delta or []):
        for (model, a), qmap in maps.items():
            if a != arm or (args.model and model != args.model):
                continue
            if (model, base) not in maps:
                print(f"  (skip Δ {arm}-{base} for {model}: baseline missing)")
                continue
            b, c, n, p = mcnemar(maps[(model, base)], qmap)
            bs = bootstrap_delta(maps[(model, base)], qmap)
            deltas[f"{model}:{arm}-{base}"] = {"mcnemar": {"base_only": b, "arm_only": c, "n": n, "p": p},
                                               "bootstrap": bs}
    if deltas:
        print("\n=== deltas ===")
        print(json.dumps(deltas, indent=2))

    summary = {"grades": {f"{m}|{a}": g for (m, a), g in grades.items()}, "deltas": deltas}
    (OUT / "grades_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nwrote {OUT/'grades_summary.json'}")


if __name__ == "__main__":
    main()
