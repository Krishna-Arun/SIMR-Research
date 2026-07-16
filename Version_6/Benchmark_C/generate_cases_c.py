#!/usr/bin/env python3
"""
Benchmark C v1 - case generation (matched-pair counterfactual discrimination)
=============================================================================
Task: given two matched acute-HF patients' pre-intervention states, the two
candidate interventions (dialysis/UF vs aggressive IV diuresis), and ONE
observed 72h post-state, identify which intervention produced that post-state.

Design (locked):
  Cohort/window/labs : same as Benchmark B (acute-HF, excl ESRD, 48h/72h,
                       core labs creatinine/BUN/potassium/bicarbonate).
  Arm A anchor       : first dialysis session during the admission.
  Arm B anchor       : first IV loop diuretic (no dialysis that admission).
  Eligibility        : >=3 pre & >=3 post for ALL FOUR core labs (identical panel).
  Matching           : exact sex+AKI, caliper 1.5 on standardized
                       [age,creat,bun,k,hco3], creatinine sub-caliper 0.5 mg/dL.
                       -> ~212 balanced pairs (all SMD<0.1 on those 5 covariates).
  Items              : 2 per pair (show each patient's post-state) -> ~424,
                       50/50 balanced. Both pre-states shown, unlabeled +
                       position randomized (seeded).
"""
import gzip, csv, json, os, math, random, datetime as dt
from collections import defaultdict, Counter

REPO = "/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research"
BASE = f"{REPO}/Version_6/acute_hf_cohort/files/mimiciv/3.1"
OUT  = f"{REPO}/Version_6/benchmark_c"
SEED = 20260713
PRE_H, POST_H, MIN_PRE, MIN_POST = 48, 72, 3, 3
CALIPER, CREAT_BAND = 1.5, 0.5

ACUTE_HF_CODES = {"I5021","I5023","I5031","I5033","I5041","I5043","I50811","I50813",
                  "42821","42823","42831","42833","42841","42843"}
EXCLUDE_CODES  = {"N186","Z992","5856","V4511","V560","Z4901","Z4902","Z4931"}
DIALYSIS_ITEMS = {225441,225802,225803,225809,225955,225805}
TARGET_ITEMS = {50912:"creat",52546:"creat",51006:"bun",52647:"bun",
                50971:"k",52610:"k",50882:"hco3"}
LAB_NAMES = {"creat":"Creatinine","bun":"BUN (Urea Nitrogen)","k":"Potassium","hco3":"Bicarbonate"}
CORE = ["creat","bun","k","hco3"]
CONTEXT_ITEMS = {50813:"Lactate",52442:"Lactate",53154:"Lactate",50820:"pH",50818:"pCO2",
                 51222:"Hemoglobin",50862:"Albumin",53085:"Albumin",50931:"Glucose",52569:"Glucose",
                 50893:"Calcium",50960:"Magnesium",50970:"Phosphate",50963:"NTproBNP"}
LOOP_KW = ["furosemide","lasix","bumetanide","bumex","torsemide","torasemide"]
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

# --- 1. diagnoses ---
print("[1] diagnoses ...", flush=True)
ahf, hadm_codes = set(), defaultdict(set)
with gzip.open(f"{BASE}/hosp/diagnoses_icd.csv.gz","rt") as f:
    r=csv.reader(f); next(r)
    for row in r:
        h,c=row[1],row[3]
        if c in ACUTE_HF_CODES: ahf.add(h)
        hadm_codes[h].add(c)

# --- 2. dialysis anchors (arm A) ---
print("[2] dialysis anchors ...", flush=True)
dialA={}; dial_admissions=set()
with gzip.open(f"{BASE}/icu/procedureevents.csv.gz","rt") as f:
    r=csv.reader(f); next(r)
    for row in r:
        h=row[1]; start=parse_ts(row[4])
        try: it=int(row[7])
        except ValueError: continue
        if h not in ahf or it not in DIALYSIS_ITEMS or start is None: continue
        dial_admissions.add(h)
        if h not in dialA or start<dialA[h]["t"]:
            dialA[h]={"t":start,"subject":row[0],"arm":"dialysis","detail":it}
dialA={h:v for h,v in dialA.items() if not (hadm_codes[h]&EXCLUDE_CODES)}

# --- 3. IV loop diuretic anchors (arm B) ---
print("[3] IV-diuretic anchors ...", flush=True)
diurB={}
with gzip.open(f"{BASE}/hosp/prescriptions.csv.gz","rt") as f:
    r=csv.reader(f); next(r)
    for row in r:
        if len(row)<21: continue
        h=row[1]
        if h not in ahf or h in dial_admissions or (hadm_codes[h]&EXCLUDE_CODES): continue
        drug=row[9].lower(); route=(row[20] or "").upper()
        if "IV" not in route or not any(k in drug for k in LOOP_KW): continue
        start=parse_ts(row[6])
        if start is None: continue
        if h not in diurB or start<diurB[h]["t"]:
            diurB[h]={"t":start,"subject":row[0],"arm":"diuresis","detail":row[9].strip()}
