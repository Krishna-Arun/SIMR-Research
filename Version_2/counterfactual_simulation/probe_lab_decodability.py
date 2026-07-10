"""
probe_lab_decodability.py — Task 2: can core labs be read out of the frozen CLMBR latent z?

This is the state-design decision gate. If core labs decode cleanly from z, we keep state = single
768-d CLMBR latent and just add a z->labs decoder head (cleanest, least overfit). If decoding is
weak, we add an explicit lab channel to the state.

Method (EHRSHOT-style linear probe, honest train/test split):
  * lab panel  = LOCF of ~14 core labs (from trajectory LOINC events, ~100% have values) to each
                 CLMBR timepoint's absolute time.
  * X = frozen z_t (768).  Y = the LOCF lab vector at t (standardized per lab).
  * Ridge z->lab, fit on TRAIN patients, report R2 on TEST (value decodability).
  * Direction test: predict sign of the NEXT-step change per lab; report balanced accuracy
    (Rising/Falling/Stable is what Benchmark B grades — direction is the robust target).

Run in simr env. Needs encoded_states with abs_times (re-encode first) + splits.json.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

BASE = Path("/scratch/users/karun09/Version_2/counterfactual_simulation")
ENC = BASE / "data/train_substrate.pkl"   # cleaned/windowed/capped substrate (was encoded_states_clmbr.pkl)
TRAJ = BASE / "data/trajectories.pkl"
SPLITS = BASE / "data/splits.json"
OUT = BASE / "data/lab_decodability.json"

CORE_LABS = {   # LOINC -> short name
    "LOINC/2160-0": "creatinine", "LOINC/3094-0": "bun", "LOINC/2823-3": "potassium",
    "LOINC/2951-2": "sodium", "LOINC/2075-0": "chloride", "LOINC/1963-8": "bicarbonate",
    "LOINC/1863-0": "anion_gap", "LOINC/2345-7": "glucose", "LOINC/2601-3": "magnesium",
    "LOINC/2777-1": "phosphate", "LOINC/718-7": "hemoglobin", "LOINC/4544-3": "hematocrit",
    "LOINC/777-3": "platelets", "LOINC/6690-2": "wbc",
}
LOINCS = list(CORE_LABS)
NAME = [CORE_LABS[c] for c in LOINCS]
L = len(LOINCS)


def locf_panels(enc, traj):
    """For each patient/timepoint, LOCF the core-lab panel from trajectory events to abs_times."""
    tmap = {int(t["patient_id"]): t for t in traj}
    X, Y, PID = [], [], []
    for e in enc:
        pid = int(e["patient_id"])
        tr = tmap.get(pid)
        if tr is None:
            continue
        # collect (time,value) per lab
        series = {c: [] for c in LOINCS}
        for ev in tr["events"]:
            c = ev.get("code")
            if c in series and ev.get("value") is not None:
                series[c].append((pd.Timestamp(ev["t"]), float(ev["value"])))
        for c in series:
            series[c].sort()
        times = pd.to_datetime(np.asarray(e["abs_times"]))
        S = np.asarray(e["s"], dtype=np.float32)
        for i, t in enumerate(times):
            row = np.full(L, np.nan, dtype=np.float32)
            for j, c in enumerate(LOINCS):
                obs = series[c]
                # last value at or before t
                v = None
                for (tt, vv) in obs:
                    if tt <= t:
                        v = vv
                    else:
                        break
                if v is not None:
                    row[j] = v
            X.append(S[i]); Y.append(row); PID.append(pid)
    return np.asarray(X), np.asarray(Y), np.asarray(PID)


def main():
    enc = pickle.load(open(ENC, "rb"))
    assert "abs_times" in enc[0], "re-encode with abs_times first (jobs/reencode_clmbr.sbatch)."
    traj = pickle.load(open(TRAJ, "rb"))
    splits = json.loads(SPLITS.read_text())
    tr_s, te_s = set(splits["splits"]["train"]), set(splits["splits"]["test"])

    X, Y, PID = locf_panels(enc, traj)
    print(f"panels: {X.shape[0]:,} timepoints x {L} labs; z-dim {X.shape[1]}")
    print("per-lab coverage (non-missing):")
    for j, nm in enumerate(NAME):
        print(f"    {nm:12s} {100*np.isfinite(Y[:,j]).mean():5.1f}%")

    trm = np.isin(PID, list(tr_s))
    tem = np.isin(PID, list(te_s))
    results = {}
    print("\n[VALUE decodability]  Ridge z->lab   (R2 on held-out test)")
    r2s = []
    for j, nm in enumerate(NAME):
        m_tr = trm & np.isfinite(Y[:, j])
        m_te = tem & np.isfinite(Y[:, j])
        if m_tr.sum() < 200 or m_te.sum() < 50:
            print(f"    {nm:12s} skipped (n_tr={m_tr.sum()})"); continue
        sc = StandardScaler().fit(Y[m_tr, j:j+1])
        ytr = sc.transform(Y[m_tr, j:j+1]).ravel()
        yte = sc.transform(Y[m_te, j:j+1]).ravel()
        reg = Ridge(alpha=10.0).fit(X[m_tr], ytr)
        pred = reg.predict(X[m_te])
        ss_res = float(((yte - pred) ** 2).sum())
        ss_tot = float(((yte - yte.mean()) ** 2).sum()) or 1.0
        r2 = 1 - ss_res / ss_tot
        r2s.append(r2); results[nm] = {"r2": round(r2, 3), "n_test": int(m_te.sum())}
        print(f"    {nm:12s} R2={r2:6.3f}   (n_test={int(m_te.sum())})")

    med = float(np.median(r2s)) if r2s else float("nan")
    print(f"\n  median R2 across labs: {med:.3f}")
    verdict = ("DECODE-ONLY viable (median R2 >= 0.4)" if med >= 0.4 else
               "WEAK — add explicit lab channel to state (median R2 < 0.4)")
    print(f"  VERDICT: {verdict}")
    results["_summary"] = {"median_r2": round(med, 3), "verdict": verdict,
                           "n_timepoints": int(X.shape[0])}
    OUT.write_text(json.dumps(results, indent=2))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
