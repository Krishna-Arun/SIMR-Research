#!/usr/bin/env python3
"""
Benchmark A - data index builder
=================================
Pre-extracts, for each eligible acute-HF patient, ALL supplemental data in the
FIRST 24h after admission, plus the ground truth (ICD codes for diagnosis, actual
intervention for treatment). Written to a compact JSON the MCP server loads once.

Eligibility: patient is in the B dialysis cohort or the diuretic-escalation
cohort, AND their intervention anchor occurs > 24h after admission (so the
first-24h window is purely pre-intervention -> leakage-safe).

Served window per case: [admittime, admittime + 24h].
"""
import gzip, csv, json, os, datetime as dt
from collections import defaultdict

REPO = "/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research"
BASE = f"{REPO}/Version_6/acute_hf_cohort/files/mimiciv/3.1"
OUT  = f"{REPO}/Version_6/benchmark_a/index"
WINDOW_H = 24.0

COMORBIDITY = {"aki":("N17","584"),"ckd":("N18","585"),
               "diabetes":("E08","E09","E10","E11","E13","250"),
               "sepsis":("A40","A41","R652","99591","99592","78552"),
               "hypertension":("I10","I11","I12","I13","I15","401","402","403","404","405"),
               "cardiogenic_shock":("R570","78551"),"atrial_fib":("I48","42731"),
               "cad":("I25","414"),"copd":("J44","496"),
               "liver_disease":("K70","K72","K74","571","5722","5723"),
               "esrd_or_dialysis":("N186","Z992","5856","V4511")}
CORONARY_PREFIX = ("8853","8854","8855","8856","8857","3722","3723","0066",
                   "3606","3607","B21","4A023","0270","0271","0272","0273")

def pts(s):
    try: return dt.datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S")
    except Exception: return None
def pdate(s):
    try: return dt.datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except Exception: return None
def fnum(x):
    try: return float(x)
    except Exception: return None

# --- admissions / patients ---
print("[1] admissions + patients ...", flush=True)
admit={}; adm_meta={}; subj_of={}
with gzip.open(f"{BASE}/hosp/admissions.csv.gz","rt") as f:
    r=csv.reader(f); next(r)
    for row in r:
        admit[row[1]]=pts(row[2]); subj_of[row[1]]=row[0]
        adm_meta[row[1]]={"admission_type":row[5],"race":row[12]}
pat={}
with gzip.open(f"{BASE}/hosp/patients.csv.gz","rt") as f:
    r=csv.reader(f); next(r)
    for row in r: pat[row[0]]={"gender":row[1],"age":row[2]}

# --- eligible cases from B dialysis + diuretic cohorts (anchor > 24h post-admit) ---
print("[2] eligible cases (anchor > 24h) ...", flush=True)
cases={}   # case_id -> meta
def load(path, cohort):
    kept=0
    for l in open(path):
        c=json.loads(l); h=c["hadm_id"]; at=pts(c["anchor_time"]); ad=admit.get(h)
        if at is None or ad is None: continue
        if (at-ad).total_seconds()/3600 <= WINDOW_H: continue   # anchor must be after the window
        if cohort=="dialysis":
            interv={"type":"dialysis","detail":c.get("dialysis",{})}
        else:
            interv={"type":"iv_diuretic_escalation","detail":c.get("escalation",{})}
        cid=f"{cohort}_{h}"
        cases[cid]={"case_id":cid,"cohort":cohort,"subject_id":c["subject_id"],"hadm_id":h,
                    "admit":ad,"anchor":at,"first24h_end":ad+dt.timedelta(hours=WINDOW_H),
                    "anchor_time":c["anchor_time"],"intervention":interv}
        kept+=1
    print(f"    {cohort}: {kept} eligible", flush=True)
load(f"{REPO}/Version_6/benchmark_b/cases_all.jsonl","dialysis")
load(f"{REPO}/Version_6/benchmark_b_diuretic/cases_all.jsonl","diuretic")
hadm2cids=defaultdict(list)
for cid,m in cases.items(): hadm2cids[m["hadm_id"]].append(cid)
elig_hadm=set(hadm2cids)
# per-hadm admit + anchor (one cohort per hadm) -> extraction window = [admit, anchor)
admit_of={m["hadm_id"]:m["admit"] for m in cases.values()}
anchor_of={m["hadm_id"]:m["anchor"] for m in cases.values()}
print(f"    total eligible cases: {len(cases)}  (unique admissions: {len(elig_hadm)})", flush=True)

# --- dictionaries ---
print("[3] dictionaries ...", flush=True)
dx_title={}
with gzip.open(f"{BASE}/hosp/d_icd_diagnoses.csv.gz","rt") as f:
    r=csv.reader(f); next(r)
    for row in r: dx_title[(row[0],row[1])]=row[2]
px_title={}
with gzip.open(f"{BASE}/hosp/d_icd_procedures.csv.gz","rt") as f:
    r=csv.reader(f); next(r)
    for row in r: px_title[(row[0],row[1])]=row[2]
labitem={}
with gzip.open(f"{BASE}/hosp/d_labitems.csv.gz","rt") as f:
    r=csv.reader(f); next(r)
    for row in r: labitem[row[0]]={"label":row[1],"fluid":row[2],"category":row[3]}

