#!/usr/bin/env python3
"""
Benchmark C feasibility: matched pairs of acute-HF patients, one dialyzed vs one
aggressively IV-diuresed (no dialysis), similar at baseline.

Reuses B's cohort (acute-HF, exclude chronic-dialysis/ESRD), window (48h/72h),
and core labs. Reports arm sizes and how many 1:1 matched pairs survive at
several calipers, with a covariate-balance (SMD) check.
"""
import gzip, csv, datetime as dt, math
from collections import defaultdict

REPO = "/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research"
BASE = f"{REPO}/Version_6/acute_hf_cohort/files/mimiciv/3.1"
PRE_H, POST_H, MIN_PRE, MIN_POST = 48, 72, 3, 3

ACUTE_HF_CODES = {"I5021","I5023","I5031","I5033","I5041","I5043","I50811","I50813",
                  "42821","42823","42831","42833","42841","42843"}
EXCLUDE_CODES  = {"N186","Z992","5856","V4511","V560","Z4901","Z4902","Z4931"}
DIALYSIS_ITEMS = {225441,225802,225803,225809,225955,225805}
TARGET = {50912:"creat",52546:"creat",51006:"bun",52647:"bun",
          50971:"k",52610:"k",50882:"hco3"}
LOOP_KW = ["furosemide","lasix","bumetanide","bumex","torsemide","torasemide"]
AKI_PREFIX = ("N17","584")

def parse_ts(s):
    try: return dt.datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S")
    except Exception: return None
def fnum(x):
    try: return float(str(x).split("-")[-1])   # ranges "80-160" -> 160
    except Exception: return None

# 1. diagnoses -> acute-HF set, per-admission codes
print("[1] diagnoses ...", flush=True)
ahf, hadm_codes = set(), defaultdict(set)
with gzip.open(f"{BASE}/hosp/diagnoses_icd.csv.gz","rt") as f:
    r=csv.reader(f); next(r)
    for row in r:
        hadm, code = row[1], row[3]
        if code in ACUTE_HF_CODES: ahf.add(hadm)
        hadm_codes[hadm].add(code)

# 2. dialysis anchors (arm A) + set of admissions with ANY dialysis
print("[2] dialysis anchors (arm A) ...", flush=True)
dial_anchor = {}
dial_admissions = set()
with gzip.open(f"{BASE}/icu/procedureevents.csv.gz","rt") as f:
    r=csv.reader(f); next(r)
    for row in r:
        hadm=row[1]; start=parse_ts(row[4])
        try: it=int(row[7])
        except ValueError: continue
        if hadm not in ahf or it not in DIALYSIS_ITEMS or start is None: continue
        dial_admissions.add(hadm)
        if hadm not in dial_anchor or start<dial_anchor[hadm]["t"]:
            dial_anchor[hadm]={"t":start,"subject":row[0]}
# exclude chronic-dialysis/ESRD
dial_anchor={h:v for h,v in dial_anchor.items() if not (hadm_codes[h]&EXCLUDE_CODES)}

# 3. IV loop diuretic anchors (arm B): first IV loop, no dialysis, no ESRD
print("[3] IV-diuretic anchors (arm B, streaming prescriptions) ...", flush=True)
diur_anchor={}
with gzip.open(f"{BASE}/hosp/prescriptions.csv.gz","rt") as f:
    r=csv.reader(f); next(r)
    for row in r:
        if len(row)<21: continue
        hadm=row[1]
        if hadm not in ahf: continue
        if hadm in dial_admissions or (hadm_codes[hadm]&EXCLUDE_CODES): continue
        drug=row[9].lower(); route=(row[20] or "").upper()
        if "IV" not in route: continue
        if not any(k in drug for k in LOOP_KW): continue
        start=parse_ts(row[6])
        if start is None: continue
        if hadm not in diur_anchor or start<diur_anchor[hadm]["t"]:
            diur_anchor[hadm]={"t":start,"subject":row[0]}
print(f"    arm A (dialysis) anchored: {len(dial_anchor)}  |  arm B (IV diuretic) anchored: {len(diur_anchor)}",
      flush=True)

anchors={**{h:("A",v) for h,v in dial_anchor.items()},
         **{h:("B",v) for h,v in diur_anchor.items()}}
anch=set(anchors)

# 4. core labs for anchored admissions
print("[4] core labs (streaming labevents) ...", flush=True)
labs=defaultdict(lambda: defaultdict(list))
with gzip.open(f"{BASE}/hosp/labevents.csv.gz","rt") as f:
    next(f)
    for line in f:
        p=line.split(",")
        if len(p)<10: continue
        hadm=p[2]
        if hadm not in anch: continue
        try: it=int(p[4])
        except ValueError: continue
        lab=TARGET.get(it)
        if lab is None: continue
        t=parse_ts(p[6]); v=fnum(p[9])
        if t is None or v is None: continue
        labs[hadm][lab].append((t,v))