print(f"    arm A={len(dialA)}  arm B={len(diurB)}", flush=True)
anchor={**dialA,**diurB}; anch=set(anchor)

# --- 4. labs (target + context, with ref ranges) ---
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

# --- 5. demographics ---
print("[5] demographics ...", flush=True)
demo={}; adm={}
with gzip.open(f"{BASE}/hosp/patients.csv.gz","rt") as f:
    r=csv.reader(f); next(r)
    for row in r:
        try: age=float(row[2])
        except ValueError: age=None
        demo[row[0]]={"gender":row[1],"age":row[2],"age_num":age}
with gzip.open(f"{BASE}/hosp/admissions.csv.gz","rt") as f:
    r=csv.reader(f); next(r)
    for row in r: adm[row[1]]={"admission_type":row[5],"race":row[12]}

# --- 6. eligibility + covariates (all 4 labs >=3/>=3) ---
def split(pts, at):
    pre=sorted([(round((t-at).total_seconds()/3600,2),v,lo,hi) for t,v,lo,hi in pts
                if -PRE_H<=(t-at).total_seconds()/3600<0])
    post=sorted([(round((t-at).total_seconds()/3600,2),v,lo,hi) for t,v,lo,hi in pts
                 if 0<(t-at).total_seconds()/3600<=POST_H])
    return pre,post

def eligible(arm_anchor):
    rows={}
    for h,v in arm_anchor.items():
        at=v["t"]; ser={}; ok=True
        for lab in CORE:
            pre,post=split(tgt[h].get(lab,[]),at)
            if len(pre)<MIN_PRE or len(post)<MIN_POST: ok=False; break
            ser[lab]=(pre,post)
        if not ok: continue
        d=demo.get(v["subject"],{})
        if d.get("age_num") is None: continue
        rows[h]={"hadm":h,"subject":v["subject"],"at":at,"arm":v["arm"],"detail":v["detail"],
                 "sex":d["gender"],"age":d["age_num"],"ser":ser,
                 "creat":ser["creat"][0][-1][1],"bun":ser["bun"][0][-1][1],
                 "k":ser["k"][0][-1][1],"hco3":ser["hco3"][0][-1][1],
                 "aki":any(c.startswith(COMORBIDITY["aki"]) for c in hadm_codes[h])}
    return rows

print("[6] eligibility ...", flush=True)
A=eligible(dialA); B=eligible(diurB)
print(f"    eligible A={len(A)} B={len(B)}", flush=True)

# --- 7. matching (exact sex+aki, caliper on z-scored [age,creat,bun,k,hco3], creat sub-caliper) ---
CONT=["age","creat","bun","k","hco3"]
pool=list(A.values())+list(B.values())
mean={c:sum(r[c] for r in pool)/len(pool) for c in CONT}
std ={c:(sum((r[c]-mean[c])**2 for r in pool)/len(pool))**.5 or 1.0 for c in CONT}
def dist(x,y): return math.sqrt(sum(((x[c]-mean[c])/std[c]-(y[c]-mean[c])/std[c])**2 for c in CONT))
print("[7] matching ...", flush=True)
Bl=list(B.values()); used=set(); pairs=[]
for a in sorted(A.values(), key=lambda r:r["creat"]):
    best=None; bd=1e9
    for i,b in enumerate(Bl):
        if i in used or b["sex"]!=a["sex"] or b["aki"]!=a["aki"]: continue
        if abs(a["creat"]-b["creat"])>CREAT_BAND: continue
        dd=dist(a,b)
        if dd<bd: bd,best=dd,i
    if best is not None and bd<=CALIPER:
        used.add(best); pairs.append((a,Bl[best]))
print(f"    matched pairs={len(pairs)}", flush=True)
# balance report
def smd(c):
    av=[a[c] for a,_ in pairs]; bv=[b[c] for _,b in pairs]
    ma,mb=sum(av)/len(av),sum(bv)/len(bv)
    sa=(sum((x-ma)**2 for x in av)/len(av))**.5; sb=(sum((x-mb)**2 for x in bv)/len(bv))**.5
    return abs(ma-mb)/(math.sqrt((sa**2+sb**2)/2) or 1.0)
balance={c:round(smd(c),3) for c in CONT}
print(f"    SMD (5 core covariates): {balance}", flush=True)
matched=set()
for a,b in pairs: matched.add(a["hadm"]); matched.add(b["hadm"])

# --- 8. coronary/contrast for matched ---
print("[8] coronary/contrast ...", flush=True)
coronary=defaultdict(list)
with gzip.open(f"{BASE}/hosp/procedures_icd.csv.gz","rt") as f:
    r=csv.reader(f); next(r)
    for row in r:
        h=row[1]; cd=parse_date(row[3]); code=row[4]
        if h not in matched or cd is None: continue
        if code.startswith(CORONARY_PREFIX):
            coronary[h].append((code,(cd-anchor[h]["t"].date()).days))

