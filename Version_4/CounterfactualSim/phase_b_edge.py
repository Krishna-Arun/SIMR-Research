#!/usr/bin/env python3
"""
phase_b_edge.py — is there a WITHIN-ARM equipoise question with a bigger, cleaner
edge than the cross-arm comparisons?

Cross-type comparisons (Phase A) mixed good overlap with poor clinical meaning.
The cleaner targets are decisions clinicians genuinely split on for the SAME
patient type — which is exactly what the landmark ICU RCTs randomized:

  • TRANSFUSION THRESHOLD  (TRICC / TRISS): restrictive (~Hb 7) vs liberal (~Hb 9).
    Decision variable = the hemoglobin at which the patient was transfused
    (last Hb before the transfusion anchor). Equipoise band ≈ Hb 7–9.

  • DIALYSIS TIMING  (STARRT-AKI / AKIKI): early vs late RRT initiation.
    Decision variable = time from hospital admission to the dialysis anchor.
    Equipoise ≈ patients not started immediately nor extremely late.

We measure, for each: is there real SPREAD in the decision variable (i.e. clinicians
actually disagreed), and how many patients sit in the equipoise band? A within-arm
question with spread + a populated equipoise band is a better, RCT-validatable target
than the cross-arm counterfactuals.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
LONG = HERE.parent / "Longitudinal"
COHORT = LONG / "cohort_data"
HB_ITEM = 51222        # Hemoglobin


def _parse(s):
    if s is None:
        return None
    s = str(s).replace("T", " ")[:19]
    for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, f)
        except ValueError:
            continue
    return None


def _pct(a):
    a = np.asarray(a, float)
    return f"n={len(a)} min={a.min():.1f} p25={np.percentile(a,25):.1f} med={np.median(a):.1f} p75={np.percentile(a,75):.1f} max={a.max():.1f}"


def main():
    ctx = json.load(open(LONG / "longitudinal_contexts.json"))["contexts"]
    by_fam = {"transfusion": [], "dialysis": []}
    for c in ctx:
        fam = c["anchor"]["family"]
        if fam in by_fam:
            by_fam[fam].append((str(c["subject_id"]), _parse(c["anchor"]["time"]),
                                c.get("hadm_id")))

    labs = pd.read_parquet(COHORT / "labs.parquet")
    hb = labs[labs.itemid == HB_ITEM].dropna(subset=["valuenum"]).copy()
    hb["ct"] = pd.to_datetime(hb.charttime)
    hb_by_sub = {str(s): g.sort_values("ct") for s, g in hb.groupby("subject_id")}
    adm = pd.read_parquet(COHORT / "admissions.parquet")
    admit_by_hadm = {int(r.hadm_id): _parse(str(r.admittime)) for r in adm.itertuples()}

    # ── TRANSFUSION THRESHOLD ────────────────────────────────────────────────
    print("=" * 74)
    print("TRANSFUSION THRESHOLD  (TRICC/TRISS: restrictive Hb~7 vs liberal Hb~9)")
    print("=" * 74)
    trig = []
    for sid, atime, _ in by_fam["transfusion"]:
        if atime is None or sid not in hb_by_sub:
            continue
        g = hb_by_sub[sid]
        pre = g[g.ct <= pd.Timestamp(atime)]
        if len(pre):
            trig.append(float(pre.valuenum.iloc[-1]))         # last Hb before transfusion
    trig = np.array(trig)
    if len(trig):
        restr = int((trig < 7).sum()); equi = int(((trig >= 7) & (trig <= 9)).sum())
        lib = int((trig > 9).sum())
        print(f"  trigger Hb (g/dL): {_pct(trig)}")
        print(f"  restrictive (<7): {restr}   EQUIPOISE [7-9]: {equi}   liberal (>9): {lib}")
        print(f"  -> {100*equi/len(trig):.0f}% sit in the equipoise band where TRICC/TRISS disagree; "
              f"spread {'PRESENT' if trig.std()>0.7 else 'weak'} (std {trig.std():.2f})")

    # ── DIALYSIS TIMING ──────────────────────────────────────────────────────
    print("\n" + "=" * 74)
    print("DIALYSIS TIMING  (STARRT-AKI/AKIKI: early vs late RRT initiation)")
    print("=" * 74)
    hours = []
    for sid, atime, hadm in by_fam["dialysis"]:
        if atime is None or hadm is None:
            continue
        at0 = admit_by_hadm.get(int(hadm))
        if at0 is None:
            continue
        h = (atime - at0).total_seconds() / 3600.0
        if h >= 0:
            hours.append(h)
    hours = np.array(hours)
    if len(hours):
        early = int((hours < 48).sum()); late = int((hours >= 48).sum())
        print(f"  hours admit->dialysis: {_pct(hours)}")
        print(f"  early (<48h): {early}   late (>=48h): {late}")
        print(f"  -> both sides populated: {'YES' if min(early,late)>=8 else 'thin'}; "
              f"timing spread {'PRESENT' if hours.std()>24 else 'weak'} (std {hours.std():.0f}h)")

    print("\n" + "-" * 74)
    print("[phase B] verdict: a within-arm question is viable where the decision variable")
    print("          has spread AND a populated equipoise band — that is the RCT-validatable")
    print("          target with naturally good overlap (same patient type, split decision).")


if __name__ == "__main__":
    main()
