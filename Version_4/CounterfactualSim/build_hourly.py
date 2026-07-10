#!/usr/bin/env python3
"""
build_hourly.py — hourly (STATE, ACTION) time series for the CAD ICU cohort, the proper
world-model substrate (user spec):

  STATE(t)  = vitals + labs (LOCF) + cumulative prior procedures   [patient status at hour t]
  ACTION(t) = drugs administered during hour t                     [the intervention]

First 72 hours per ICU stay (bounds compute; matches the CF horizon). Heavy scans
(chartevents 3.3G, labevents 2.4G) are cached to parquet so re-runs are cheap.
Output: hourly_substrate.pkl  ->  per-stay {Z:[T,state_dim], A:[T,action_dim], hours, ...}
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/2physionet.org/files/mimiciv/3.1")
ICU, HOSP = ROOT / "icu", ROOT / "hosp"
HERE = Path(__file__).resolve().parent
COH = HERE / "cad_cohort_full.parquet"
HMAX = 72

VITALS = {220045: "hr", 220050: "sbp", 220051: "dbp", 220052: "map",
          220210: "rr", 220277: "spo2", 223761: "temp_f", 223762: "temp_c"}
LABS = {50912: "creatinine", 51222: "hemoglobin", 51221: "hematocrit", 51265: "platelet",
        51301: "wbc", 50983: "sodium", 50971: "potassium", 50882: "bicarbonate",
        51006: "bun", 50931: "glucose", 51003: "troponin_t", 50963: "ntprobnp"}
DRUGS = {221906: "norepi", 221289: "epi", 221749: "phenyleph", 222315: "vasopressin",
         221662: "dopamine", 221653: "dobutamine", 222168: "propofol", 221744: "fentanyl",
         225152: "heparin", 221794: "furosemide", 223258: "insulin"}
# cumulative prior-procedure flags in STATE (set to 1 from the hour started onward)
PROCS = {"proc_vent": [225792, 225794, 225303, 224385],       # any ventilation/intubation
         "proc_dialysis": [225802, 225803, 225809]}           # any RRT/CRRT
PROC_ITEMS = {i for v in PROCS.values() for i in v}


def _hour(t, t0):
    return int((t - t0).total_seconds() // 3600)


def scan_events(path, itemids, cols, val="valuenum", cache=None):
    """Chunk-scan a big events table, keep rows whose itemid∈itemids and stay in cohort."""
    if cache and cache.exists():
        print(f"  [cache] {cache.name}"); return pd.read_parquet(cache)
    keep, n = [], 0
    for ch in pd.read_csv(path, chunksize=2_000_000, usecols=cols):
        n += len(ch)
        ch = ch[ch.itemid.isin(itemids)].dropna(subset=[val])
        ch = ch[ch.stay_id.isin(STAYS)] if "stay_id" in ch else ch[ch.hadm_id.isin(HADMS)]
        if len(ch):
            keep.append(ch)
        print(f"\r  scanned {n:,}, kept {sum(len(k) for k in keep):,}", end="")
    print()
    out = pd.concat(keep, ignore_index=True)
    if cache:
        out.to_parquet(cache)
    return out


def main():
    coh = pd.read_parquet(COH)
    ic = pd.read_csv(ICU / "icustays.csv.gz", usecols=["hadm_id", "stay_id", "intime"])
    ic = ic[ic.hadm_id.isin(set(coh.hadm_id.astype("int64")))].copy()
    ic["intime"] = pd.to_datetime(ic.intime)
    global STAYS, HADMS
    STAYS = set(ic.stay_id); HADMS = set(ic.hadm_id)
    t0 = dict(zip(ic.stay_id, ic.intime)); s2h = dict(zip(ic.stay_id, ic.hadm_id))
    print(f"[hourly] {len(STAYS):,} CAD ICU stays, first {HMAX}h each")

    print("[hourly] vitals (chartevents 3.3G) …")
    v = scan_events(ICU / "chartevents.csv.gz", set(VITALS),
                    ["stay_id", "charttime", "itemid", "valuenum"], cache=HERE / "_hv.parquet")
    print("[hourly] drugs (inputevents) …")
    dcols = ["stay_id", "starttime", "endtime", "itemid", "rate", "amount"]
    di = pd.read_csv(ICU / "inputevents.csv.gz", usecols=dcols)
    di = di[di.itemid.isin(DRUGS) & di.stay_id.isin(STAYS)].copy()
    print(f"  drug rows: {len(di):,}")
    print("[hourly] procedures (procedureevents) …")
    pe = pd.read_csv(ICU / "procedureevents.csv.gz", usecols=["stay_id", "starttime", "itemid"])
    pe = pe[pe.itemid.isin(PROC_ITEMS) & pe.stay_id.isin(STAYS)].copy()
    pe["starttime"] = pd.to_datetime(pe.starttime)
    print(f"  procedure rows: {len(pe):,}")
    print("[hourly] labs (labevents 2.4G, by hadm) …")
    lv = scan_events(HOSP / "labevents.csv.gz", set(LABS),
                     ["hadm_id", "charttime", "itemid", "valuenum"], cache=HERE / "_hl.parquet")

    # ---- assemble per-stay hourly tensors ----
    v["charttime"] = pd.to_datetime(v.charttime)
    v["stay_id"] = v.stay_id.astype("int64")
    lv["charttime"] = pd.to_datetime(lv.charttime); lv["hadm_id"] = lv.hadm_id.astype("int64")
    di["starttime"] = pd.to_datetime(di.starttime); di["endtime"] = pd.to_datetime(di.endtime)
    lab_by_hadm = {h: g for h, g in lv.groupby("hadm_id")}
    vit_by_stay = {s: g for s, g in v.groupby("stay_id")}
    drug_by_stay = {s: g for s, g in di.groupby("stay_id")}
    # earliest start-hour of each procedure group per stay
    proc_by_stay = {}
    for r in pe.itertuples():
        for pname, items in PROCS.items():
            if r.itemid in items:
                proc_by_stay.setdefault(r.stay_id, {}).setdefault(pname, r.starttime)
                if r.starttime < proc_by_stay[r.stay_id][pname]:
                    proc_by_stay[r.stay_id][pname] = r.starttime

    vit_cols = ["hr", "sbp", "dbp", "map", "rr", "spo2", "temp"]     # temp merged F/C -> C
    lab_cols = list(LABS.values())
    drug_cols = list(DRUGS.values())
    proc_cols = list(PROCS.keys())
    state_cols = vit_cols + lab_cols + proc_cols
    substrate = {}
    for si, sid in enumerate(STAYS):
        base = t0[sid]; hadm = s2h[sid]
        Z = np.full((HMAX, len(state_cols)), np.nan, "float32")
        for pc in proc_cols:                                         # procedures default 0 (not observed = not done)
            Z[:, state_cols.index(pc)] = 0.0
        A = np.zeros((HMAX, len(drug_cols)), "float32")
        # vitals -> hourly mean
        g = vit_by_stay.get(sid)
        if g is not None:
            g = g.assign(h=((g.charttime - base).dt.total_seconds() // 3600).astype(int))
            g = g[(g.h >= 0) & (g.h < HMAX)]
            for iid, name in VITALS.items():
                gg = g[g.itemid == iid]
                if not len(gg):
                    continue
                col = "temp" if name.startswith("temp") else name
                agg = gg.groupby("h").valuenum.mean()
                vals = agg.values.astype("float32")
                if name == "temp_f":
                    vals = (vals - 32) * 5 / 9
                Z[agg.index.values, state_cols.index(col)] = vals
        # labs -> LOCF onto the grid
        lg = lab_by_hadm.get(hadm)
        if lg is not None:
            lg = lg.assign(h=((lg.charttime - base).dt.total_seconds() // 3600).astype(int))
            for iid, name in LABS.items():
                gg = lg[(lg.itemid == iid) & (lg.h < HMAX)].sort_values("h")
                if not len(gg):
                    continue
                ci = state_cols.index(name)
                last = np.nan
                gi = {int(h): float(val) for h, val in zip(gg.h, gg.valuenum)}
                for hh in range(HMAX):
                    if hh in gi:
                        last = gi[hh]
                    Z[hh, ci] = last
        # drugs -> active per hour (rate if present else 1)
        dg = drug_by_stay.get(sid)
        if dg is not None:
            for r in dg.itertuples():
                h0 = max(0, _hour(r.starttime, base))
                h1 = _hour(r.endtime, base) if pd.notna(r.endtime) else h0
                h1 = min(HMAX - 1, h1)
                if h1 < 0 or h0 >= HMAX:
                    continue
                val = float(r.rate) if pd.notna(r.rate) and r.rate > 0 else 1.0
                A[h0:h1 + 1, drug_cols.index(DRUGS[r.itemid])] = np.maximum(
                    A[h0:h1 + 1, drug_cols.index(DRUGS[r.itemid])], val)
        # cumulative procedure flags: 1 from the start-hour onward
        for pname, st in proc_by_stay.get(sid, {}).items():
            hs = _hour(st, base)
            if hs < HMAX:
                Z[max(0, hs):, state_cols.index(pname)] = 1.0
        # keep stays with >= 6 hours of any vital signal
        valid_h = int((~np.isnan(Z[:, :len(vit_cols)]).all(1)).sum())
        if valid_h >= 6:
            substrate[int(sid)] = {"Z": Z, "A": A, "hadm_id": int(hadm), "valid_hours": valid_h}
        if si % 2000 == 0:
            print(f"\r  assembled {si:,}/{len(STAYS):,}", end="")
    print()
    meta = {"state_cols": state_cols, "drug_cols": drug_cols,
            "vit_cols": vit_cols, "lab_cols": lab_cols, "HMAX": HMAX}
    with open(HERE / "hourly_substrate.pkl", "wb") as f:
        pickle.dump({"stays": substrate, "meta": meta}, f)
    print(f"[hourly] saved hourly_substrate.pkl — {len(substrate):,} stays, "
          f"state_dim {len(state_cols)}, action_dim {len(drug_cols)}")
    # quick sanity
    ex = next(iter(substrate.values()))
    print(f"[hourly] example stay: Z {ex['Z'].shape}, A {ex['A'].shape}, valid_hours {ex['valid_hours']}")
    drug_use = np.mean([s["A"].sum(0) > 0 for s in substrate.values()], 0)
    print("[hourly] drug prevalence (frac stays ever on):",
          {d: round(float(p), 2) for d, p in zip(drug_cols, drug_use)})


if __name__ == "__main__":
    main()
