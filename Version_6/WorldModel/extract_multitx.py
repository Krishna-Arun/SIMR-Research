#!/usr/bin/env python3
"""
Multi-treatment cohort extraction (foundation for the full multi-treatment causal WM).

Per acute-HF ICU admission, anchored at ICU admission time t0:
  - baseline confounders: comorbidity flags + age + sex + baseline (first) target-lab values
  - 4 target-lab trajectory over [t0, t0+120h]  (hour, lab, value, ref)
  - 6 treatments: active flag + first start time within [t0, t0+48h]

Output: multitx_cohort.jsonl (one record per admission). This unblocks (a) per-treatment
causal effects for all 6 treatments and (b) a world model with a multi-hot action.
"""
import gzip, csv, json, os, datetime as dt, argparse
from collections import defaultdict

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "acute_hf_cohort/files/mimiciv/3.1")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "multitx_cohort.jsonl")

TARGET_ITEMS = {"50912": "creat", "52546": "creat", "51006": "bun", "52647": "bun",
                "50971": "k", "52610": "k", "50882": "hco3"}
LAB_NAMES = {"creat": "Creatinine", "bun": "BUN (Urea Nitrogen)", "k": "Potassium", "hco3": "Bicarbonate"}
COMORBID = {"aki": ("N17", "584"), "ckd_nonesrd": ("N18", "585"), "diabetes": ("E08", "E09", "E10", "E11", "E13", "250"),
            "sepsis": ("A40", "A41", "R652", "99591", "99592"), "hypertension": ("I10", "I11", "I12", "I13", "401", "402", "403", "404", "405"),
            "cardiogenic_shock": ("R570", "78551"), "atrial_fib": ("I48", "42731"), "cad": ("I25", "414"),
            "copd": ("J44", "496"), "liver_disease": ("K70", "K72", "K74", "571", "5722", "5723")}
DRUG2TX = {"furosemide": "diuretic", "bumetanide": "diuretic", "torsemide": "diuretic",
           "nitroglycerin": "vasodilator", "nitroprusside": "vasodilator",
           "dobutamine": "inotrope", "milrinone": "inotrope",
           "norepinephrine": "vasopressor", "epinephrine": "vasopressor", "vasopressin": "vasopressor",
           "phenylephrine": "vasopressor", "dopamine": "vasopressor"}
PROC2TX = {"invasive ventilation": "ventilation", "dialysis": "dialysis", "crrt": "dialysis", "cvvh": "dialysis"}
TREATMENTS = ["diuretic", "vasodilator", "inotrope", "vasopressor", "dialysis", "ventilation"]


def pts(s):
    try: return dt.datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S")
    except Exception: return None
def fnum(x):
    try: return float(x)
    except Exception: return None