# --- 9. meds (with dose) for matched, pre-window ---
print("[9] medications ...", flush=True)
meds=defaultdict(lambda: defaultdict(dict))
with gzip.open(f"{BASE}/hosp/prescriptions.csv.gz","rt") as f:
    r=csv.reader(f); next(r)
    for row in r:
        if len(row)<21: continue
        h=row[1]
        if h not in matched: continue
        start,stop,drug=parse_ts(row[6]),parse_ts(row[7]),row[9]
        if start is None or not drug: continue
        at=anchor[h]["t"]; ws=at-dt.timedelta(hours=PRE_H)
        if not (start<at and (stop is None or stop>ws)): continue
        for cls in classify_drug(drug):
            key=(drug.strip(),row[15],row[16],row[20])
            meds[h][cls][key]={"drug":drug.strip(),"dose_val":row[15] or None,
                               "dose_unit":row[16] or None,"doses_per_24h":row[19] or None,
                               "route":row[20] or None}

# --- 10. build per-patient state ---
def prestate(rec):
    h=rec["hadm"]; at=rec["at"]; subj=rec["subject"]
    def fmt(pts): return [{"h":x[0],"v":x[1],"ref_low":x[2],"ref_high":x[3]} for x in pts]
    ctx_base={}
    for name,pts in ctx[h].items():
        pre=sorted([((t-at).total_seconds()/3600,v,lo,hi) for t,v,lo,hi in pts
                    if -PRE_H<=(t-at).total_seconds()/3600<0])
        if pre:
            _,v,lo,hi=pre[-1]
            ctx_base[name]={"value":round(v,3),"ref_low":lo,"ref_high":hi,"status":range_status(v,lo,hi)}
    return {
        "demographics":{"gender":demo[subj]["gender"],"age":demo[subj]["age"]},
        "admission":adm.get(h,{}),
        "comorbidities":{fl:any(c.startswith(pref) for c in hadm_codes[h]) for fl,pref in COMORBIDITY.items()},
        "coronary_contrast":{"present":bool(coronary.get(h)),
                             "procedures":[{"icd":c,"offset_days":o} for c,o in sorted(coronary.get(h,[]),key=lambda x:abs(x[1]))]},
        "medications_pre_window":{c:list(e.values()) for c,e in meds[h].items()},
        "context_labs_baseline":ctx_base,
        "pre_window_target_labs":{LAB_NAMES[l]:fmt(rec["ser"][l][0]) for l in CORE},
    }
def poststate(rec):
    return {LAB_NAMES[l]:[{"h":x[0],"v":x[1],"ref_low":x[2],"ref_high":x[3]} for x in rec["ser"][l][1]] for l in CORE}

INTERVENTIONS={
  "dialysis":"Renal replacement therapy (dialysis / ultrafiltration): mechanically removes solutes (creatinine, urea, potassium) and fluid, and corrects acidosis with buffer.",
  "diuresis":"Aggressive IV loop diuresis (high-dose IV furosemide/bumetanide/torsemide): drives renal fluid and sodium excretion; may raise creatinine/BUN (pre-renal) and cause contraction alkalosis / potassium wasting.",
}

# --- 11. emit items (2 per pair; show each post-state; both pre-states, position randomized) ---
print("[11] building items ...", flush=True)
os.makedirs(OUT, exist_ok=True)
rng=random.Random(SEED)
items=[]
for pi,(a,b) in enumerate(pairs):
    sa, sb = prestate(a), prestate(b)   # a=dialysis, b=diuresis
    for shown in (a,b):                 # one item per patient's observed post-state
        order=[("P1",sa),("P2",sb)] if rng.random()<0.5 else [("P1",sb),("P2",sa)]
        items.append({
            "item_id":f"BENCHC_{pi}_{shown['arm']}",
            "pair_id":pi,
            "window_hours":{"pre":PRE_H,"post":POST_H},
            "interventions":INTERVENTIONS,
            "patients":{lbl:st for lbl,st in order},   # two matched pre-states, unlabeled
            "observed_post_state":poststate(shown),
            "answer":shown["arm"],                     # "dialysis" | "diuresis"
            "meta":{"dialysis_hadm":a["hadm"],"diuresis_hadm":b["hadm"],
                    "shown_hadm":shown["hadm"],"shown_arm":shown["arm"]},
        })

with open(f"{OUT}/cases_c.jsonl","w") as f:
    for it in items: f.write(json.dumps(it)+"\n")

dist_lbl=Counter(it["answer"] for it in items)
print("\n===================== SUMMARY =====================")
print(f"Matched pairs        : {len(pairs)}")
print(f"SMD (5 covariates)   : {balance}")
print(f"Items                : {len(items)}  (label balance: {dict(dist_lbl)})")
print(f"Wrote                : {OUT}/cases_c.jsonl")
