"""
eval_simulator_benchmarkB.py — Task 5: model-free eval of the simulator, Benchmark-B methodology,
on the held-out TEST split (the honest 'does it actually work' proof, no LLM).

Only 2/100 existing Benchmark-B questions map to our test split (it was built on a broader post-proc
cohort), so we apply Benchmark B's OWN direction rule (qgen/trajectory.py) to our test patients:
  baseline = last real lab value <= time_zero;  post_rep = last real value in (t0, t0+H].
  Stable if ref_lo <= post_rep <= ref_hi;  else Rising if post_rep>=baseline else Falling.
We REQUIRE a real post remeasurement (fixes the LOCF 'fake stable' artifact).

Simulator prediction: from z at time_zero, roll the world model forward through the ACTUAL actions to
the timepoint nearest the post value, decode -> un-standardize -> predicted post_rep, apply same rule.
Compare vs baselines: persistence (post_rep=baseline) and majority-class. Balanced 3-class accuracy.

Run: simr python eval_simulator_benchmarkB.py
"""
from __future__ import annotations
import json, pickle
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np, pandas as pd, torch
from train_substrate_wm import ACJEPA, LabDecoder, CORE, LOINCS, LABN, NL, ARM

BASE = Path("/scratch/users/karun09/Version_2/counterfactual_simulation")
BQ = Path("/scratch/users/karun09/Version_2/Benchmark_B/Question_Generation/outputs/questions.jsonl")
H_HOURS = 48.0
STABLE_REL = 0.15
DEV = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Benchmark-B lab label -> our core name
BQLAB = {"Creatinine": "creatinine", "Potassium": "potassium", "Sodium": "sodium",
         "Platelet Count": "platelets", "Bicarbonate": "bicarbonate",
         "Urea Nitrogen": "bun", "Hemoglobin": "hemoglobin"}
NAME2LOINC = {v: k for k, v in CORE.items()}


def ref_ranges():
    """mode ref_lower/ref_upper per lab from Benchmark B questions."""
    lo, hi = defaultdict(list), defaultdict(list)
    for l in open(BQ):
        for t in json.loads(l)["target_labs_detail"]:
            nm = BQLAB.get(t["label"])
            if nm and t.get("ref_lower") is not None and t.get("ref_upper") is not None:
                lo[nm].append(t["ref_lower"]); hi[nm].append(t["ref_upper"])
    return {nm: (Counter(lo[nm]).most_common(1)[0][0], Counter(hi[nm]).most_common(1)[0][0])
            for nm in lo}


def direction(post_rep, baseline, lo, hi):
    if lo is not None and hi is not None and lo <= post_rep <= hi:
        return "Stable"
    if lo is not None and hi is not None:
        return "Rising" if post_rep >= baseline else "Falling"
    rel = (post_rep - baseline) / (abs(baseline) + 1e-6)
    if abs(rel) < STABLE_REL: return "Stable"
    return "Rising" if rel > 0 else "Falling"


def lab_series(traj):
    tmap = {int(t["patient_id"]): t for t in traj}
    out = {}
    for pid, tr in tmap.items():
        ser = {c: [] for c in LOINCS}
        for ev in tr["events"]:
            c = ev.get("code")
            if c in ser and ev.get("value") is not None:
                ser[c].append((pd.Timestamp(ev["t"]), float(ev["value"])))
        for c in ser: ser[c].sort()
        out[pid] = ser
    return out


