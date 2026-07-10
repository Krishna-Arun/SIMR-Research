"""
extract_benefit_outcome.py — re-extract a BENEFIT-ALIGNED, long-horizon outcome.

WHY: the golden inspection proved that troponin/CK-MB at 96h is dominated by the
periprocedural injury hump — PCI makes the injury marker RISE acutely even though it is
beneficial. So a 96h injury level cannot measure "did the treatment help." To measure
benefit we look PAST the hump: does the injury marker RESOLVE toward normal by a longer
horizon (peak -> last available value within index+HORIZON_DAYS)?

For each admission we compute, per injury marker:
  peak_post   = max post-index value within HORIZON_DAYS         (captures the hump)
  last_post   = last post-index value within HORIZON_DAYS        (captures recovery)
  resolution  = (peak_post - last_post) / peak_post              (1.0 = fully resolved, 0 = stuck high)
A higher resolution = better recovery = treatment more useful. The CTB ground truth then uses
the matched-pair DiD on `resolution` (benefit-aligned: treated resolving MORE than control = helps).

Sodium (negative control): carried through unchanged; its benefit truth is fixed to no-different.

HEAVY (scans the 978k-row labs CSV) -> run as a Slurm job (run_extract.sbatch), NOT on login node.
Output: data/benefit_outcomes.json
"""
import pandas as pd, numpy as np, json
from pathlib import Path
from datetime import timedelta

D = Path("/scratch/users/karun09/physionet.org/files/mimic-iv-ext-cardiac-disease/1.0.0")
BENCH = Path("/scratch/users/karun09/CAUSAL_BENCHMARK")
OUT = Path("/scratch/users/karun09/causal_benchmark_v3/data/benefit_outcomes.json")
HORIZON_DAYS = 14
INJURY = ["Troponin T", "Creatine Kinase, MB Isoenzyme"]

def main():
    epdata = json.loads((BENCH/"data/episodes.json").read_text())
    eps = epdata["episodes"]
    index_by_hadm = {e["hadm_id"]: pd.Timestamp(e["intervention"]["index_time"]) for e in eps}
    hadms = set(index_by_hadm)

    labs = pd.read_csv(D/"heart_labevents_examination_group.csv", low_memory=False,
                       usecols=["hadm_id","charttime","valuenum","label"])
    labs = labs[labs["hadm_id"].isin(hadms) & labs["label"].isin(INJURY) & labs["valuenum"].notna()]
    labs["charttime"] = pd.to_datetime(labs["charttime"])

    out = {}
    for e in eps:
        h = e["hadm_id"]; idx = index_by_hadm[h]; horizon = idx + timedelta(days=HORIZON_DAYS)
        rec = {}
        sub = labs[labs["hadm_id"] == h]
        for m in INJURY:
            md = sub[sub["label"] == m]
            post = md[(md["charttime"] > idx) & (md["charttime"] <= horizon)].sort_values("charttime")
            if len(post) < 2:
                continue
            vals = post["valuenum"].tolist()
            peak = max(vals); last = vals[-1]
            resolution = (peak - last)/peak if peak else 0.0
            rec[m] = {"peak_post": round(peak,3), "last_post": round(last,3),
                      "resolution": round(float(resolution),3), "n_post": len(vals),
                      "horizon_days": HORIZON_DAYS}
        if rec:
            out[e["episode_id"]] = rec

    OUT.write_text(json.dumps({"horizon_days": HORIZON_DAYS, "metric": "resolution=(peak-last)/peak",
                               "n_episodes_with_outcome": len(out), "outcomes": out}, indent=2))
    print(f"wrote {OUT} — {len(out)} episodes with a long-horizon resolution outcome")

if __name__ == "__main__":
    main()
