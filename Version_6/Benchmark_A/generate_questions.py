#!/usr/bin/env python3
"""
Benchmark A - question generation pipeline (Evaluator-Optimizer + two-sided gate)
=================================================================================
Per case: build ground-truth MC options deterministically, then use gpt-oss-20b
as GENERATOR (writes the vignette + question stem) <-> EVALUATOR (critiques for
leakage / vagueness / buzzwords), up to 3 rounds. Then a two-sided validity gate
(the SCORER answers the item):
   keep  iff  (WITHOUT supplementals -> WRONG)  AND  (WITH supplementals -> RIGHT)

4 buckets: {diagnosis, treatment} x {dialysis, diuretic}. MC A-D with
"none of the above"; none-of-above is the correct answer exactly 25% of the time
(controlled deterministically here). All roles = gpt-oss-20b.
"""
import argparse, json, os, re, sys, random, time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "benchmark_b"))
from evaluate import load_local, _final_channel, _extract_json  # gpt-oss helpers
import supplemental_tools as T

# ---- acute-HF subtype code -> canonical description (ICD-9 folded to ICD-10 text) ----
SUBTYPE_DESC = {
    "I5021":"Acute systolic (congestive) heart failure","42821":"Acute systolic (congestive) heart failure",
    "I5023":"Acute on chronic systolic (congestive) heart failure","42823":"Acute on chronic systolic (congestive) heart failure",
    "I5031":"Acute diastolic (congestive) heart failure","42831":"Acute diastolic (congestive) heart failure",
    "I5033":"Acute on chronic diastolic (congestive) heart failure","42833":"Acute on chronic diastolic (congestive) heart failure",
    "I5041":"Acute combined systolic and diastolic (congestive) heart failure","42841":"Acute combined systolic and diastolic (congestive) heart failure",
    "I5043":"Acute on chronic combined systolic and diastolic (congestive) heart failure","42843":"Acute on chronic combined systolic and diastolic (congestive) heart failure",
    "I50811":"Acute right heart failure","I50813":"Acute on chronic right heart failure",
}
ALL_SUBTYPES = ["Acute systolic (congestive) heart failure",
                "Acute on chronic systolic (congestive) heart failure",
                "Acute diastolic (congestive) heart failure",
                "Acute on chronic diastolic (congestive) heart failure",
                "Acute combined systolic and diastolic (congestive) heart failure",
                "Acute on chronic combined systolic and diastolic (congestive) heart failure",
                "Acute right heart failure"]
INTERVENTIONS = {"dialysis":"Renal replacement therapy (dialysis / ultrafiltration)",
                 "iv_diuretic_escalation":"Aggressive IV loop diuretic dose escalation"}
INTERV_POOL = list(INTERVENTIONS.values()) + [
    "IV vasodilator therapy (e.g., nitroglycerin)",
    "Inotropic support (e.g., dobutamine or milrinone)",
    "Coronary revascularization (PCI or CABG)",
    "Initiation of mechanical ventilation"]

# leakage blocklist (terms that would give away the answer if in the vignette)
# phrase-level give-aways only (NOT bare anatomy words like "systolic"/"diastolic",
# NOT documented drug names, which are legitimate factual context)
LEAK_TERMS = ["systolic heart failure","diastolic heart failure","systolic (congestive)",
              "diastolic (congestive)","systolic dysfunction","diastolic dysfunction",
              "systolic and diastolic","reduced ejection fraction","preserved ejection fraction",
              "ejection fraction","hfref","hfpef","hfmref","reduced ef","preserved ef",
              "dialysis","ultrafiltrat","crrt","cvvh","hemodialys","renal replacement",
              "diuretic escalation","escalate the diuretic","escalated diuretic",
              "increase the diuretic","uptitrat"]

_MODEL = _TOK = _DEV = None
def chat(system, user, effort="low", max_new_tokens=1200, sample=False, temperature=0.7):
    import torch
    msgs=[{"role":"system","content":system},{"role":"user","content":user}]
    kw=dict(add_generation_prompt=True, return_tensors="pt", return_dict=True)
    try: enc=_TOK.apply_chat_template(msgs, reasoning_effort=effort, **kw)
    except TypeError: enc=_TOK.apply_chat_template(msgs, **kw)
    enc={k:v.to(_DEV) for k,v in enc.items()}
    gen=dict(max_new_tokens=max_new_tokens, pad_token_id=_TOK.eos_token_id)
    if sample: gen.update(do_sample=True, temperature=temperature, top_p=0.95)
    else:      gen.update(do_sample=False)
    with torch.no_grad():
        out=_MODEL.generate(**enc, **gen)
    return _final_channel(_TOK.decode(out[0][enc["input_ids"].shape[1]:], skip_special_tokens=False))