def main():
    sub = pickle.load(open(BASE / "data/train_substrate.pkl", "rb"))
    traj = pickle.load(open(BASE / "data/trajectories.pkl", "rb"))
    sp = json.loads((BASE / "data/splits.json").read_text())
    test = set(sp["splits"]["test"])
    ck = torch.load(BASE / "data/world_model_enriched.pt", map_location=DEV)
    model = ACJEPA(ck["zdim"], ck["adim"]).to(DEV); model.load_state_dict(ck["model"]); model.eval()
    dec = LabDecoder(ck["zdim"], NL).to(DEV); dec.load_state_dict(ck["dec"]); dec.eval()
    lmean = np.array(ck["lab_scaler_mean"]); lstd = np.sqrt(np.array(ck["lab_scaler_var"]))
    refs = ref_ranges()
    print("ref ranges:", {k: (round(v[0],2), round(v[1],2)) for k,v in refs.items()})
    series = lab_series(traj)
    labidx = {nm: LABN.index(nm) for nm in BQLAB.values()}

    @torch.no_grad()
    def decode_units(z):
        return dec(z).cpu().numpy() * lstd + lmean   # [.,NL] real units

    rows = []   # (lab, true, sim, persist)
    subtest = [s for s in sub if int(s["patient_id"]) in test]
    for e in subtest:
        pid = int(e["patient_id"]); ser = series.get(pid, {})
        times = pd.to_datetime(np.asarray(e["abs_times"]))
        Z = torch.tensor(e["s"], device=DEV).float()
        A = torch.tensor(e["action_matrix"], device=DEV).float()
        hrs = np.asarray(e["hours"], dtype=float)
        T = len(times)
        for i in range(T - 1):
            t0 = times[i]
            # roll model forward from i to the last timepoint within H
            khi = i
            for k in range(i + 1, T):
                if (times[k] - t0).total_seconds() / 3600.0 <= H_HOURS: khi = k
                else: break
            if khi == i:  # no substrate step inside window
                continue
            zc = Z[i:i+1]
            act_fired = False
            for j in range(i + 1, khi + 1):
                dt = torch.tensor([max(hrs[j] - hrs[j-1], 0.0)], device=DEV).float()
                zc = model(zc, A[j:j+1], dt)
                if float(A[j].abs().sum()) > 0: act_fired = True
            sim_units = decode_units(zc)[0]
            post_time_hi = t0 + pd.Timedelta(hours=H_HOURS)
            for nm, loinc in NAME2LOINC.items():
                if nm not in BQLAB.values(): continue
                obs = ser.get(loinc, [])
                base = None
                for tt, vv in obs:
                    if tt <= t0: base = vv
                    else: break
                if base is None: continue
                post = [(tt, vv) for tt, vv in obs if t0 < tt <= post_time_hi]
                if not post: continue                 # require REAL remeasurement
                post_rep = post[-1][1]
                lo, hi = refs.get(nm, (None, None))
                true_d = direction(post_rep, base, lo, hi)
                sim_d = direction(float(sim_units[labidx[nm]]), base, lo, hi)
                pers_d = direction(base, base, lo, hi)  # persistence: post=baseline
                rows.append((nm, true_d, sim_d, pers_d, act_fired,
                             base < lo or base > hi))    # baseline out-of-range flag

    df = pd.DataFrame(rows, columns=["lab", "true", "sim", "pers", "active", "base_oor"])
    print(f"\nTEST-split evaluable (lab, time_zero) items with REAL post remeasurement: {len(df)}")
    print(f"patients contributing: {df.index.size and len(subtest)}  true-dir dist: {dict(Counter(df['true']))}")

    def balacc(true, pred):
        cls = ["Rising", "Falling", "Stable"]
        accs = []
        for c in cls:
            m = true == c
            if m.sum() > 0: accs.append((pred[m] == c).mean())
        return float(np.mean(accs)) if accs else float("nan")

    maj = Counter(df["true"]).most_common(1)[0][0]
    overall = {"n": len(df),
               "simulator_balacc": round(balacc(df["true"].values, df["sim"].values), 3),
               "persistence_balacc": round(balacc(df["true"].values, df["pers"].values), 3),
               "majority_class": maj,
               "majority_acc": round(float((df["true"] == maj).mean()), 3),
               "simulator_raw_acc": round(float((df["sim"] == df["true"]).mean()), 3),
               "persistence_raw_acc": round(float((df["pers"] == df["true"]).mean()), 3)}
    per_lab = {}
    for nm, g in df.groupby("lab"):
        per_lab[nm] = {"n": len(g),
                       "sim_balacc": round(balacc(g["true"].values, g["sim"].values), 3),
                       "pers_balacc": round(balacc(g["true"].values, g["pers"].values), 3)}
    def subset(mask, label):
        g = df[mask]
        if len(g) < 30: return {"label": label, "n": len(g), "note": "too few"}
        return {"label": label, "n": len(g),
                "sim_balacc": round(balacc(g["true"].values, g["sim"].values), 3),
                "pers_balacc": round(balacc(g["true"].values, g["pers"].values), 3),
                "true_dist": dict(Counter(g["true"]))}
    subsets = {
        "active_treatment": subset(df["active"].values, "treatment active in window"),
        "baseline_out_of_range": subset(df["base_oor"].values, "abnormal baseline (lab can move)"),
        "active_and_oor": subset((df["active"] & df["base_oor"]).values, "active + abnormal baseline"),
    }
    out = {"overall": overall, "per_lab": per_lab, "subsets": subsets, "H_hours": H_HOURS}
    (BASE / "data/benchmarkB_eval.json").write_text(json.dumps(out, indent=2))

    print("\n==== MODEL-FREE EVAL (TEST split, Benchmark-B rule) ====")
    print(f"  simulator  balanced-acc: {overall['simulator_balacc']}  (raw {overall['simulator_raw_acc']})")
    print(f"  persistence balanced-acc: {overall['persistence_balacc']}  (raw {overall['persistence_raw_acc']})")
    print(f"  majority-class ({maj}) acc: {overall['majority_acc']}   [3-class chance=0.333]")
    print("  per-lab (sim vs pers balanced-acc):")
    for nm, v in sorted(per_lab.items(), key=lambda x: -x[1]["sim_balacc"]):
        print(f"    {nm:12s} n={v['n']:4d}  sim={v['sim_balacc']}  pers={v['pers_balacc']}")
    print("\n  subsets (where a world model CAN beat persistence):")
    for k, v in subsets.items():
        if "sim_balacc" in v:
            print(f"    {v['label']:34s} n={v['n']:5d}  sim={v['sim_balacc']}  pers={v['pers_balacc']}")
    print(f"\nwrote {BASE/'data/benchmarkB_eval.json'}")


if __name__ == "__main__":
    main()
