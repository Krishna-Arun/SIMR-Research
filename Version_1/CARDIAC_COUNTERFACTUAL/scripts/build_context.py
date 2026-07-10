"""
build_context.py  —  pre-index clinical context for the BROAD 3-arm cohort.

The original build_dataset.py only kept troponin-dense admissions (good for the lab task, bad
for the multi-arm durable-outcome task where CABG/medical patients lack serial troponins). This
builds the chart context the LLM sees for EVERY cardiac admission, with a uniform, leak-free
index so the three arms are comparable:

  index = admittime + INDEX_OFFSET_H (default 24h)   ← the early-workup decision point
  context = presentation notes (safe) + FULL timestamped labs (charttime <= index) + microbiology
  + comorbidity vector

Output: data/context.json  keyed by hadm_id. build_multiarm_cohort.py supplies arm + outcomes;
the runner joins the two by hadm_id. Heavy (reads the full labs CSV) -> run via the sbatch.
"""

import json
import logging
import os
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

BENCH = Path(__file__).parent.parent
sys.path.insert(0, str(BENCH / "scripts"))
from cardiac_defs import (LABS_FILE, NOTES_FILE, MICRO_FILE, DIAG_FILE, COMORBIDITIES,
                           pre_labs_full, summarize_all_labs, summarize_micro,
                           build_comorbidity_vector, _clip)
import mimic_link

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

OUT = BENCH / "data" / "context.json"
INDEX_FILE = BENCH / "data" / "index.json"            # arm + time-zero from assign_index.py
AKI_WINDOW_H = int(os.environ.get("TASKC_AKI_WINDOW_H", str(7 * 24)))   # KDIGO 7-day window


def aki_from_creatinine(adm_labs, index):
    """KDIGO acute kidney injury from the creatinine series (the SECONDARY v1 outcome, and
    PCI's signature harm via contrast). baseline = lowest pre-index creatinine (best estimate
    of stable renal function); AKI = post-index rise >=0.3 mg/dL OR >=1.5x baseline within 7d.
    Stages: 1 (>=1.5x or +0.3), 2 (>=2x), 3 (>=3x or peak>=4.0)."""
    if adm_labs is None or len(adm_labs) == 0:
        return {"aki": None, "missing": True}
    cr = adm_labs[adm_labs["label"] == "Creatinine"].sort_values("charttime")
    if len(cr) == 0:
        return {"aki": None, "missing": True}
    dt = (cr["charttime"] - index).dt.total_seconds() / 3600.0
    pre = cr["valuenum"][dt <= 0]
    post = cr["valuenum"][(dt > 0) & (dt <= AKI_WINDOW_H)]
    if len(pre) == 0 or len(post) == 0:
        return {"aki": None, "missing": True, "n_pre": int(len(pre)), "n_post": int(len(post))}
    baseline = float(np.nanmin(pre.values))
    peak = float(np.nanmax(post.values))
    delta = peak - baseline
    ratio = peak / baseline if baseline > 0 else float("inf")
    aki = int(delta >= 0.3 or ratio >= 1.5)
    stage = 0
    if aki:
        stage = 3 if (ratio >= 3.0 or peak >= 4.0) else (2 if ratio >= 2.0 else 1)
    return {"aki": aki, "aki_stage": stage, "creatinine_baseline": round(baseline, 3),
            "creatinine_peak_post": round(peak, 3), "delta_creatinine": round(delta, 3),
            "n_pre": int(len(pre)), "n_post": int(len(post)), "missing": False}


