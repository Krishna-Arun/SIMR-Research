"""filter_icu_meds_bounded.py — bound the ICU MEDS context to the admission window (+demographics).

Full lifetime history made the 10k encode intractable (97k batches, >6h). For ICU dynamics the relevant
context is the current admission, not decades-old events. Keep: birth/gender/death (femr needs birthdate)
+ all events inside any admission window (±6h). Rewrites data_icu/mimic_meds/data/icu_000.parquet in place.
Run in clmbr311 (needs datasets)."""
import json
from pathlib import Path
import pandas as pd, datasets

BASE = Path("/scratch/users/karun09/Version_2/counterfactual_simulation")
OUT = BASE / "data_icu"
SHARD = OUT / "mimic_meds/data/icu_000.parquet"
DEMOG = ("SNOMED/184099003", "SNOMED/419620001", "MIMIC_IV_Gender/")


def main():
    samp = json.loads((OUT/"icu_sample.json").read_text())
    windows = {int(k): [(pd.Timestamp(a)-pd.Timedelta(hours=6), pd.Timestamp(b)+pd.Timedelta(hours=6))
                        for a, b in v] for k, v in samp["windows"].items()}
    df = pd.read_parquet(str(SHARD))     # bulk read (fast) instead of datasets row-iteration
    print(f"loaded {len(df)} patients", flush=True)

    rows = []; n_before = 0; n_after = 0
    for row in df.to_dict("records"):    # plain loop — no multiprocessing workers
        pid = int(row["patient_id"]); wins = windows.get(pid, [])
        keep = []
        for e in row["events"]:
            n_before += 1
            c = e["code"]
            if c.startswith(DEMOG):
                keep.append(e); continue
            t = pd.Timestamp(e["time"])
            if any(lo <= t <= hi for lo, hi in wins):
                keep.append(e)
        if len(keep) >= 2:
            rows.append({"patient_id": pid, "events": keep}); n_after += len(keep)
    print(f"events {n_before:,} -> {n_after:,} ({100*n_after/max(n_before,1):.1f}%); patients kept {len(rows)}", flush=True)
    tmp = str(SHARD) + ".tmp"
    datasets.Dataset.from_list(rows).to_parquet(tmp)
    Path(tmp).replace(SHARD)
    print(f"rewrote {SHARD}", flush=True)


if __name__ == "__main__":
    main()