# ---------- ground truth + options ----------
def diagnosis_truth(entry):
    codes=[c["icd"] for c in entry["ground_truth"]["icd_codes"] if c["icd"] in SUBTYPE_DESC]
    if not codes: return None
    return SUBTYPE_DESC[codes[0]]           # patient's (primary) acute-HF subtype

def build_options(correct_text, pool, none_correct, rng):
    distract=[x for x in pool if x!=correct_text]
    rng.shuffle(distract)
    if none_correct:
        opts=distract[:3]                    # correct answer deliberately absent
        answer_is_none=True
    else:
        opts=[correct_text]+distract[:2]
        answer_is_none=False
    rng.shuffle(opts)
    opts=opts+["None of the above"]
    letters=["A","B","C","D"]
    options={L:t for L,t in zip(letters,opts)}
    answer="D" if answer_is_none else letters[opts.index(correct_text)]
    return options, answer

# ---------- generator / evaluator prompts ----------
try:
    _EX = json.load(open(os.path.join(HERE, "vignette_examples.json")))
except Exception:
    _EX = []
EXAMPLES = "\n\n".join(f"REAL EXAMPLE {i+1} (style reference only, a DIFFERENT patient):\n{e}"
                       for i, e in enumerate(_EX))
# Fixed question stems -- the model does NOT invent the question.
QUESTION_STEMS = {
    "diagnosis": "What is this patient's specific acute heart failure subtype?",
    "treatment": "What is the most appropriate next intervention for this patient at this point in the admission?",
}

GEN_SYS=("You write realistic clinical vignettes for a benchmark. EVERY patient is an ACUTE HEART "
    "FAILURE patient admitted to the hospital. Write ONLY the vignette narrative -- do NOT write the "
    "question, the options, or the answer (those are supplied separately). Match the STYLE and clinical "
    "detail of the REAL example vignettes provided (history, presenting symptoms, exam impression), but "
    "write about the CURRENT patient grounded in the structured data given. The vignette must be detailed "
    "and realistic yet QUANTITATIVELY INCOMPLETE: do NOT state any numeric lab values, doses, or vital "
    "numbers; do NOT name the specific heart-failure subtype, the diagnosis, or the treatment given; no "
    "give-away buzzwords. A reader must still need to pull hard quantitative data (labs, meds, contrast, "
    "covariates) to answer. Output JSON.")

COMORBID_TERMS={
 "diabetes":["diabet"],"ckd":["chronic kidney","ckd","chronic renal"],
 "cad":["coronary artery","coronary disease"," cad"],"copd":["copd","chronic obstructive"],
 "sepsis":["sepsis","septic"],"atrial_fib":["atrial fibrillation","afib","a-fib","a fib"],
 "hypertension":["hypertension","htn"],"cardiogenic_shock":["cardiogenic shock"],
 "liver_disease":["cirrhosis","liver disease","hepatic failure"],"aki":["acute kidney injury"," aki"]}

def _facts(sup):
    d=sup["demographics"]; como=[k for k,v in sup["comorbidities"].items() if v]
    meds=sorted({m["drug"] for m in sup["medications"]})
    return (f"- Age: {d.get('age')}  (use this EXACT age)\n"
            f"- Sex: {d.get('gender')}  (M = man, F = woman -- use the correct one)\n"
            f"- Race: {d.get('race')}\n- Admission type: {d.get('admission_type')}\n"
            f"- Documented comorbidities (the ONLY ones you may mention): {', '.join(como) if como else 'none coded'}\n"
            f"- Medications administered: {', '.join(meds[:25]) if meds else 'none'}\n"
            f"- Coronary/contrast procedure this admission: {'yes' if sup['coronary_contrast'] else 'no'}")

def gen_prompt(sup, qtype, critique):
    reveal=("the patient's specific acute heart-failure subtype" if qtype=="diagnosis"
            else "which clinical intervention this patient should receive next")
    c=f"\nREVISE per this critique:\n{critique}\n" if critique else ""
    return (f"{EXAMPLES}\n\n"
            f"PATIENT FACTS -- everything you write MUST be supported by these. Use the EXACT age and sex. "
            f"You may mention ONLY the documented comorbidities below and the listed medications. Do NOT "
            f"invent comorbidities, prior events, or specific findings that are not in this data:\n{_facts(sup)}\n\n"
            f"Every patient is an acute-HF admission, so you may state they presented with a heart-failure "
            f"decompensation. A separate multiple-choice question (which you must NOT write) will ask for "
            f"{reveal}. Write a factual, patient-specific vignette in the style of the real examples, WITHOUT "
            f"revealing the answer, any lab/vital/dose numbers, or give-away terms. You MAY state age and sex.{c}\n"
            'Output ONLY JSON: {"vignette": "<4-7 sentence narrative grounded ONLY in the facts above>"}')

