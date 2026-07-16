#!/usr/bin/env python3
"""
Benchmark B (diuretic variant) - case generation
=================================================
SAME task/window/labs/state/labels as Benchmark B, but the anchor is an
IV LOOP DIURETIC DOSE ESCALATION instead of the first dialysis session.

Escalation anchor (locked):
  First IV loop diuretic order in the acute-HF admission whose furosemide-
  equivalent dose is >= 2x the patient's prior IV loop dose that admission,
  with an absolute step-up of >= 40 mg furosemide-equivalent. (Requires a
  prior IV loop dose to escalate from; mg-unit boluses only.)

Cohort: acute-HF, EXCLUDE chronic-dialysis/ESRD AND any admission that received
dialysis (so the 72h post-window reflects the diuretic push, not concurrent RRT).

Furosemide equivalence: furosemide x1, torsemide x2, bumetanide x40.
Label: reference-range MEMBERSHIP change (moved_into_range / stayed /
moved_out_of_range), baseline (last pre) -> last post, per core lab.
"""
import gzip, csv, json, os, datetime as dt
from collections import defaultdict, Counter

REPO = "/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research"
BASE = f"{REPO}/Version_6/acute_hf_cohort/files/mimiciv/3.1"
OUT  = f"{REPO}/Version_6/benchmark_b_diuretic"
PRE_H, POST_H, MIN_PRE, MIN_POST = 48, 72, 3, 3
STEP_RATIO, STEP_ABS = 2.0, 40.0   # >=2x prior AND >=+40 mg furosemide-eq

ACUTE_HF_CODES = {"I5021","I5023","I5031","I5033","I5041","I5043","I50811","I50813",
                  "42821","42823","42831","42833","42841","42843"}
EXCLUDE_CODES  = {"N186","Z992","5856","V4511","V560","Z4901","Z4902","Z4931"}
DIALYSIS_ITEMS = {225441,225802,225803,225809,225955,225805}
TARGET_ITEMS = {50912:"creat",52546:"creat",51006:"bun",52647:"bun",
                50971:"k",52610:"k",50882:"hco3"}
LAB_NAMES = {"creat":"Creatinine","bun":"BUN (Urea Nitrogen)","k":"Potassium","hco3":"Bicarbonate"}
LABS = ["creat","bun","k","hco3"]
CONTEXT_ITEMS = {50813:"Lactate",52442:"Lactate",53154:"Lactate",50820:"pH",50818:"pCO2",
                 51222:"Hemoglobin",50862:"Albumin",53085:"Albumin",50931:"Glucose",52569:"Glucose",
                 50893:"Calcium",50960:"Magnesium",50970:"Phosphate",50963:"NTproBNP"}
LOOP_EQUIV = [("bumetanide",40.0),("bumex",40.0),("torsemide",2.0),("torasemide",2.0),
              ("furosemide",1.0),("lasix",1.0),("ethacrynic",1.0)]
MED_CLASSES = {
    "loop_diuretic":["furosemide","bumetanide","torsemide","torasemide","ethacrynic","lasix","bumex"],
    "thiazide_diuretic":["hydrochlorothiazide","metolazone","chlorothiazide","chlorthalidone","indapamide","hctz","zaroxolyn"],
    "k_sparing_diuretic":["spironolactone","eplerenone","amiloride","triamterene","aldactone"],
    "potassium_binder":["polystyrene sulfonate","kayexalate","patiromer","veltassa","sodium zirconium","lokelma"],
    "insulin":["insulin"], "dextrose":["dextrose","d50","d5w","d10w"],
    "iv_bicarbonate":["sodium bicarbonate","bicarbonate"],
    "potassium_supplement":["potassium chloride","potassium phosph","kcl","klor","k-dur"],
    "vasopressor_inotrope":["norepinephrine","epinephrine","phenylephrine","vasopressin","dopamine","dobutamine","levophed","milrinone"],
    "ace_arb_arni":["lisinopril","enalapril","captopril","ramipril","benazepril","quinapril","fosinopril",
                    "losartan","valsartan","candesartan","olmesartan","irbesartan","telmisartan","sacubitril"],
    "nephrotoxic_abx":["vancomycin","gentamicin","tobramycin","amikacin","colistin"],
    "beta_agonist":["albuterol","salbutamol"],
    "iv_saline":["sodium chloride 0.9","0.9% sodium chloride","normal saline"],
    "iv_lactated_ringers":["lactated ringers","lactated ringer"],
}
COMORBIDITY = {"aki":("N17","584"),"ckd_nonesrd":("N18","585"),
               "diabetes":("E08","E09","E10","E11","E13","250"),
               "sepsis":("A40","A41","R652","99591","99592","78552"),
               "hypertension":("I10","I11","I12","I13","I15","401","402","403","404","405"),
               "cardiogenic_shock":("R570","78551"),"atrial_fib":("I48","42731"),
               "cad":("I25","414"),"copd":("J44","496"),
               "liver_disease":("K70","K72","K74","571","5722","5723")}