# 5. demographics
print("[5] demographics ...", flush=True)
demo={}
with gzip.open(f"{BASE}/hosp/patients.csv.gz","rt") as f:
    r=csv.reader(f); next(r)
    for row in r:
        try: age=float(row[2])
        except ValueError: age=None
        demo[row[0]]={"sex":row[1],"age":age}

# 6. build eligible covariate rows per arm
# apples-to-apples: require >=MIN pre & post for ALL FOUR core labs in both arms
CORE=["creat","bun","k","hco3"]
def baseline(hadm, lab, at):
    pre=sorted((t,v) for t,v in labs[hadm].get(lab,[]) if -PRE_H<=(t-at).total_seconds()/3600<0)
    post=sum(1 for t,_ in labs[hadm].get(lab,[]) if 0<(t-at).total_seconds()/3600<=POST_H)
    return (pre[-1][1] if pre else None), len(pre), post

def build(arm_anchor):
    out=[]
    for hadm,v in arm_anchor.items():
        at=v["t"]; subj=v["subject"]
        base={}; ok=True
        for lab in CORE:
            bv,npre,npost=baseline(hadm,lab,at)
            if bv is None or npre<MIN_PRE or npost<MIN_POST: ok=False; break
            base[lab]=bv
        if not ok: continue
        d=demo.get(subj,{})
        if d.get("age") is None: continue
        out.append({"hadm":hadm,"subject":subj,"sex":d["sex"],"age":d["age"],
                    "creat":base["creat"],"bun":base["bun"],"k":base["k"],"hco3":base["hco3"],
                    "aki":any(c.startswith(AKI_PREFIX) for c in hadm_codes[hadm])})
    return out

A=build(dial_anchor); B=build(diur_anchor)
print(f"\n    eligible (>=3/>=3 creatinine + full baseline):  arm A={len(A)}  arm B={len(B)}", flush=True)

# 7. standardize continuous covariates over pooled eligible
CONT=["age","creat","bun","k","hco3"]
pooled=A+B
mean={c:sum(r[c] for r in pooled)/len(pooled) for c in CONT}
std ={c:(sum((r[c]-mean[c])**2 for r in pooled)/len(pooled))**0.5 or 1.0 for c in CONT}
def vec(r): return [ (r[c]-mean[c])/std[c] for c in CONT ]
def dist(x,y): return math.sqrt(sum((a-b)**2 for a,b in zip(vec(x),vec(y))))

# 8. greedy 1:1 matching: exact on (sex, aki), overall caliper + creatinine sub-caliper (raw mg/dL)
def match(caliper, creat_band):
    used=set(); pairs=[]
    for a in sorted(A, key=lambda r:r["creat"]):
        best=None; bd=1e9
        for i,b in enumerate(B):
            if i in used: continue
            if b["sex"]!=a["sex"] or b["aki"]!=a["aki"]: continue
            if abs(a["creat"]-b["creat"])>creat_band: continue   # creatinine sub-caliper
            dd=dist(a,b)
            if dd<bd: bd, best = dd, i
        if best is not None and bd<=caliper:
            used.add(best); pairs.append((a,B[best],bd))
    return pairs

def smds(pairs):
    out=[]
    for c in CONT:
        av=[p[0][c] for p in pairs]; bv=[p[1][c] for p in pairs]
        ma,mb=sum(av)/len(av),sum(bv)/len(bv)
        sa=(sum((x-ma)**2 for x in av)/len(av))**.5; sb=(sum((x-mb)**2 for x in bv)/len(bv))**.5
        sp=math.sqrt((sa**2+sb**2)/2) or 1.0
        out.append(abs(ma-mb)/sp)
    return out

print(f"\nSweeping creatinine sub-caliper (overall caliper fixed at 1.5):")
print(f"{'creat_band(mg/dL)':>18} | {'pairs':>6} | SMD age/creat/bun/k/hco3 | all<0.1?")
print("-"*74)
best_cfg=None
for band in [0.20,0.25,0.30,0.35,0.40,0.50]:
    pairs=match(1.5, band)
    if not pairs: print(f"{band:>18} | {0:>6} |"); continue
    ss=smds(pairs); allok=all(s<0.1 for s in ss)
    print(f"{band:>18} | {len(pairs):>6} | "+" ".join(f"{s:.2f}" for s in ss)+f" | {'YES' if allok else 'no'}")
    if allok and (best_cfg is None or len(pairs)>best_cfg[1]):
        best_cfg=(band,len(pairs))
if best_cfg:
    print(f"\n>> Largest all-SMD<0.1 config: creat_band={best_cfg[0]} mg/dL -> {best_cfg[1]} matched pairs")
else:
    print("\n>> No config kept all SMDs <0.1; loosen creat_band or accept ~0.1-0.15 on creatinine.")