# --- diagnoses (ground truth + comorbidities) ---
print("[4] diagnoses ...", flush=True)
hadm_codes=defaultdict(list); hadm_codeset=defaultdict(set)
with gzip.open(f"{BASE}/hosp/diagnoses_icd.csv.gz","rt") as f:
    r=csv.reader(f); next(r)
    for row in r:
        h=row[1]
        if h not in elig_hadm: continue
        code,ver,seq=row[3],row[4],row[2]
        hadm_codes[h].append({"icd":code,"version":ver,"seq":int(seq) if seq.isdigit() else None,
                              "title":dx_title.get((code,ver),"")})
        hadm_codeset[h].add(code)

# --- labs in window (ALL labs) ---
print("[5] labs (streaming labevents) ...", flush=True)
labs=defaultdict(lambda: defaultdict(list))   # hadm -> label -> [rows]
with gzip.open(f"{BASE}/hosp/labevents.csv.gz","rt") as f:
    r=csv.reader(f); next(r)   # csv.reader: value/comments may contain commas
    for row in r:
        if len(row)<14: continue
        h=row[2]
        if h not in elig_hadm: continue
        t=pts(row[6])
        if t is None: continue
        if not (admit_of[h] <= t < anchor_of[h]): continue
        it=row[4]; meta=labitem.get(it)
        if not meta: continue
        labs[h][meta["label"]].append({"t":row[6],"value":row[8],"valuenum":fnum(row[9]),
                                       "uom":row[10],"ref_low":fnum(row[11]),"ref_high":fnum(row[12]),
                                       "flag":row[13]})

# --- medications started in window ---
print("[6] medications (streaming prescriptions) ...", flush=True)
meds=defaultdict(list)
with gzip.open(f"{BASE}/hosp/prescriptions.csv.gz","rt") as f:
    r=csv.reader(f); next(r)
    for row in r:
        if len(row)<21: continue
        h=row[1]
        if h not in elig_hadm: continue
        st=pts(row[6])
        if st is None: continue
        if not (admit_of[h] <= st < anchor_of[h]): continue
        meds[h].append({"drug":row[9].strip(),"dose_val":row[15] or None,"dose_unit":row[16] or None,
                        "doses_per_24h":row[19] or None,"route":row[20] or None,"starttime":row[6]})

# --- coronary/contrast procedures in window ---
print("[7] procedures (coronary/contrast) ...", flush=True)
coronary=defaultdict(list)
with gzip.open(f"{BASE}/hosp/procedures_icd.csv.gz","rt") as f:
    r=csv.reader(f); next(r)
    for row in r:
        h=row[1]
        if h not in elig_hadm: continue
        cd=pdate(row[3])
        if cd is None: continue
        if not (admit_of[h].date() <= cd <= anchor_of[h].date()): continue
        code,ver=row[4],row[5]
        if code.startswith(CORONARY_PREFIX):
            coronary[h].append({"icd":code,"title":px_title.get((code,ver),""),"chartdate":row[3]})

# --- assemble ---
print("[8] assembling index ...", flush=True)
os.makedirs(OUT, exist_ok=True)
index={}
for cid,m in cases.items():
    h=m["hadm_id"]; subj=m["subject_id"]; ad=m["admit"]
    comorbid={fl:any(c.startswith(pref) for c in hadm_codeset[h]) for fl,pref in COMORBIDITY.items()}
    index[cid]={
        "case_id":cid,"cohort":m["cohort"],"subject_id":subj,"hadm_id":h,
        "admit":ad.strftime("%Y-%m-%d %H:%M:%S"),
        "first24h_end":m["first24h_end"].strftime("%Y-%m-%d %H:%M:%S"),
        "pretreatment_end":m["anchor"].strftime("%Y-%m-%d %H:%M:%S"),
        "anchor_time":m["anchor_time"],
        "ground_truth":{"icd_codes":sorted(hadm_codes[h],key=lambda x:(x["seq"] or 999)),
                        "intervention":m["intervention"]},
        "supplementals":{
            "demographics":{"gender":pat.get(subj,{}).get("gender"),"age":pat.get(subj,{}).get("age"),
                            **adm_meta.get(h,{})},
            "comorbidities":comorbid,
            "labs":{lab:sorted(rows,key=lambda x:x["t"]) for lab,rows in labs[h].items()},
            "medications":sorted(meds[h],key=lambda x:x["starttime"]),
            "coronary_contrast":sorted(coronary[h],key=lambda x:x["chartdate"]),
        },
    }

with open(f"{OUT}/cases_index.json","w") as f:
    json.dump(index,f)

# summary
import statistics as st
nlabs=[len(e["supplementals"]["labs"]) for e in index.values()]
have_labs=sum(1 for n in nlabs if n>0)
print("\n===================== SUMMARY =====================")
from collections import Counter
print("cases by cohort:", dict(Counter(e["cohort"] for e in index.values())))
print(f"total indexed cases : {len(index)}")
print(f"cases with >=1 lab in first 24h : {have_labs} ({have_labs/len(index):.0%})")
print(f"median distinct labs / case     : {st.median(nlabs):.0f}")
print(f"wrote {OUT}/cases_index.json")
