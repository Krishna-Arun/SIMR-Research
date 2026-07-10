"""
build_cohort.py — cardiovascular ICU cohort with genuine treatment equipoise + dense labs.

Three filters, intersected:
  1. Equipoise: reuse CARDIAC_COUNTERFACTUAL's already-built 3-arm revascularization cohort
     (data/multiarm_cohort.json) — admissions where the real decision was PCI vs CABG vs medical
     management. This is real clinical equipoise (documented in that project's README), NOT
     Benchmark C's cross-system procedure matching (which deliberately pairs UNRELATED procedures
     like dialysis vs. ventilation across two different patients — not alternatives to each other).
  2. ICU stay required: icu_los_days > 0 (already computed per-episode by mimic_link.link_episode).
  3. Dense labs: >= MIN_DISTINCT_LABS distinct lab itemids and >= MIN_LAB_MEASUREMENTS total
     measurements during the admission, computed fresh from the full hosp/labevents.csv.gz
     (the cardiac-ext source CARDIAC_COUNTERFACTUAL was originally built from is no longer on
     disk, but full MIMIC-IV 3.1 is, and that's all this step needs).

NOTE: the source multiarm_cohort.json was built from a cardiac-ext dataset that has since been
purged from $SCRATCH — that's fine, we reuse its already-computed OUTPUT (arm/eligible/icu_los_days
per hadm_id), we don't need to regenerate it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

CARDIAC_COHORT = Path("/scratch/users/karun09/Version_1/CARDIAC_COUNTERFACTUAL/data/multiarm_cohort.json")
LABEVENTS = Path("/scratch/users/karun09/physionet.org/files/mimiciv/3.1/hosp/labevents.csv.gz")
OUT_DIR = Path("/scratch/users/karun09/Version_2/counterfactual_simulation/cohort")

MIN_DISTINCT_LABS = 20        # same bar Benchmark A already uses for "data-rich enough"
MIN_LAB_MEASUREMENTS = 50


def load_equipoise_icu_cohort() -> pd.DataFrame:
    data = json.loads(CARDIAC_COHORT.read_text())
    df = pd.DataFrame(data["episodes"])
    print(f"multiarm_cohort.json: {len(df)} episodes, arms={data['arm_sizes']}")
    df = df[df["eligible"] == True].copy()               # alive at time-zero
    print(f"  after eligible (alive at index): {len(df)}  arms={df['arm'].value_counts().to_dict()}")
    df = df[df["icu_los_days"] > 0].copy()                # ICU stay required
    print(f"  after ICU-stay required:         {len(df)}  arms={df['arm'].value_counts().to_dict()}")
    return df


def compute_lab_density(hadm_ids: set[int]) -> pd.DataFrame:
    print(f"scanning {LABEVENTS} for {len(hadm_ids):,} target hadm_ids ...")
    counts = {}   # hadm_id -> set(itemid), n_rows
    n_rows_total = 0
    itemid_sets: dict[int, set] = {}
    row_counts: dict[int, int] = {}
    for chunk in pd.read_csv(LABEVENTS, usecols=["hadm_id", "itemid"],
                             dtype={"hadm_id": "float64", "itemid": "int32"},
                             chunksize=5_000_000):
        n_rows_total += len(chunk)
        chunk = chunk.dropna(subset=["hadm_id"])
        chunk["hadm_id"] = chunk["hadm_id"].astype("int64")
        chunk = chunk[chunk["hadm_id"].isin(hadm_ids)]
        if len(chunk):
            for h, g in chunk.groupby("hadm_id")["itemid"]:
                itemid_sets.setdefault(h, set()).update(g.tolist())
                row_counts[h] = row_counts.get(h, 0) + len(g)
        print(f"  scanned {n_rows_total:,} rows so far, matched {len(itemid_sets):,} hadm_ids", end="\r")
    print()
    rows = [{"hadm_id": h, "n_distinct_labs": len(itemid_sets.get(h, set())),
            "n_lab_measurements": row_counts.get(h, 0)} for h in hadm_ids]
    return pd.DataFrame(rows)


def main():
    cohort = load_equipoise_icu_cohort()
    density = compute_lab_density(set(cohort["hadm_id"].astype(int)))
    merged = cohort.merge(density, on="hadm_id", how="left")
    merged["n_distinct_labs"] = merged["n_distinct_labs"].fillna(0).astype(int)
    merged["n_lab_measurements"] = merged["n_lab_measurements"].fillna(0).astype(int)

    print("\nlab-density distribution (pre-filter):")
    print(merged[["n_distinct_labs", "n_lab_measurements"]].describe(percentiles=[.1, .25, .5, .75, .9]))

    final = merged[(merged["n_distinct_labs"] >= MIN_DISTINCT_LABS) &
                   (merged["n_lab_measurements"] >= MIN_LAB_MEASUREMENTS)].copy()
    print(f"\nafter dense-labs filter (>={MIN_DISTINCT_LABS} distinct, >={MIN_LAB_MEASUREMENTS} total): "
         f"{len(final)}  arms={final['arm'].value_counts().to_dict()}")

    keep_cols = ["hadm_id", "arm", "pci_vessels", "index_time", "ttp_hours", "age", "sex",
                "icu_los_days", "icu_readmit", "n_comorbidities", "aki", "aki_stage",
                "in_hospital_mortality", "mortality_30d", "readmission_30d",
                "n_distinct_labs", "n_lab_measurements"]
    final = final[[c for c in keep_cols if c in final.columns]]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    final.to_parquet(OUT_DIR / "cohort_v1.parquet", index=False)
    summary = {
        "n_final": len(final),
        "arm_sizes": final["arm"].value_counts().to_dict(),
        "filters": {"equipoise_source": str(CARDIAC_COHORT), "icu_required": True,
                   "min_distinct_labs": MIN_DISTINCT_LABS, "min_lab_measurements": MIN_LAB_MEASUREMENTS},
        "age_mean": float(final["age"].dropna().mean()) if "age" in final and len(final) else None,
        "mortality_30d_rate": float(final["mortality_30d"].mean()) if "mortality_30d" in final and len(final) else None,
    }
    (OUT_DIR / "cohort_v1_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nwrote {OUT_DIR / 'cohort_v1.parquet'} ({len(final)} rows)")
    print(f"wrote {OUT_DIR / 'cohort_v1_summary.json'}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
