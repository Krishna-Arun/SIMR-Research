#!/usr/bin/env python3
"""
Benchmark B v1 - case generation
=================================
Task: given an acute-HF patient's pre-procedure clinical state, predict how
core BMP lab trajectories change after dialysis, with causal justification.

Locked design (v1):
  Event    : first dialysis session DURING the acute-HF admission (precise ts)
  Exclude  : chronic-dialysis / ESRD admissions (isolate acute-AKI cases)
  Window   : 48h pre / 72h post the dialysis start
  Include  : >=3 measurements of the target lab on each side
  Targets  : creatinine, BUN, potassium, bicarbonate (serum, Chemistry)
  Label    : reference-range MEMBERSHIP change, baseline (last pre) -> last post
               moved_into_range   : out-of-range -> within-range  (normalizing)
               moved_out_of_range : within-range -> out-of-range  (worsening)
               stayed             : in-range membership unchanged
  State    : Tier-1 structured only (no narrative):
               demographics, admission, comorbidity flags, coronary/contrast
               exposure, dialysis params, pre-window medications by class,
               baseline context labs, pre-window target-lab series.

All raw series + ref ranges are stored so the label rule can be re-tuned
without re-reading the source tables.
"""
import gzip, csv, json, os, datetime as dt
from collections import defaultdict

# ----------------------------------------------------------------------
REPO = "/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research"
BASE = f"{REPO}/Version_6/acute_hf_cohort/files/mimiciv/3.1"
OUT  = f"{REPO}/Version_6/benchmark_b"

PRE_H, POST_H     = 48, 72
MIN_PRE, MIN_POST = 3, 3

ACUTE_HF_CODES = {"I5021","I5023","I5031","I5033","I5041","I5043","I50811",
                  "I50813","42821","42823","42831","42833","42841","42843"}
EXCLUDE_CODES  = {"N186","Z992","5856","V4511","V560","Z4901","Z4902","Z4931"}

DIALYSIS_ITEMS = {225441,225802,225803,225809,225955,225805}
DIALYSIS_LABEL = {225441:"Hemodialysis",225802:"CRRT",225803:"CVVHD",
                  225809:"CVVHDF",225955:"SCUF",225805:"Peritoneal Dialysis"}

TARGET_ITEMS = {50912:"creat",52546:"creat",51006:"bun",52647:"bun",
                50971:"k",52610:"k",50882:"hco3"}
LAB_NAMES = {"creat":"Creatinine","bun":"BUN (Urea Nitrogen)",
             "k":"Potassium","hco3":"Bicarbonate"}
LABS = ["creat","bun","k","hco3"]

CONTEXT_ITEMS = {50813:"Lactate",52442:"Lactate",53154:"Lactate",
                 50820:"pH",50818:"pCO2",51222:"Hemoglobin",
                 50862:"Albumin",53085:"Albumin",50931:"Glucose",52569:"Glucose",
                 50893:"Calcium",50960:"Magnesium",50970:"Phosphate",
                 50963:"NTproBNP"}

# medication classes -> lowercase name substrings
MED_CLASSES = {
    "loop_diuretic":       ["furosemide","bumetanide","torsemide","torasemide","ethacrynic","lasix","bumex"],
    "thiazide_diuretic":   ["hydrochlorothiazide","metolazone","chlorothiazide","chlorthalidone","indapamide","hctz","zaroxolyn"],
    "k_sparing_diuretic":  ["spironolactone","eplerenone","amiloride","triamterene","aldactone"],
    "potassium_binder":    ["polystyrene sulfonate","kayexalate","patiromer","veltassa","sodium zirconium","lokelma"],
    "insulin":             ["insulin"],
    "dextrose":            ["dextrose","d50","d5w","d10w"],
    "iv_bicarbonate":      ["sodium bicarbonate","bicarbonate"],
    "potassium_supplement":["potassium chloride","potassium phosph","kcl","klor","k-dur"],
    "vasopressor_inotrope":["norepinephrine","epinephrine","phenylephrine","vasopressin","dopamine","dobutamine","levophed","milrinone"],
    "ace_arb_arni":        ["lisinopril","enalapril","captopril","ramipril","benazepril","quinapril","fosinopril",
                            "losartan","valsartan","candesartan","olmesartan","irbesartan","telmisartan","sacubitril"],
    "nephrotoxic_abx":     ["vancomycin","gentamicin","tobramycin","amikacin","colistin"],
    "beta_agonist":        ["albuterol","salbutamol"],
    "iv_saline":           ["sodium chloride 0.9","0.9% sodium chloride","normal saline"],
    "iv_lactated_ringers": ["lactated ringers","lactated ringer"],
}

