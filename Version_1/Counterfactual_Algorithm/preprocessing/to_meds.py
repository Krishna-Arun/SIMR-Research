"""Stage 2b (scaffold) — MIMIC-IV -> MEDS for the official CLMBR (femr) encoder.

The frozen CLMBR (StanfordShahLab/clmbr-t-base) consumes patients in the MEDS schema with codes in
the OMOP/SNOMED space and a pretrained tokenizer dictionary. The production path (see the Stanford
`som-shahlab/mimic_tutorial`) is:

    # 1. install the stack (done by jobs/clmbr_smoke.sbatch -> clmbr311 venv)
    #      meds_etl[cpp]==0.2.3  meds_reader==0.0.6  femr==0.2.3  xformers  torch
    # 2. convert raw MIMIC-IV -> MEDS
    meds_etl_mimic  <MIMIC_ROOT>  <OUT>/mimic-meds  --num_proc 16 --num_shards 16 --backend cpp
    # 3. convert MEDS -> meds_reader
    meds_reader_convert  <OUT>/mimic-meds  <OUT>/mimic-meds-reader  --num_threads 16
    # 4. Athena OMOP vocabulary (USER ACTION: free OHDSI account download from athena.ohdsi.org,
    #    run the bundled CPT4 fixer) -> needed so CLMBR can map codes to its pretrained tokens.
    # 5. encode with models.encoder.CLMBRFemrEncoder (see Stage 0 smoke for the call shape).

==> BLOCKERS (flagged in the plan, not silently assumed):
    (a) Athena OMOP vocabulary requires a manual OHDSI download (only the user can do this).
    (b) meds_etl_mimic expects the standard MIMIC directory layout; the demo (plain .csv.gz, v2.2)
        must be validated against it.
The GRU encoder path needs NONE of this and is the default until the above are in place.

This module also provides a MINIMAL in-memory MEDS builder for quick single-patient experiments
(NOT a substitute for meds_etl_mimic — the code space is approximate and will not match CLMBR's
pretrained vocabulary for most codes).
"""
from __future__ import annotations

import datetime
from typing import List

# Coarse, APPROXIMATE map from our event types to OMOP-style codes for in-memory experiments only.
# Real conversion uses meds_etl_mimic + Athena; do not rely on this for quantitative results.
_VISIT_CODE = "Visit/IP"


def trajectory_to_meds(traj: dict) -> dict:
    """Best-effort MEDS-schema patient from a Stage-1 trajectory dict (APPROXIMATE codes).

    Returns {'patient_id', 'events': [{'time': datetime, 'measurements': [{'code', 'numeric_value'?}]}]}
    grouped by timestamp. Use only for plumbing/smoke experiments with femr.
    """
    by_time = {}
    for e in traj["events"]:
        t = e["t"]
        if not isinstance(t, datetime.datetime):
            t = datetime.datetime.fromisoformat(str(t))
        key = t.replace(microsecond=0)
        meas = by_time.setdefault(key, [])
        if e["type"] in ("admission", "discharge"):
            meas.append({"code": _VISIT_CODE})
        elif e["type"] == "diagnosis":
            meas.append({"code": e["code"]})                 # e.g. ICD10_I21 (approx; not SNOMED)
        elif e["type"] == "procedure":
            meas.append({"code": f"PROC/{e['code']}"})
        elif e["type"] == "drug":
            meas.append({"code": f"DRUG/{e['code']}"})
        elif e["type"] == "lab":
            m = {"code": e["code"]}
            if e.get("value") is not None:
                m["numeric_value"] = float(e["value"])
            meas.append(m)
    events = [{"time": k, "measurements": v} for k, v in sorted(by_time.items())]
    return {"patient_id": int(traj["patient_id"]), "events": events}


def trajectories_to_meds(trajectories: List[dict]) -> List[dict]:
    return [trajectory_to_meds(t) for t in trajectories]


if __name__ == "__main__":
    print(__doc__)