def match(label, table):
    ll = label.lower()
    for k, v in table.items():
        if k in ll: return v
    return None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--limit", type=int, default=0); args = ap.parse_args()

    print("[1] icustays (t0 per hadm) ...", flush=True)
    t0 = {}; subj = {}
    with gzip.open(f"{BASE}/icu/icustays.csv.gz", "rt") as f:
        for r in csv.DictReader(f):
            it = pts(r["intime"]); h = r["hadm_id"]
            if it and (h not in t0 or it < t0[h]):
                t0[h] = it; subj[h] = r["subject_id"]
    hadms = set(t0)
    if args.limit:
        hadms = set(list(hadms)[:args.limit]); t0 = {h: t0[h] for h in hadms}; subj = {h: subj[h] for h in hadms}
    print(f"    {len(hadms)} acute-HF ICU admissions", flush=True)

    print("[2] patients / admissions ...", flush=True)
    age = {}; sex = {}
    with gzip.open(f"{BASE}/hosp/patients.csv.gz", "rt") as f:
        for r in csv.DictReader(f):
            age[r["subject_id"]] = fnum(r.get("anchor_age")); sex[r["subject_id"]] = r.get("gender")

    print("[3] diagnoses (comorbidities) ...", flush=True)
    codeset = defaultdict(set)
    with gzip.open(f"{BASE}/hosp/diagnoses_icd.csv.gz", "rt") as f:
        r = csv.reader(f); next(r)
        for row in r:
            if row[1] in hadms: codeset[row[1]].add(row[3])

    print("[4] treatments (inputevents + procedureevents) ...", flush=True)
    lab_items = {}
    with gzip.open(f"{BASE}/icu/d_items.csv.gz", "rt") as f:
        for r in csv.DictReader(f): lab_items[r["itemid"]] = r["label"]
    item2tx = {i: (match(l, DRUG2TX) or match(l, PROC2TX)) for i, l in lab_items.items()}
    tx_start = defaultdict(lambda: defaultdict(lambda: None))   # hadm -> tx -> earliest start (hours from t0)
    for fname in ("inputevents", "procedureevents"):
        with gzip.open(f"{BASE}/icu/{fname}.csv.gz", "rt") as f:
            for r in csv.DictReader(f):
                h = r["hadm_id"]; tx = item2tx.get(r["itemid"])
                if tx and h in hadms:
                    st = pts(r.get("starttime", ""))
                    if st:
                        hr = (st - t0[h]).total_seconds() / 3600
                        if 0 <= hr <= 48 and (tx_start[h][tx] is None or hr < tx_start[h][tx]):
                            tx_start[h][tx] = round(hr, 2)

    print("[5] labevents (streaming target labs) ...", flush=True)
    labs = defaultdict(lambda: defaultdict(list))   # hadm -> lab -> [(hour, val, lo, hi)]
    with gzip.open(f"{BASE}/hosp/labevents.csv.gz", "rt") as f:
        r = csv.reader(f); next(r)
        for row in r:
            if len(row) < 13: continue
            h = row[2]
            if h not in hadms: continue
            lab = TARGET_ITEMS.get(row[4])
            if not lab: continue
            ct = pts(row[6]); v = fnum(row[9])
            if ct is None or v is None: continue
            hr = (ct - t0[h]).total_seconds() / 3600
            if -6 <= hr <= 120:
                labs[h][LAB_NAMES[lab]].append((round(hr, 2), v, fnum(row[11]), fnum(row[12])))

    print("[6] assembling ...", flush=True)
    n = 0
    with open(OUT, "w") as fo:
        for h in hadms:
            s = subj[h]
            como = {fl: any(c.startswith(pref) for c in codeset[h]) for fl, pref in COMORBID.items()}
            baseline = {}
            for lab, rows in labs[h].items():
                pre = [x for x in rows if x[0] <= 6] or rows
                if pre: baseline[lab] = sorted(pre, key=lambda x: abs(x[0]))[0][1]
            traj = {lab: sorted([x for x in rows if x[0] >= 0]) for lab, rows in labs[h].items()}
            tx = {t: (1 if tx_start[h][t] is not None else 0) for t in TREATMENTS}
            tx_t = {t: tx_start[h][t] for t in TREATMENTS}
            fo.write(json.dumps({"hadm_id": h, "subject_id": s, "age": age.get(s), "sex": sex.get(s),
                                 "comorbidities": como, "baseline_labs": baseline,
                                 "lab_traj": traj, "treatments": tx, "treatment_start_h": tx_t}) + "\n")
            n += 1
    print(f"wrote {n} records -> {OUT}", flush=True)
    from collections import Counter
    import statistics as st
    recs = [json.loads(l) for l in open(OUT)]
    print("treatment prevalence:", {t: sum(r["treatments"][t] for r in recs) for t in TREATMENTS})
    nlab = [sum(len(v) for v in r["lab_traj"].values()) for r in recs]
    print(f"median lab measurements/admission (0-120h): {st.median(nlab):.0f}")


if __name__ == "__main__":
    main()