COMORBIDITY = {   # flag -> ICD prefixes (ICD-10 & ICD-9)
    "aki":              ("N17","584"),
    "ckd_nonesrd":      ("N18","585"),        # ESRD already excluded from cohort
    "diabetes":         ("E08","E09","E10","E11","E13","250"),
    "sepsis":           ("A40","A41","R652","99591","99592","78552"),
    "hypertension":     ("I10","I11","I12","I13","I15","401","402","403","404","405"),
    "cardiogenic_shock":("R570","78551"),
    "atrial_fib":       ("I48","42731"),
    "cad":              ("I25","414"),
    "copd":             ("J44","496"),
    "liver_disease":    ("K70","K72","K74","571","5722","5723"),
}
CORONARY_PREFIX = ("8853","8854","8855","8856","8857","3722","3723","0066",
                   "3606","3607","B21","4A023","0270","0271","0272","0273")
# ----------------------------------------------------------------------

def parse_ts(s):
    try: return dt.datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S")
    except Exception: return None

def parse_date(s):
    try: return dt.datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except Exception: return None

def range_status(v, lo, hi):
    if lo is None or hi is None: return None
    if v < lo: return "Below"
    if v > hi: return "Above"
    return "Within"

def classify_drug(name):
    n = name.lower()
    return [cls for cls, keys in MED_CLASSES.items() if any(k in n for k in keys)]

# --- 1. diagnoses: acute-HF set, per-admission codes ---
print("[1/8] diagnoses ...")
ahf, hadm_codes = set(), defaultdict(set)
with gzip.open(f"{BASE}/hosp/diagnoses_icd.csv.gz","rt") as f:
    r = csv.reader(f); next(r)
    for row in r:
        hadm, code = row[1], row[3]
        if code in ACUTE_HF_CODES: ahf.add(hadm)
        hadm_codes[hadm].add(code)
print(f"      {len(ahf)} acute-HF admissions")

# --- 2. first dialysis anchor per acute-HF admission, minus ESRD/chronic ---
print("[2/8] dialysis anchors (excluding chronic-dialysis/ESRD) ...")
anchor = {}
with gzip.open(f"{BASE}/icu/procedureevents.csv.gz","rt") as f:
    r = csv.reader(f); next(r)
    for row in r:
        subj, hadm, stay = row[0], row[1], row[2]
        start, end = parse_ts(row[4]), parse_ts(row[5])
        try: itemid = int(row[7])
        except ValueError: continue
        if hadm not in ahf or itemid not in DIALYSIS_ITEMS or start is None:
            continue
        if hadm not in anchor or start < anchor[hadm]["t"]:
            anchor[hadm] = {"t":start,"end":end,"itemid":itemid,"stay_id":stay,"subject":subj}
excluded = {h for h in anchor if hadm_codes[h] & EXCLUDE_CODES}
for h in excluded: del anchor[h]
print(f"      {len(anchor)} anchored acute-AKI admissions "
      f"({len({a['subject'] for a in anchor.values()})} patients); "
      f"excluded {len(excluded)} chronic-dialysis/ESRD")

anch = set(anchor)

# --- 3. labs (target + context) for anchored admissions ---
print("[3/8] labs (streaming labevents) ...")
tgt = defaultdict(lambda: defaultdict(list))
ctx = defaultdict(lambda: defaultdict(list))
with gzip.open(f"{BASE}/hosp/labevents.csv.gz","rt") as f:
    next(f)
    for line in f:
        p = line.split(",")
        if len(p) < 13: continue
        hadm = p[2]
        if hadm not in anch: continue
        try: itemid = int(p[4])
        except ValueError: continue
        lab = TARGET_ITEMS.get(itemid); name = CONTEXT_ITEMS.get(itemid)
        if lab is None and name is None: continue
        t = parse_ts(p[6])
        if t is None: continue
        try: v = float(p[9])
        except ValueError: continue
        try: lo = float(p[11])
        except ValueError: lo = None
        try: hi = float(p[12])
        except ValueError: hi = None
        if lab:  tgt[hadm][lab].append((t,v,lo,hi))
        if name: ctx[hadm][name].append((t,v,lo,hi))