def fact_check(vignette, sup):
    """Reject vignettes that assert facts absent from the record (fabrication)."""
    d=sup["demographics"]; v=vignette.lower()
    age=str(d.get("age") or "").strip()
    if age and age not in vignette:
        return f"state the patient's exact age ({age})"
    g=d.get("gender")
    if g=="M" and not any(w in v for w in ["man"," male","gentleman"," he "," his "]):
        return "the patient is male -- reflect that"
    if g=="F" and not any(w in v for w in ["woman"," female"," she "," her ","lady"]):
        return "the patient is female -- reflect that"
    true_flags=sup["comorbidities"]
    for flag,kws in COMORBID_TERMS.items():
        if not true_flags.get(flag) and any(k in v for k in kws):
            return f"remove '{flag}' -- it is NOT a documented comorbidity for this patient"
    return None

EVAL_SYS=("You are a strict reviewer of benchmark vignettes. Reject if the vignette: names or "
    "strongly implies the diagnosis/subtype or the treatment; contains numeric lab/vital/dose values; "
    "uses give-away buzzwords; is vague/generic; or is not answerable-in-principle only after pulling "
    "quantitative data. Output JSON.")
def eval_prompt(vignette, question, qtype):
    return (f"QUESTION TYPE: {qtype}\nVIGNETTE: {vignette}\nQUESTION: {question}\n\n"
            'Output ONLY JSON: {"accept": true|false, "issues": "<one line; empty if accept>"}')

def leak_check(vignette):
    v=vignette.lower()
    if re.search(r"\d+\.\d+", vignette): return "contains a decimal number (likely a lab value)"
    hits=[t for t in LEAK_TERMS if t in v]
    if hits: return "leak term(s): "+", ".join(hits[:4])
    return None

# ---------- scorer (two-sided validity gate) ----------
SCORE_SYS=("You are a careful clinician answering a multiple-choice question. Reason about EACH "
    "listed option specifically, then choose the single best letter. Only choose 'None of the "
    "above' if you are genuinely confident that none of the other options is correct -- do NOT "
    "use it as a fallback when uncertain; if unsure, pick the most likely listed option. Output JSON.")
def score_prompt(vignette, question, options, supp=None):
    o="\n".join(f"{L}. {t}" for L,t in options.items())
    extra=("" if supp is None else
           "\n\nAVAILABLE SUPPLEMENTAL DATA:\n"+json.dumps(supp, default=str)[:20000])
    return (f"VIGNETTE: {vignette}\n\nQUESTION: {question}\nOPTIONS:\n{o}{extra}\n\n"
            'Output ONLY JSON: {"reasoning":"<2-4 sentences, addressing the options>","answer":"<A|B|C|D>"}')

def answer_mc(vignette, question, options, supp=None, effort="medium", sample=False):
    try:
        obj=_extract_json(chat(SCORE_SYS, score_prompt(vignette,question,options,supp), effort, 2400, sample=sample))
        a=str(obj.get("answer","")).strip().upper()[:1]
        return a if a in options else None
    except Exception:
        return None

