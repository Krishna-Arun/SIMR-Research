"""
build_multiarm_cohort.py  —  assemble the 3-arm cohort with durable outcomes.

Joins:
  - data/index.json    (arm + time-zero per admission; from assign_index.py)
  - data/context.json  (comorbidities + AKI; from build_context.py)
  - MIMIC core          (mortality / readmission / ICU / age-sex; via mimic_link)

Landmark = alive at time-zero (treated: alive at their procedure; medical: alive at the matched
decision window) — so we never credit a treatment for a patient who didn't reach the decision.

Output: data/multiarm_cohort.json + per-arm composition (overlap sanity).
"""

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BENCH = Path(__file__).parent.parent
sys.path.insert(0, str(BENCH / "scripts"))
import mimic_link

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

INDEX_FILE = BENCH / "data" / "index.json"
CONTEXT_FILE = BENCH / "data" / "context.json"
OUT = BENCH / "data" / "multiarm_cohort.json"
ARMS = ["pci", "cabg", "medical"]


def main():
    idx = json.loads(INDEX_FILE.read_text())["index"]
    ctx = {}
    if CONTEXT_FILE.exists():
        ctx = {int(k): v for k, v in json.loads(CONTEXT_FILE.read_text())["context"].items()}
    else:
        log.warning("context.json absent — comorbidities/AKI empty (run build_context first)")

    adm, pat, icu = mimic_link.load_core(mimic_link.mimic_root())
    adm_by_hadm, pat_by_subj, icu_agg = mimic_link.build_index(adm, pat, icu)
    log.info(f"MIMIC core: adm={len(adm)} pat={len(pat)} icu={len(icu)}")

    episodes, n_elig = [], 0
    for h, meta in idx.items():
        h = int(h)
        index_time = pd.Timestamp(meta["index_time"])
        c = ctx.get(h, {})
        rec = {"hadm_id": h, "arm": meta["arm"], "pci_vessels": meta.get("pci_vessels", "n/a"),
               "index_time": meta["index_time"], "ttp_hours": meta.get("ttp_hours"),
               "comorbidities": c.get("comorbidities", {}),
               "n_comorbidities": c.get("n_comorbidities"),
               "aki": c.get("outcomes", {}).get("aki", {}).get("aki"),
               "aki_stage": c.get("outcomes", {}).get("aki", {}).get("aki_stage")}
        if h in adm_by_hadm.index:
            out = mimic_link.link_episode(h, index_time, adm_by_hadm, pat_by_subj, icu_agg)
            rec.update(out)
            d2d = out.get("days_index_to_death")
            rec["eligible"] = bool(d2d is None or d2d > 0)     # alive at time-zero
            n_elig += int(rec["eligible"])
        else:
            rec["_linked"] = False
            rec["eligible"] = None
        episodes.append(rec)

    arm_sizes = {a: sum(1 for e in episodes if e["arm"] == a) for a in ARMS}
    OUT.write_text(json.dumps({
        "task": "multiarm_revascularization_cohort", "arms": ARMS,
        "n": len(episodes), "n_eligible": n_elig, "arm_sizes": arm_sizes,
        "episodes": episodes}, indent=2))
    log.info(f"Wrote {OUT}: arms {arm_sizes}, eligible {n_elig}/{len(episodes)}")

    df = pd.DataFrame([e for e in episodes if e.get("eligible")])
    if len(df):
        log.info("Per-arm composition (eligible; overlap sanity):")
        for a in ARMS:
            g = df[df["arm"] == a]
            if not len(g):
                continue
            age = g["age"].dropna() if "age" in g else pd.Series([], dtype=float)
            log.info(f"  {a:8s} n={len(g):4d}  age={age.mean():.0f}  "
                     f"comorbid={g['n_comorbidities'].dropna().mean():.1f}  "
                     f"readmit30={g['readmission_30d'].mean():.3f}  "
                     f"AKI={g['aki'].dropna().mean():.3f}  "
                     f"30d_mort={g['mortality_30d'].mean():.3f}  "
                     f"icu_los={g['icu_los_days'].mean():.1f}")


if __name__ == "__main__":
    main()
