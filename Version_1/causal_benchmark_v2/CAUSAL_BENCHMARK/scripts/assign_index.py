"""
assign_index.py  —  per-admission treatment arm + TIME-ZERO (index), shared by all steps.

Time-zero = the treatment-decision point (everything BEFORE it is model input; everything
after is outcome / excluded):
  - treated (PCI/CABG): index = procedure time (chartdate + 12h; MIMIC procedure dates are
    day-resolution). Input = the full pre-procedure workup.
  - medical (no procedure): index = admittime + MATCHED decision window = the treated arms'
    MEDIAN time-from-admission-to-procedure, so window lengths are comparable across arms and
    window length itself doesn't betray the arm.

Output: data/index.json  {hadm_id: {arm, index_time, ttp_hours}}. Light (procedures + admissions
only) — runs now; admissions.csv.gz has landed.
"""

import json
import logging
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

BENCH = Path(__file__).parent.parent
sys.path.insert(0, str(BENCH / "scripts"))
from build_dataset import arm_for_codes, pci_vessel_group, D as CARDIAC_DIR
import mimic_link

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

PROC_FILE = CARDIAC_DIR / "heart_procedures.csv"
DIAG_FILE = CARDIAC_DIR / "heart_diagnoses_all_true.csv"
OUT = BENCH / "data" / "index.json"
PROC_DAY_OFFSET_H = 12          # procedure date -> midday (dates are day-resolution)
MIN_TTP_H = 6.0                 # floor on time-to-procedure (guards data quirks)


def main():
    procs = pd.read_csv(PROC_FILE, dtype={"icd_code": str})
    procs["chartdate"] = pd.to_datetime(procs["chartdate"], errors="coerce")
    codes_by_hadm = procs.groupby("hadm_id")["icd_code"].apply(lambda s: set(map(str, s)))
    proc_dt = procs.groupby("hadm_id")["chartdate"].min()

    arm_of, vessel_of = {}, {}
    for h, codes in codes_by_hadm.items():
        a = arm_for_codes(codes)
        if a:
            arm_of[h] = a
            vessel_of[h] = pci_vessel_group(codes) if a == "pci" else "n/a"

    diag = pd.read_csv(DIAG_FILE, usecols=["hadm_id"])
    universe = set(diag["hadm_id"].unique())
    for h in universe:
        arm_of.setdefault(h, "medical")

    adm, _, _ = mimic_link.load_core(mimic_link.mimic_root())
    admit = adm.dropna(subset=["admittime"]).set_index("hadm_id")["admittime"].to_dict()

    # treated time-to-procedure (hours), to set the matched medical window
    ttps = []
    for h, a in arm_of.items():
        if a in ("pci", "cabg") and h in admit and h in proc_dt.index and pd.notna(proc_dt[h]):
            idx = proc_dt[h] + timedelta(hours=PROC_DAY_OFFSET_H)
            ttp = (idx - pd.Timestamp(admit[h])).total_seconds() / 3600.0
            if ttp >= MIN_TTP_H:
                ttps.append(ttp)
    median_ttp = float(np.median(ttps)) if ttps else 36.0
    log.info(f"Treated time-to-procedure: median={median_ttp:.1f}h (n={len(ttps)}); "
             f"medical index = admit + {median_ttp:.1f}h")

    out = {}
    n = {"pci": 0, "cabg": 0, "medical": 0, "skip": 0}
    for h in universe:
        a = arm_of[h]
        if h not in admit:
            n["skip"] += 1
            continue
        if a in ("pci", "cabg") and h in proc_dt.index and pd.notna(proc_dt[h]):
            idx = proc_dt[h] + timedelta(hours=PROC_DAY_OFFSET_H)
            ttp = (idx - pd.Timestamp(admit[h])).total_seconds() / 3600.0
            if ttp < MIN_TTP_H:                      # procedure essentially at admission -> floor it
                idx = pd.Timestamp(admit[h]) + timedelta(hours=MIN_TTP_H); ttp = MIN_TTP_H
        else:
            idx = pd.Timestamp(admit[h]) + timedelta(hours=median_ttp); ttp = median_ttp
        out[str(int(h))] = {"hadm_id": int(h), "arm": a, "index_time": idx.isoformat(),
                            "ttp_hours": round(float(ttp), 1), "pci_vessels": vessel_of.get(h, "n/a")}
        n[a] += 1

    OUT.write_text(json.dumps({"median_ttp_h": round(median_ttp, 1), "min_ttp_h": MIN_TTP_H,
                               "n": len(out), "arm_sizes": {k: n[k] for k in ("pci", "cabg", "medical")},
                               "index": out}, indent=2))
    log.info(f"Wrote {OUT}: arms {n} (skipped {n['skip']} without admittime)")


if __name__ == "__main__":
    main()