CORONARY_PREFIX = ("8853","8854","8855","8856","8857","3722","3723","0066",
                   "3606","3607","B21","4A023","0270","0271","0272","0273")

def parse_ts(s):
    try: return dt.datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S")
    except Exception: return None
def parse_date(s):
    try: return dt.datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except Exception: return None
def fnum(x):
    try: return float(str(x).split("-")[-1])
    except Exception: return None
def range_status(v,lo,hi):
    if lo is None or hi is None: return None
    return "Below" if v<lo else "Above" if v>hi else "Within"
def classify_drug(name):
    n=name.lower(); return [c for c,ks in MED_CLASSES.items() if any(k in n for k in ks)]
def loop_equiv_factor(name):
    n=name.lower()
    for kw,f in LOOP_EQUIV:
        if kw in n: return f
    return None

# 1. diagnoses
print("[1] diagnoses ...", flush=True)
ahf, hadm_codes = set(), defaultdict(set)
with gzip.open(f"{BASE}/hosp/diagnoses_icd.csv.gz","rt") as f:
    r=csv.reader(f); next(r)
    for row in r:
        h,c=row[1],row[3]
        if c in ACUTE_HF_CODES: ahf.add(h)
        hadm_codes[h].add(c)

# 2. admissions that received dialysis (EXCLUDE)
print("[2] dialysis admissions (exclude) ...", flush=True)
dial_admissions=set()
with gzip.open(f"{BASE}/icu/procedureevents.csv.gz","rt") as f:
    r=csv.reader(f); next(r)
    for row in r:
        try: it=int(row[7])
        except ValueError: continue
        if it in DIALYSIS_ITEMS: dial_admissions.add(row[1])

# 3. escalation anchors (prescriptions pass 1): collect IV loop mg orders, find dose step-up
print("[3] escalation anchors (prescriptions) ...", flush=True)
orders=defaultdict(list)   # hadm -> [(start, equiv_mg, drug, route)]
with gzip.open(f"{BASE}/hosp/prescriptions.csv.gz","rt") as f:
    r=csv.reader(f); next(r)
    for row in r:
        if len(row)<21: continue
        h=row[1]
        if h not in ahf or h in dial_admissions or (hadm_codes[h]&EXCLUDE_CODES): continue
        drug=row[9]; route=(row[20] or "").upper(); unit=(row[16] or "").lower()
        if "IV" not in route or unit!="mg": continue
        fac=loop_equiv_factor(drug)
        if fac is None: continue
        dose=fnum(row[15]); start=parse_ts(row[6])
        if dose is None or start is None: continue
        orders[h].append((start, dose*fac, drug.strip(), row[20] or ""))

anchor={}
for h,ol in orders.items():
    ol.sort(key=lambda x:x[0])
    running_max=None
    for start,eq,drug,route in ol:
        if running_max is not None and eq>=STEP_RATIO*running_max and (eq-running_max)>=STEP_ABS:
            anchor[h]={"t":start,"subject":None,"from":round(running_max,1),"to":round(eq,1),
                       "drug":drug,"route":route}
            break
        running_max = eq if running_max is None else max(running_max,eq)
print(f"    escalation-anchored admissions: {len(anchor)}", flush=True)
anch=set(anchor)