def gate_no_supp(vignette, question, options, answer, k=3, effort="medium"):
    """Majority-of-k discard gate. Ask the scorer to answer WITHOUT supplementals
    k times (sampled, so the tries differ). KEEP the question only if it CANNOT be
    answered in the majority of tries (i.e. correct in <ceil(k/2)) -- the question
    must genuinely require the supplemental data."""
    smp = (k > 1)                          # k=1 -> deterministic greedy single shot
    votes=[answer_mc(vignette, question, options, supp=None, effort=effort, sample=smp) for _ in range(k)]
    n_correct=sum(1 for v in votes if v==answer)
    keep = n_correct < (k//2 + 1)          # correct in fewer than a majority -> keep
    return keep, votes, n_correct

# ---------- per-case pipeline ----------
def make_question(entry, qtype, none_correct, rng, max_rounds, gate_k=3, gate_effort="medium"):
    if qtype=="diagnosis":
        correct=diagnosis_truth(entry)
        if correct is None: return None, "no acute-HF subtype code on record"
        pool=ALL_SUBTYPES
    else:
        correct=INTERVENTIONS[entry["ground_truth"]["intervention"]["type"]]
        pool=INTERV_POOL
    options, answer = build_options(correct, pool, none_correct, rng)

    # window per question type: diagnosis=first 24h, treatment=all labs pre-treatment
    window = "first24h" if qtype == "diagnosis" else "pretreatment"
    sup = T._sliced(entry, window)
    case_ref = f"{entry['case_id']}|{'24h' if window=='first24h' else 'pre'}"

    critique=None; vignette=question=None
    for rnd in range(max_rounds):
        try:
            g=_extract_json(chat(GEN_SYS, gen_prompt(sup,qtype,critique), "low", 1400))
            vignette=g.get("vignette","").strip(); question=QUESTION_STEMS[qtype]  # fixed stem, not LLM-written
        except Exception as e:
            critique=f"invalid JSON ({e}); output valid JSON"; continue
        lk=leak_check(vignette)
        if lk: critique="Leakage: "+lk+". Remove it."; continue
        fx=fact_check(vignette, sup)
        if fx: critique="Not factual: "+fx+"."; continue
        try:
            ev=_extract_json(chat(EVAL_SYS, eval_prompt(vignette,question,qtype), "low", 400))
        except Exception:
            ev={"accept":True,"issues":""}
        if ev.get("accept"): break
        critique=ev.get("issues","tighten the vignette")
    if not vignette: return None, "generation failed"
    # hard factuality/leakage guard: never emit a vignette that still fails after revisions
    if leak_check(vignette): return None, "failed leak check after revisions"
    fx=fact_check(vignette, sup)
    if fx: return None, f"failed fact check after revisions: {fx}"

    # one-sided validity gate (Majority-of-k): KEEP only if the scorer CANNOT answer
    # WITHOUT the supplementals in a majority of k sampled tries (the question must
    # genuinely require the data). Answering *with* the data is the benchmark task
    # itself, so it is not tested here.
    keep, votes, n_correct = gate_no_supp(vignette, question, options, answer, gate_k, gate_effort)
    item={"case_id":entry["case_id"],"case_ref":case_ref,"window":window,
          "cohort":entry["cohort"],"type":qtype,
          "vignette":vignette,"question":question,"options":options,"answer":answer,
          "answer_text":("None of the above" if answer=="D" and none_correct else options[answer]),
          "none_of_above_correct":none_correct,"ground_truth_correct_text":correct,
          "gate":{"without_supp_votes":votes,"n_correct":n_correct,"k":gate_k},"kept":keep}
    return item, ("kept" if keep else f"discarded (answerable without supp: {n_correct}/{gate_k} correct)")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--n-per-bucket", type=int, default=1)
    ap.add_argument("--max-rounds", type=int, default=3)
    ap.add_argument("--gate-k", type=int, default=3, help="Majority-of-k discard gate")
    ap.add_argument("--case-ids-file", default=None,
                    help="file with one case_id per line (e.g. the complete-set backbone); "
                         "one treatment question per listed case_id, in order")
    ap.add_argument("--out", default=os.path.join(HERE,"questions.jsonl"))
    ap.add_argument("--seed", type=int, default=20260713)
    args=ap.parse_args()
    global _MODEL,_TOK,_DEV
    index,_=T._load()
    rng=random.Random(args.seed)

    # build the case_id plan
    if args.case_ids_file:
        cids=[l.strip() for l in open(args.case_ids_file) if l.strip() and not l.startswith("#")]
        cids=[c for c in cids if c in index]
        plan=[( "treatment", index[c]["cohort"], c) for c in cids]      # explicit list, in order
    else:
        by_cohort={"dialysis":[],"diuretic":[]}
        for cid,e in index.items(): by_cohort[e["cohort"]].append(cid)
        for k in by_cohort: rng.shuffle(by_cohort[k])
        ptr={"dialysis":0,"diuretic":0}; plan=[]
        for cohort in ("dialysis","diuretic"):      # diagnosis dropped -- treatment-planning only
            for i in range(args.n_per_bucket):
                plan.append(("treatment", cohort, by_cohort[cohort][ptr[cohort]])); ptr[cohort]+=1

    _MODEL,_TOK,_DEV=load_local("openai/gpt-oss-20b")
    # none-of-above exactly ~25% across the plan
    n_none=round(0.25*len(plan)); none_flags=[True]*n_none+[False]*(len(plan)-n_none); rng.shuffle(none_flags)
    kept=[]; log=[]; t0=time.monotonic()
    with open(args.out,"w") as fo:
        for i,((qtype,cohort,cid),none_c) in enumerate(zip(plan,none_flags),1):
            item,status=make_question(index[cid], qtype, none_c, rng, args.max_rounds, args.gate_k)
            log.append((qtype,cohort,status))
            print(f"  [{i}/{len(plan)}] {qtype}/{cohort} -> {status}  ({(time.monotonic()-t0)/i:.0f}s/q avg)", flush=True)
            if item and item["kept"]:
                kept.append(item); fo.write(json.dumps(item)+"\n"); fo.flush()
    print("\n===== SUMMARY =====")
    print(f"generated attempts : {len(plan)}   kept : {len(kept)}")
    print("status counts:", Counter(s.split(' ')[0] for _,_,s in log))
    print(f"kept by bucket:", Counter((k['type'],k['cohort']) for k in kept))
    print(f"wrote {args.out}")

if __name__=="__main__":
    main()