print(f"      labs for {len(tgt)} admissions")

# --- 4. medications in pre-window (with dose / units / route / frequency) ---
# prescriptions cols: ...,starttime(6),stoptime(7),drug_type(8),drug(9),...,
#   dose_val_rx(15),dose_unit_rx(16),form_val_disp(17),form_unit_disp(18),
#   doses_per_24_hrs(19),route(20)
print("[4/8] medications (streaming prescriptions) ...")
meds = defaultdict(lambda: defaultdict(dict))   # hadm -> class -> {dedup_key: entry}
with gzip.open(f"{BASE}/hosp/prescriptions.csv.gz","rt") as f:
    r = csv.reader(f); next(r)
    for row in r:
        if len(row) < 21: continue
        hadm = row[1]
        if hadm not in anch: continue
        start, stop, drug = parse_ts(row[6]), parse_ts(row[7]), row[9]
        if start is None or not drug: continue
        at = anchor[hadm]["t"]; win_start = at - dt.timedelta(hours=PRE_H)
        if not (start < at and (stop is None or stop > win_start)): continue
        dose_val, dose_unit, per_day, route = row[15], row[16], row[19], row[20]
        for cls in classify_drug(drug):
            key = (drug.strip(), dose_val, dose_unit, route)
            meds[hadm][cls][key] = {
                "drug": drug.strip(),
                "dose_val": dose_val or None,
                "dose_unit": dose_unit or None,
                "doses_per_24h": per_day or None,
                "route": route or None,
            }
print(f"      meds for {len(meds)} admissions")

# --- 5. demographics ---
print("[5/8] demographics ...")
demo = {}
with gzip.open(f"{BASE}/hosp/patients.csv.gz","rt") as f:
    r = csv.reader(f); next(r)
    for row in r: demo[row[0]] = {"gender":row[1],"age":row[2]}
adm = {}
with gzip.open(f"{BASE}/hosp/admissions.csv.gz","rt") as f:
    r = csv.reader(f); next(r)
    for row in r: adm[row[1]] = {"admittime":row[2],"admission_type":row[5],"race":row[12]}

# --- 6. coronary / contrast procedures ---
print("[6/8] coronary/contrast procedures ...")
coronary = defaultdict(list)
with gzip.open(f"{BASE}/hosp/procedures_icd.csv.gz","rt") as f:
    r = csv.reader(f); next(r)
    for row in r:
        hadm, cdate, code = row[1], parse_date(row[3]), row[4]
        if hadm not in anch or cdate is None: continue
        if code.startswith(CORONARY_PREFIX):
            off = (cdate - anchor[hadm]["t"].date()).days
            coronary[hadm].append((code, off))

# --- 7. helpers ---
def split_series(pts, at):
    pre, post = [], []
    for t,v,lo,hi in pts:
        h = (t-at).total_seconds()/3600.0
        if   -PRE_H <= h < 0:  pre.append((round(h,2),v,lo,hi))
        elif 0 < h <= POST_H:  post.append((round(h,2),v,lo,hi))
    pre.sort(); post.sort()
    return pre, post

def make_label(pre, post):
    _,bv,blo,bhi = pre[-1]; _,pv,plo,phi = post[-1]
    bs, ps = range_status(bv,blo,bhi), range_status(pv,plo,phi)
    if bs is None or ps is None: lbl = None
    else:
        b_in, p_in = bs=="Within", ps=="Within"
        lbl = ("moved_into_range" if (not b_in and p_in)
               else "moved_out_of_range" if (b_in and not p_in) else "stayed")
    return {"label":lbl,"baseline_value":round(bv,3),"baseline_status":bs,
            "baseline_ref":[blo,bhi],"post_value":round(pv,3),"post_status":ps,
            "post_ref":[plo,phi]}

# --- 8. build cases ---
print("[8/8] building cases ...")
os.makedirs(OUT, exist_ok=True)
cases = []
n_elig = {l:0 for l in LABS}; n_lbl = {l:0 for l in LABS}
dist = {l:defaultdict(int) for l in LABS}; n_all4 = 0