# subject_id per hadm (from any prescriptions row already? use admissions)
# 4. labs (target + context) + demographics/admissions
print("[4] labs ...", flush=True)
tgt=defaultdict(lambda: defaultdict(list)); ctx=defaultdict(lambda: defaultdict(list))
with gzip.open(f"{BASE}/hosp/labevents.csv.gz","rt") as f:
    next(f)
    for line in f:
        p=line.split(",")
        if len(p)<13: continue
        h=p[2]
        if h not in anch: continue
        try: it=int(p[4])
        except ValueError: continue
        lab=TARGET_ITEMS.get(it); name=CONTEXT_ITEMS.get(it)
        if lab is None and name is None: continue
        t=parse_ts(p[6]); v=fnum(p[9])
        if t is None or v is None: continue
        lo=fnum(p[11]); hi=fnum(p[12])
        if lab: tgt[h][lab].append((t,v,lo,hi))
        if name: ctx[h][name].append((t,v,lo,hi))

print("[5] demographics ...", flush=True)
demo={}; adm={}; subj_of={}
with gzip.open(f"{BASE}/hosp/admissions.csv.gz","rt") as f:
    r=csv.reader(f); next(r)
    for row in r:
        adm[row[1]]={"admission_type":row[5],"race":row[12]}
        subj_of[row[1]]=row[0]
with gzip.open(f"{BASE}/hosp/patients.csv.gz","rt") as f:
    r=csv.reader(f); next(r)
    for row in r: demo[row[0]]={"gender":row[1],"age":row[2]}

# 6. coronary/contrast
print("[6] coronary/contrast ...", flush=True)
coronary=defaultdict(list)
with gzip.open(f"{BASE}/hosp/procedures_icd.csv.gz","rt") as f:
    r=csv.reader(f); next(r)
    for row in r:
        h=row[1]; cd=parse_date(row[3]); code=row[4]
        if h not in anch or cd is None: continue
        if code.startswith(CORONARY_PREFIX):
            coronary[h].append((code,(cd-anchor[h]["t"].date()).days))

# 7. meds (with dose), pre-window (prescriptions pass 2)
print("[7] medications ...", flush=True)
meds=defaultdict(lambda: defaultdict(dict))
with gzip.open(f"{BASE}/hosp/prescriptions.csv.gz","rt") as f:
    r=csv.reader(f); next(r)
    for row in r:
        if len(row)<21: continue
        h=row[1]
        if h not in anch: continue
        start,stop,drug=parse_ts(row[6]),parse_ts(row[7]),row[9]
        if start is None or not drug: continue
        at=anchor[h]["t"]; ws=at-dt.timedelta(hours=PRE_H)
        if not (start<at and (stop is None or stop>ws)): continue
        for cls in classify_drug(drug):
            key=(drug.strip(),row[15],row[16],row[20])
            meds[h][cls][key]={"drug":drug.strip(),"dose_val":row[15] or None,
                               "dose_unit":row[16] or None,"doses_per_24h":row[19] or None,
                               "route":row[20] or None}

# 8. build helpers
def split_series(pts, at):
    pre,post=[],[]
    for t,v,lo,hi in pts:
        h=(t-at).total_seconds()/3600.0
        if -PRE_H<=h<0: pre.append((round(h,2),v,lo,hi))
        elif 0<h<=POST_H: post.append((round(h,2),v,lo,hi))
    pre.sort(); post.sort(); return pre,post
def make_label(pre,post):
    _,bv,blo,bhi=pre[-1]; _,pv,plo,phi=post[-1]
    bs,ps=range_status(bv,blo,bhi),range_status(pv,plo,phi)
    if bs is None or ps is None: lbl=None
    else:
        bi,pi=bs=="Within",ps=="Within"
        lbl=("moved_into_range" if (not bi and pi) else "moved_out_of_range" if (bi and not pi) else "stayed")
    return {"label":lbl,"baseline_value":round(bv,3),"baseline_status":bs,"baseline_ref":[blo,bhi],
            "post_value":round(pv,3),"post_status":ps,"post_ref":[plo,phi]}