def main():
    log.info(f"Loading time-zero from {INDEX_FILE.name} (procedure-time / matched-window index) ...")
    idx = json.loads(INDEX_FILE.read_text())["index"]
    index_by_hadm = {int(h): pd.Timestamp(v["index_time"]) for h, v in idx.items()}

    log.info("Loading diagnoses (comorbidities) ...")
    diag = pd.read_csv(DIAG_FILE, usecols=["hadm_id", "icd_code"], dtype={"icd_code": str})
    diag_by_hadm = diag.groupby("hadm_id")["icd_code"].apply(list).to_dict()
    universe = sorted(set(diag_by_hadm) & set(index_by_hadm))
    log.info(f"Cohort universe (cardiac admits with a time-zero): {len(universe)}")

    log.info("Loading full labs ...")
    labs = pd.read_csv(LABS_FILE, low_memory=False,
                       usecols=["hadm_id", "charttime", "valuenum", "valueuom", "label"])
    labs["charttime"] = pd.to_datetime(labs["charttime"], errors="coerce")
    labs = labs[labs["valuenum"].notna() & labs["charttime"].notna()]
    labs = labs[labs["hadm_id"].isin(universe)]
    labs_by = dict(tuple(labs.groupby("hadm_id")))

    log.info("Loading admission notes (safe presentation fields) ...")
    notes = pd.read_csv(NOTES_FILE, low_memory=False,
                        usecols=["hadm_id", "HPI", "physical_exam", "chief_complaint"])
    notes_by = {int(r["hadm_id"]): {"chief_complaint": _clip(r.get("chief_complaint", ""), 300),
                                    "hpi": _clip(r.get("HPI", ""), 1800),
                                    "physical_exam": _clip(r.get("physical_exam", ""), 1800)}
                for _, r in notes.iterrows() if pd.notna(r["hadm_id"])}

    log.info("Loading microbiology ...")
    micro = pd.read_csv(MICRO_FILE, low_memory=False,
                        usecols=["hadm_id", "charttime", "chartdate", "spec_type_desc",
                                 "test_name", "org_name", "interpretation"])
    micro["charttime"] = pd.to_datetime(micro["charttime"].fillna(micro["chartdate"]), errors="coerce")
    micro = micro[micro["charttime"].notna() & micro["hadm_id"].isin(universe)]
    micro_by = dict(tuple(micro.groupby("hadm_id")))

    log.info(f"Building context for {len(universe)} admissions (index = procedure-time / matched-window) ...")
    context = {}
    n_labs = 0
    for i, h in enumerate(universe):
        index = index_by_hadm[h]
        adm_labs = labs_by.get(h)
        cc = {**notes_by.get(int(h), {"chief_complaint": "", "hpi": "", "physical_exam": ""}),
              "labs_all": summarize_all_labs(adm_labs, index),
              "labs_full": pre_labs_full(adm_labs, index),
              "microbiology": summarize_micro(micro_by.get(h), index)}
        comorbid = build_comorbidity_vector(diag_by_hadm.get(h, []))
        n_labs += sum(len(v) for v in cc["labs_full"].values())
        context[str(int(h))] = {"hadm_id": int(h), "index_time": index.isoformat(),
                                "clinical_context": cc, "comorbidities": comorbid,
                                "n_comorbidities": int(sum(comorbid.values())),
                                "outcomes": {"aki": aki_from_creatinine(adm_labs, index)}}
        if (i + 1) % 1000 == 0:
            log.info(f"  {i + 1}/{len(universe)}")

    aki_vals = [c["outcomes"]["aki"].get("aki") for c in context.values()]
    n_aki_scorable = sum(1 for v in aki_vals if v is not None)
    n_aki_pos = sum(1 for v in aki_vals if v == 1)
    OUT.write_text(json.dumps({
        "benchmark": "multiarm_context_v1",
        "index_source": "assign_index (procedure-time / matched-window)", "aki_window_h": AKI_WINDOW_H,
        "n_admissions": len(context),
        "avg_pre_index_labs": round(n_labs / max(len(context), 1), 1),
        "aki_scorable": n_aki_scorable, "aki_positive": n_aki_pos,
        "context": context,
    }, indent=2))
    log.info(f"Wrote {OUT}  ({len(context)} admissions, avg {n_labs/max(len(context),1):.0f} pre-index labs each)")
    log.info(f"AKI scorable: {n_aki_scorable}/{len(context)}  AKI-positive: {n_aki_pos} "
             f"({100*n_aki_pos/max(n_aki_scorable,1):.1f}% of scorable)")


if __name__ == "__main__":
    main()
