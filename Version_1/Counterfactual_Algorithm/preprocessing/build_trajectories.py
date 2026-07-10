"""Stage 1 — build per-patient chronological event sequences from MIMIC-IV.

Output (``data/trajectories.pkl``): a list of patient dicts
    {
      "patient_id": int,
      "static": {"gender": str, "anchor_age": float},
      "events": [ {"t": Timestamp, "hours": float, "type": str, "code": str,
                   "value": float|None, "action": str, "action_id": int}, ... ],   # time-sorted
      "outcomes": {"mortality": 0/1, "n_icu_stays": int, "max_los_days": float,
                   "n_admissions": int},
    }
plus ``data/trajectory_stats.json`` (summary) and ``data/action_vocab.json``.

Time discretization: events are kept at their native timestamps and ordered into discrete
*event steps*; ``hours`` is the offset from each patient's first event. (A daily-bin helper is
provided for the GRU path that wants fixed steps.) This event-step view aligns with how CLMBR
consumes timelines.

Run:  python preprocessing/build_trajectories.py [config.yaml]
Research environment only — not a clinical tool.
"""
from __future__ import annotations

import os
import sys
from collections import Counter

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.common import load_config, get_logger, save_pickle, save_json, set_seed
from preprocessing.load_mimic import load_all
from preprocessing.actions import ActionVocab, event_to_action

log = get_logger("build_traj")


def _long_events(tables: dict, cfg: dict) -> pd.DataFrame:
    """Flatten all source tables into one long frame: subject_id,time,type,code,value."""
    frames = []
    adm = tables["admissions"]

    # admission + discharge markers
    if len(adm):
        a = adm[["subject_id", "admittime"]].dropna(subset=["admittime"]).copy()
        a["type"], a["code"], a["value"] = "admission", "ADMISSION", np.nan
        a = a.rename(columns={"admittime": "time"})
        frames.append(a[["subject_id", "time", "type", "code", "value"]])

        d = adm[["subject_id", "dischtime"]].dropna(subset=["dischtime"]).copy()
        d["type"], d["code"], d["value"] = "discharge", "DISCHARGE", np.nan
        d = d.rename(columns={"dischtime": "time"})
        frames.append(d[["subject_id", "time", "type", "code", "value"]])

    # diagnoses: no native time -> attach admission admittime (avoids discharge leakage)
    dx = tables["diagnoses_icd"]
    if len(dx) and len(adm):
        amap = adm[["hadm_id", "admittime"]].dropna(subset=["admittime"])
        dxm = dx.merge(amap, on="hadm_id", how="inner")
        dxm["type"] = "diagnosis"
        dxm["code"] = ("ICD" + dxm["icd_version"].astype(str) + "_" + dxm["icd_code"].astype(str))
        dxm["value"] = np.nan
        dxm = dxm.rename(columns={"admittime": "time"})
        frames.append(dxm[["subject_id", "time", "type", "code", "value"]])

    # procedures: chartdate
    pr = tables["procedures_icd"]
    if len(pr) and "chartdate" in pr.columns:
        prm = pr.dropna(subset=["chartdate"]).copy()
        prm["type"] = "procedure"
        prm["code"] = prm["icd_code"].astype(str)   # raw code (action mapping needs it)
        prm["value"] = np.nan
        prm = prm.rename(columns={"chartdate": "time"})
        frames.append(prm[["subject_id", "time", "type", "code", "value"]])

    # prescriptions: starttime, drug name
    rx = tables["prescriptions"]
    if len(rx) and "starttime" in rx.columns:
        rxm = rx.dropna(subset=["starttime"]).copy()
        rxm["type"] = "drug"
        rxm["code"] = rxm["drug"].astype(str)
        rxm["value"] = np.nan
        rxm = rxm.rename(columns={"starttime": "time"})
        frames.append(rxm[["subject_id", "time", "type", "code", "value"]])

    # labs: charttime, itemid, valuenum
    lab = tables["labevents"]
    if len(lab) and "charttime" in lab.columns:
        labm = lab.dropna(subset=["charttime"]).copy()
        labm["type"] = "lab"
        labm["code"] = "LAB_" + labm["itemid"].astype(str)
        labm["value"] = pd.to_numeric(labm.get("valuenum"), errors="coerce")
        labm = labm.rename(columns={"charttime": "time"})
        frames.append(labm[["subject_id", "time", "type", "code", "value"]])

    if not frames:
        return pd.DataFrame(columns=["subject_id", "time", "type", "code", "value"])
    ev = pd.concat(frames, ignore_index=True)
    ev = ev.dropna(subset=["time"])
    ev = ev.sort_values(["subject_id", "time"], kind="mergesort").reset_index(drop=True)
    return ev