# 9. build cases
print("[8] building cases ...", flush=True)
os.makedirs(OUT, exist_ok=True)
cases=[]; n_elig={l:0 for l in LABS}; n_lbl={l:0 for l in LABS}
dist={l:defaultdict(int) for l in LABS}; n_all4=0
for h,a in anchor.items():
    at=a["t"]; subj=subj_of.get(h)
    targets,pre_ser,post_ser={},{},{}
    for lab in LABS:
        pre,post=split_series(tgt[h].get(lab,[]),at)
        f=lambda pts:[{"h":x[0],"v":x[1],"ref_low":x[2],"ref_high":x[3]} for x in pts]
        pre_ser[lab],post_ser[lab]=f(pre),f(post)
        elig=len(pre)>=MIN_PRE and len(post)>=MIN_POST
        info={"eligible":elig,"n_pre":len(pre),"n_post":len(post),"label":None}
        if elig:
            n_elig[lab]+=1; info.update(make_label(pre,post))
            if info["label"] is not None: n_lbl[lab]+=1; dist[lab][info["label"]]+=1
        targets[lab]=info
    all4=all(targets[l]["eligible"] and targets[l]["label"] is not None for l in LABS)
    if all4: n_all4+=1
    ctx_base={}
    for name,pts in ctx[h].items():
        pre=sorted([((t-at).total_seconds()/3600,v,lo,hi) for t,v,lo,hi in pts
                    if -PRE_H<=(t-at).total_seconds()/3600<0])
        if pre:
            hh,v,lo,hi=pre[-1]
            ctx_base[name]={"value":round(v,3),"ref_low":lo,"ref_high":hi,
                            "status":range_status(v,lo,hi),"hours_before":round(-hh,2)}
    comorbid={fl:any(c.startswith(pref) for c in hadm_codes[h]) for fl,pref in COMORBIDITY.items()}
    cor=sorted(coronary.get(h,[]),key=lambda x:abs(x[1]))
    desc=(f"IV loop diuretic dose escalation: {a['from']:g} -> {a['to']:g} mg furosemide-equivalent "
          f"({a['drug']} {a['route']}) at t=0.")
    cases.append({
        "case_id":f"BENCHBD_{h}","subject_id":subj,"hadm_id":h,
        "anchor_time":at.strftime("%Y-%m-%d %H:%M:%S"),
        "anchor_description":desc,
        "escalation":{"from_mg_furos_eq":a["from"],"to_mg_furos_eq":a["to"],"drug":a["drug"],"route":a["route"]},
        "state":{
            "demographics":demo.get(subj,{}),
            "admission":adm.get(h,{}),
            "acute_hf_codes":sorted(hadm_codes[h]&ACUTE_HF_CODES),
            "comorbidities":comorbid,
            "coronary_contrast":{"present":bool(cor),
                                 "procedures":[{"icd":c,"offset_days":o} for c,o in cor]},
            "medications_pre_window":{c:list(e.values()) for c,e in meds[h].items()},
            "context_labs_baseline":ctx_base,
            "pre_window_target_labs":{LAB_NAMES[l]:pre_ser[l] for l in LABS},
        },
        "outcome":{
            "window_hours":{"pre":PRE_H,"post":POST_H},
            "post_window_target_labs":{LAB_NAMES[l]:post_ser[l] for l in LABS},
            "targets":{LAB_NAMES[l]:targets[l] for l in LABS},
            "eligible_all_four":all4,
        },
    })

with open(f"{OUT}/cases_all.jsonl","w") as f:
    for c in cases: f.write(json.dumps(c)+"\n")
with open(f"{OUT}/cases_eligible_all4.jsonl","w") as f:
    for c in cases:
        if c["outcome"]["eligible_all_four"]: f.write(json.dumps(c)+"\n")

print("\n===================== SUMMARY =====================")
print(f"Escalation-anchored admissions : {len(cases)}")
print(f"Usable for ALL FOUR labs       : {n_all4}")
print(f"\n{'lab':>20} | {'elig':>5} {'labeled':>7} | into / stayed / out")
print("-"*66)
for l in LABS:
    d=dist[l]
    print(f"{LAB_NAMES[l]:>20} | {n_elig[l]:>5} {n_lbl[l]:>7} | {d['moved_into_range']} / {d['stayed']} / {d['moved_out_of_range']}")
print(f"\nWrote:\n  {OUT}/cases_all.jsonl ({len(cases)})\n  {OUT}/cases_eligible_all4.jsonl ({n_all4})")
