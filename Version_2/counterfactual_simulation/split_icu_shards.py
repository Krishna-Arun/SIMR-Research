"""split_icu_shards.py — partition the bounded 10k MEDS + trajectories into 4 shards for parallel encode.
Each shard gets its own meds_dir + trajectories.pkl + config (out_dir). Round-robin for balance."""
import json, pickle
from pathlib import Path
import pandas as pd, datasets

CS = Path("/scratch/users/karun09/Version_2/counterfactual_simulation")
OUT = CS / "data_icu"
NSHARD = 4


def main():
    ds = datasets.Dataset.from_parquet(str(OUT/"mimic_meds/data/icu_000.parquet"))  # preserves schema
    ds_pids = [int(p) for p in ds["patient_id"]]
    traj = pickle.load(open(OUT/"trajectories.pkl","rb"))
    traj_by = {int(t["patient_id"]): t for t in traj}
    pids = sorted(ds_pids)
    grp = {p: i % NSHARD for i, p in enumerate(pids)}     # round-robin
    base_cfg = (CS/"configs_icu.yaml").read_text()

    for k in range(NSHARD):
        sd = OUT / f"shard{k}"; (sd/"mimic_meds/data").mkdir(parents=True, exist_ok=True)
        idx = [i for i, p in enumerate(ds_pids) if grp[p] == k]
        ds.select(idx).to_parquet(str(sd/"mimic_meds/data/part.parquet"))   # schema-preserving
        tk = [traj_by[p] for p in (ds_pids[i] for i in idx) if p in traj_by]
        pickle.dump(tk, open(sd/"trajectories.pkl","wb"))
        cfg = base_cfg.replace(str(OUT/"mimic_meds"), str(sd/"mimic_meds")).replace(
              f"out_dir:     {OUT}", f"out_dir:     {sd}")
        # robust: replace any bare data_icu out_dir line
        cfg = cfg.replace(f"{OUT}\n", f"{sd}\n")
        (CS/f"configs_icu_shard{k}.yaml").write_text(cfg)
        print(f"shard{k}: {len(idx)} patients, {len(tk)} trajectories -> {sd}")
    print("wrote 4 shards + configs")


if __name__ == "__main__":
    main()