def _outcomes(tables: dict, sid: int) -> dict:
    adm = tables["admissions"]
    pts = tables["patients"]
    icu = tables["icustays"]
    a = adm[adm["subject_id"] == sid] if len(adm) else adm
    mortality = 0
    if len(a) and "hospital_expire_flag" in a.columns:
        mortality = int((a["hospital_expire_flag"] == 1).any())
    if not mortality and len(pts):
        p = pts[pts["subject_id"] == sid]
        if len(p) and "dod" in p.columns:
            mortality = int(p["dod"].notna().any())
    n_icu = int((icu["subject_id"] == sid).sum()) if len(icu) else 0
    max_los = float(icu[icu["subject_id"] == sid]["los"].max()) if (len(icu) and n_icu) else 0.0
    if not np.isfinite(max_los):
        max_los = 0.0
    return {"mortality": mortality, "n_icu_stays": n_icu,
            "max_los_days": round(max_los, 3), "n_admissions": int(len(a))}


def build(cfg: dict) -> list:
    tables = load_all(cfg)
    ev = _long_events(tables, cfg)
    log.info("flattened %d total events across %d patients",
             len(ev), ev["subject_id"].nunique() if len(ev) else 0)

    vocab = ActionVocab()
    pts = tables["patients"].set_index("subject_id") if len(tables["patients"]) else None
    min_ev = cfg["preprocess"]["min_events_per_patient"]
    cap = cfg["preprocess"]["max_labs_per_patient"]

    trajectories = []
    for sid, grp in ev.groupby("subject_id", sort=True):
        grp = grp.sort_values("time", kind="mergesort")
        if cap and len(grp) > cap:
            grp = grp.iloc[:cap]
        if len(grp) < min_ev:
            continue
        t0 = grp["time"].iloc[0]
        events = []
        for _, r in grp.iterrows():
            e = {
                "t": r["time"],
                "hours": float((r["time"] - t0).total_seconds() / 3600.0),
                "type": r["type"],
                "code": str(r["code"]),
                "value": (None if pd.isna(r["value"]) else float(r["value"])),
            }
            grp_name = event_to_action(e)
            e["action"] = grp_name
            e["action_id"] = vocab.to_id(grp_name)
            events.append(e)

        static = {"gender": None, "anchor_age": None}
        if pts is not None and sid in pts.index:
            row = pts.loc[sid]
            static = {"gender": str(row.get("gender")),
                      "anchor_age": (None if pd.isna(row.get("anchor_age"))
                                     else float(row.get("anchor_age")))}

        trajectories.append({
            "patient_id": int(sid),
            "static": static,
            "events": events,
            "outcomes": _outcomes(tables, sid),
        })

    log.info("built %d trajectories (>= %d events)", len(trajectories), min_ev)
    return trajectories, vocab


def summarize(trajectories: list, vocab: ActionVocab) -> dict:
    n = len(trajectories)
    lens = [len(t["events"]) for t in trajectories]
    type_ctr, act_ctr = Counter(), Counter()
    mort = 0
    for t in trajectories:
        mort += t["outcomes"]["mortality"]
        for e in t["events"]:
            type_ctr[e["type"]] += 1
            if e["action_id"] != 0:
                act_ctr[e["action"]] += 1
    return {
        "n_patients": n,
        "events_per_patient": {
            "min": int(min(lens)) if lens else 0,
            "max": int(max(lens)) if lens else 0,
            "mean": round(float(np.mean(lens)), 1) if lens else 0,
            "median": int(np.median(lens)) if lens else 0,
        },
        "total_events": int(sum(lens)),
        "event_type_counts": dict(type_ctr),
        "intervention_action_counts": dict(act_ctr.most_common()),
        "n_action_groups": vocab.n_actions,
        "mortality_rate": round(mort / n, 3) if n else 0,
    }


def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "configs", "default.yaml")
    cfg = load_config(cfg_path)
    set_seed(cfg.get("seed", 0))
    out_dir = cfg["data"]["out_dir"]

    trajectories, vocab = build(cfg)
    save_pickle(trajectories, os.path.join(out_dir, "trajectories.pkl"))
    stats = summarize(trajectories, vocab)
    save_json(stats, os.path.join(out_dir, "trajectory_stats.json"))
    save_json({"groups": vocab.groups, "n_actions": vocab.n_actions},
              os.path.join(out_dir, "action_vocab.json"))

    log.info("saved -> %s/trajectories.pkl", out_dir)
    log.info("stats: %s", stats)

    # ---- verification asserts (Stage 1 success criteria) ----
    assert len(trajectories) > 0, "no trajectories built"
    for t in trajectories[:50]:
        hs = [e["hours"] for e in t["events"]]
        assert all(hs[i] <= hs[i + 1] + 1e-6 for i in range(len(hs) - 1)), \
            f"events not time-sorted for patient {t['patient_id']}"
    log.info("STAGE1_OK: %d patients, %d events", stats["n_patients"], stats["total_events"])


if __name__ == "__main__":
    main()
