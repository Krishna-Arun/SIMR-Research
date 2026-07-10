"""Stage 2b.2 — encode patients with the frozen official CLMBR via femr + Athena ontology.

Pipeline:
  MEDS dataset (build_meds.py)  +  Athena OMOP ontology  +  trajectory event times (Stage 1)
      -> femr.models.transformer.compute_features(clmbr-t-base)  -> 768-d state per timepoint
      -> reassembled into the SAME schema as the GRU encoder's encoded_states.pkl, so the world
         model / simulator / benchmark / RL consume CLMBR states unchanged.

The CLMBR tokenizer maps each MIMIC code into its pretrained OMOP/SNOMED vocabulary **via the
ontology built from the Athena vocabulary** — which is why Athena is required (codes that cannot be
mapped become unknown and contribute little signal).

Output: data/encoded_states_clmbr.pkl   (list of {patient_id, s:[T,768], action_ids, hours, outcomes})

Run inside clmbr311 (GPU recommended):
    python models/encode_clmbr.py configs/default.yaml
"""
from __future__ import annotations

import glob
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.common import load_config, get_logger, load_pickle, save_pickle

log = get_logger("encode_clmbr")

ATHENA_HELP = """
================================================================================
 Athena OMOP vocabulary not found at: {path}
 The CLMBR encoder cannot map MIMIC codes without it. To obtain it (one-time):
   1. Create a free account at https://athena.ohdsi.org/
   2. Download a vocabulary bundle including at least: SNOMED, ICD9CM, ICD10CM,
      ICD9Proc, ICD10PCS, RxNorm, NDC, LOINC, CPT4, ATC, OMOP Extension.
   3. Unzip it; run the included CPT4 reconstitution (cpt.sh / cpt4.jar) so CONCEPT.csv is complete.
   4. Point data.athena_path in the config at the unzipped folder (it must contain CONCEPT.csv,
      CONCEPT_RELATIONSHIP.csv, CONCEPT_ANCESTOR.csv, ...).
 The GRU encoder path (encoder.kind: gru) needs none of this.
================================================================================
"""


def load_meds_dataset(meds_dir: str):
    import datasets
    files = sorted(glob.glob(os.path.join(meds_dir, "data", "*.parquet")))
    if not files:
        raise FileNotFoundError(f"no MEDS parquet under {meds_dir}/data — run build_meds.py first")
    log.info("loading MEDS dataset from %d parquet shard(s)", len(files))
    return datasets.Dataset.from_parquet(files)


def to_nested_dataset(flat_ds):
    """Regroup flat MEDS 0.2 (events=[{time,code,numeric_value,...}]) into the nested schema femr
    0.2.3 expects (events=[{time, measurements:[{code, numeric_value}]}]), grouping by timestamp.

    Preserves every code (incl. the birth event that femr.pat_utils.get_patient_birthdate needs).
    """
    import datasets
    records = []
    for row in flat_ds:
        groups = {}
        order = []
        for e in row["events"]:
            t = e["time"]
            if t not in groups:
                groups[t] = []
                order.append(t)
            m = {"code": e["code"], "numeric_value": e.get("numeric_value")}
            groups[t].append(m)
        events = [{"time": t, "measurements": groups[t]} for t in order]
        records.append({"patient_id": int(row["patient_id"]), "events": events})
    log.info("regrouped %d patients into nested schema", len(records))
    return datasets.Dataset.from_list(records)


def build_labels(trajectories: list):
    """One femr label per trajectory event time (so CLMBR states align with the GRU substrate)."""
    import meds
    labels = []
    for t in trajectories:
        pid = int(t["patient_id"])
        for e in t["events"]:
            pt = e["t"]
            labels.append(meds.Label(patient_id=pid, prediction_time=pt, boolean_value=True))
    log.info("built %d labels across %d patients", len(labels), len(trajectories))
    return labels


def reassemble(result: dict, trajectories: list) -> list:
    """Group CLMBR features by patient, sort by time, attach action_ids/hours/outcomes from Stage 1."""
    pids = np.asarray(result["patient_ids"]).astype(int)
    times = np.asarray(result["feature_times"])            # datetime64
    feats = np.asarray(result["features"]).astype(np.float32)

    # per-patient time -> action_id map + outcomes, from the trajectory
    by_pid = {int(t["patient_id"]): t for t in trajectories}

    order = np.lexsort((times, pids))
    pids, times, feats = pids[order], times[order], feats[order]

    encoded = []
    for pid in np.unique(pids):
        m = pids == pid
        ts, fs = times[m], feats[m]
        traj = by_pid.get(int(pid))
        if traj is None or len(ts) < 2:
            continue
        # nearest trajectory event per feature time -> action id; hours from feature times
        ev_times = np.array([np.datetime64(e["t"]) for e in traj["events"]])
        ev_actions = np.array([e["action_id"] for e in traj["events"]], dtype=np.int64)
        idx = np.clip(np.searchsorted(ev_times, ts), 0, len(ev_times) - 1)
        action_ids = ev_actions[idx]
        hours = ((ts - ts[0]) / np.timedelta64(1, "h")).astype(np.float32)
        # keep the ABSOLUTE feature times so downstream stages (enriched actions,
        # lab-value alignment) can join against the raw MIMIC event tables exactly,
        # instead of guessing wall-clock from relative hours.
        abs_times = ts.astype("datetime64[s]")
        encoded.append({"patient_id": int(pid), "s": fs.astype(np.float32),
                        "action_ids": action_ids, "hours": hours,
                        "abs_times": abs_times,
                        "outcomes": traj["outcomes"]})
    return encoded


def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "configs/default.yaml"
    cfg = load_config(cfg_path)
    out_dir = cfg["data"]["out_dir"]
    athena_path = cfg["data"]["athena_path"]
    model_name = cfg["encoder"]["clmbr_model"]

    if not (os.path.isdir(athena_path) and os.path.exists(os.path.join(athena_path, "CONCEPT.csv"))):
        log.error(ATHENA_HELP.format(path=athena_path))
        sys.exit(2)

    import torch
    import femr.ontology
    import femr.models.transformer

    trajectories = load_pickle(os.path.join(out_dir, "trajectories.pkl"))
    dataset = to_nested_dataset(load_meds_dataset(cfg["data"]["meds_dir"]))
    labels = build_labels(trajectories)

    log.info("building femr ontology from Athena: %s", athena_path)
    ontology = femr.ontology.Ontology(athena_path)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log.info("computing CLMBR features on %s (this can take a while)...", device)
    # num_proc=1: the in-memory ontology is large; forking workers OOMs on a small allocation.
    result = femr.models.transformer.compute_features(
        dataset=dataset, model_path=model_name, labels=labels,
        num_proc=1, tokens_per_batch=2048, device=device, ontology=ontology)
    log.info("compute_features -> %d feature vectors, dim=%d",
             len(result["features"]), np.asarray(result["features"]).shape[-1])

    encoded = reassemble(result, trajectories)
    save_pickle(encoded, os.path.join(out_dir, "encoded_states_clmbr.pkl"))
    assert encoded and encoded[0]["s"].shape[1] == cfg["encoder"]["clmbr_dim"], \
        "unexpected CLMBR feature dim"
    log.info("STAGE2b_OK: %d patients encoded with frozen CLMBR (dim=%d) -> encoded_states_clmbr.pkl",
             len(encoded), encoded[0]["s"].shape[1])


if __name__ == "__main__":
    main()