for hadm, a in anchor.items():
    at, subj = a["t"], a["subject"]
    dur = round((a["end"]-a["t"]).total_seconds()/3600.0,2) if a["end"] else None

    targets, pre_ser, post_ser = {}, {}, {}
    for lab in LABS:
        pre, post = split_series(tgt[hadm].get(lab,[]), at)
        f = lambda pts: [{"h":h,"v":v,"ref_low":lo,"ref_high":hi} for h,v,lo,hi in pts]
        pre_ser[lab], post_ser[lab] = f(pre), f(post)
        elig = len(pre)>=MIN_PRE and len(post)>=MIN_POST
        info = {"eligible":elig,"n_pre":len(pre),"n_post":len(post),"label":None}
        if elig:
            n_elig[lab]+=1; info.update(make_label(pre,post))
            if info["label"] is not None:
                n_lbl[lab]+=1; dist[lab][info["label"]]+=1
        targets[lab]=info

    usable = {l: targets[l]["eligible"] and targets[l]["label"] is not None for l in LABS}
    all4 = all(usable.values())
    if all4: n_all4+=1

    ctx_base = {}
    for name, pts in ctx[hadm].items():
        pre = sorted([((t-at).total_seconds()/3600.0, v, lo, hi)
                      for t,v,lo,hi in pts if -PRE_H <= (t-at).total_seconds()/3600.0 < 0])
        if pre:
            h,v,lo,hi = pre[-1]
            ctx_base[name] = {"value":round(v,3),"ref_low":lo,"ref_high":hi,
                              "status":range_status(v,lo,hi),"hours_before":round(-h,2)}

    comorbid = {flag: any(c.startswith(pref) for c in hadm_codes[hadm])
                for flag,pref in COMORBIDITY.items()}
    hf_codes = sorted(hadm_codes[hadm] & ACUTE_HF_CODES)
    cor = sorted(coronary.get(hadm,[]), key=lambda x: abs(x[1]))

    cases.append({
        "case_id": f"BENCHB_{hadm}",
        "subject_id":subj, "hadm_id":hadm, "stay_id":a["stay_id"],
        "anchor_time": at.strftime("%Y-%m-%d %H:%M:%S"),
        "dialysis": {"modality":DIALYSIS_LABEL.get(a["itemid"],str(a["itemid"])),
                     "duration_hours":dur},
        "state": {
            "demographics": demo.get(subj,{}),
            "admission": adm.get(hadm,{}),
            "acute_hf_codes": hf_codes,
            "comorbidities": comorbid,
            "coronary_contrast": {"present":bool(cor),
                                  "procedures":[{"icd":c,"offset_days":o} for c,o in cor]},
            "medications_pre_window": {c:list(entries.values()) for c,entries in meds[hadm].items()},
            "context_labs_baseline": ctx_base,
            "pre_window_target_labs": {LAB_NAMES[l]:pre_ser[l] for l in LABS},
        },
        "outcome": {
            "window_hours":{"pre":PRE_H,"post":POST_H},
            "post_window_target_labs": {LAB_NAMES[l]:post_ser[l] for l in LABS},
            "targets": {LAB_NAMES[l]:targets[l] for l in LABS},
            "eligible_all_four": all4,
        },
    })

with open(f"{OUT}/cases_all.jsonl","w") as f:
    for c in cases: f.write(json.dumps(c)+"\n")
with open(f"{OUT}/cases_eligible_all4.jsonl","w") as f:
    for c in cases:
        if c["outcome"]["eligible_all_four"]: f.write(json.dumps(c)+"\n")

print("\n===================== SUMMARY =====================")
print(f"Anchored acute-AKI admissions : {len(cases)}")
print(f"Distinct patients             : {len({c['subject_id'] for c in cases})}")
print(f"Usable for ALL FOUR labs      : {n_all4}")
print(f"\n{'lab':>20} | {'elig':>5} {'labeled':>7} | into / stayed / out")
print("-"*66)
for l in LABS:
    d = dist[l]
    print(f"{LAB_NAMES[l]:>20} | {n_elig[l]:>5} {n_lbl[l]:>7} | "
          f"{d['moved_into_range']} / {d['stayed']} / {d['moved_out_of_range']}")
print(f"\nWrote:\n  {OUT}/cases_all.jsonl ({len(cases)})"
      f"\n  {OUT}/cases_eligible_all4.jsonl ({n_all4})")
