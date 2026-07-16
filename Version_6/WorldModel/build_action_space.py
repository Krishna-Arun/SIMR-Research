#!/usr/bin/env python3
"""
Approach #1: DAG defines the action space.

The DAG separates nodes into ACTIONS (interventions a clinician sets), CONFOUNDERS
(baseline state driving the decision), and OUTCOMES (labs). This script extracts the
ACTION nodes: per-admission MULTI-HOT vectors over the clinically-distinct treatments
(the decision variables for MPC), from the acute-HF ICU cohort.

Treatments (grouped, actionable, prevalent enough to learn) -- rare MCS/ECMO excluded:
  diuretic | vasodilator | inotrope | vasopressor | dialysis | ventilation

Output: action_space.json  { hadm_id: [6-hot] }  + a co-occurrence summary (treatments
co-occur, so the action is a VECTOR, not a single choice -- key for scaling to MPC).
"""
import gzip, csv, json, os
from collections import defaultdict
import numpy as np

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "acute_hf_cohort/files/mimiciv/3.1")
TREATMENTS = ["diuretic", "vasodilator", "inotrope", "vasopressor", "dialysis", "ventilation"]

DRUG2TX = {  # inputevents drug substrings -> grouped treatment
    "furosemide": "diuretic", "bumetanide": "diuretic",
    "nitroglycerin": "vasodilator", "nitroprusside": "vasodilator",
    "dobutamine": "inotrope", "milrinone": "inotrope",
    "norepinephrine": "vasopressor", "epinephrine": "vasopressor", "vasopressin": "vasopressor",
    "phenylephrine": "vasopressor", "dopamine": "vasopressor",
}
PROC2TX = {"invasive ventilation": "ventilation", "dialysis": "dialysis", "crrt": "dialysis", "cvvh": "dialysis"}


def match(label, table):
    ll = label.lower()
    for k, v in table.items():
        if k in ll:
            return v
    return None


def main():
    icu_hadm = set()
    with gzip.open(f"{BASE}/icu/icustays.csv.gz", "rt") as f:
        for row in csv.DictReader(f):
            icu_hadm.add(row["hadm_id"])
    lab = {}
    with gzip.open(f"{BASE}/icu/d_items.csv.gz", "rt") as f:
        for row in csv.DictReader(f):
            lab[row["itemid"]] = row["label"]
    item2tx = {}
    for i, l in lab.items():
        item2tx[i] = match(l, DRUG2TX) or match(l, PROC2TX)

    got = defaultdict(set)   # hadm -> set(treatments)
    for src, fname in [("input", "inputevents"), ("proc", "procedureevents")]:
        with gzip.open(f"{BASE}/icu/{fname}.csv.gz", "rt") as f:
            for row in csv.DictReader(f):
                tx = item2tx.get(row["itemid"])
                if tx and row["hadm_id"] in icu_hadm:
                    got[row["hadm_id"]].add(tx)

    idx = {t: i for i, t in enumerate(TREATMENTS)}
    action = {h: [1 if t in got.get(h, ()) else 0 for t in TREATMENTS] for h in icu_hadm}
    json.dump(action, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "action_space.json"), "w"))

    N = len(icu_hadm)
    M = np.array([action[h] for h in icu_hadm])
    print(f"acute-HF ICU admissions: {N}\n")
    print("ACTION-SPACE prevalence (multi-hot; treatments CO-OCCUR):")
    for t in TREATMENTS:
        print(f"  {t:12s} {M[:, idx[t]].sum():6d}  {100*M[:, idx[t]].mean():5.1f}%")
    print(f"\n# treatments per admission: mean {M.sum(1).mean():.2f}  "
          f"(0:{(M.sum(1)==0).mean()*100:.0f}%  1:{(M.sum(1)==1).mean()*100:.0f}%  "
          f"2:{(M.sum(1)==2).mean()*100:.0f}%  3+:{(M.sum(1)>=3).mean()*100:.0f}%)")
    print("\nco-occurrence (P(row | col)):")
    print("           " + " ".join(f"{t[:5]:>6}" for t in TREATMENTS))
    for a in TREATMENTS:
        row = []
        for b in TREATMENTS:
            denom = M[:, idx[b]].sum()
            row.append((M[:, idx[a]] * M[:, idx[b]]).sum() / denom if denom else 0)
        print(f"  {a:10s}" + " ".join(f"{x:6.2f}" for x in row))
    print("\nwrote action_space.json  (per-admission 6-hot over treatments)")


if __name__ == "__main__":
    main()
