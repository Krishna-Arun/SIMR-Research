#!/usr/bin/env python3
"""
Benchmark A - scoring agent (component #4).

Consumes an ANSWERING-AGENT TRANSCRIPT per item and grades it with gpt-oss-20b
against the two rubrics, plus deterministic MC correctness.

Scoring scheme (locked = scheme B):
  - MC accuracy         : deterministic; did the chosen letter match ground truth?
  - reasoning_composite : (request_mean + answer_score) / 2   [0..1]  (how well it reasoned)
  MC correctness and reasoning quality are reported as SEPARATE axes.

Transcript schema (one JSON object per item; produced by answering agent #3):
{
  "item": { ... a question object from questions.jsonl ... },
  "requests": [ {"name": "Creatinine", "causal_justification": "..."}, ... ],
  "final_answer": {"letter": "B", "causal_justification": "..."}
}

Rubrics (0 / 0.5 / 1):
  SUPPLEMENTAL REQUEST (per request) -- judged against the VIGNETTE + already-retrieved
  labs, because at request time the agent has NOT seen the value it is asking for:
    0   irrelevant, nonsensical, or inaccurate given the vignette
    0.5 accurate but generic/textbook, not tied to the vignette
    1   ties the item's necessity to a SPECIFIC vignette feature (or an already-retrieved value)
  ANSWER -- judged against the RETRIEVED values (the agent has them by now):
    0   nonsensical / irrelevant / inaccurate
    0.5 generic causal links; does not use the retrieved lab values
    1   patient-specific causal links citing the retrieved values (and external evidence)

Usage:
  python scorer.py --mock                 # validate rubric on a good vs lazy mock agent
  python scorer.py --transcripts t.jsonl  # score a real transcript file
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "benchmark_b"))
from evaluate import load_local, _final_channel, _extract_json
import supplemental_tools as T

_M=_TK=_DV=None
def chat(system, user, effort="low", max_new_tokens=1400):
    import torch
    msgs=[{"role":"system","content":system},{"role":"user","content":user}]
    kw=dict(add_generation_prompt=True, return_tensors="pt", return_dict=True)
    try: enc=_TK.apply_chat_template(msgs, reasoning_effort=effort, **kw)
    except TypeError: enc=_TK.apply_chat_template(msgs, **kw)
    enc={k:v.to(_DV) for k,v in enc.items()}
    with torch.no_grad():
        out=_M.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False, pad_token_id=_TK.eos_token_id)
    return _final_channel(_TK.decode(out[0][enc["input_ids"].shape[1]:], skip_special_tokens=False))

SCORER_SYS=(
 "You are an expert clinical grader for a medical-reasoning benchmark. You are given the patient's "
 "TRUE data (the correct answer and the full supplemental record), the question, and an AGENT's "
 "behavior: the supplemental data it requested (each with a justification) and its final answer with "
 "a causal justification. Grade STRICTLY and patient-specifically per the rubrics. A justification "
 "that merely recites textbook facts without tying them to THIS patient's data is 0.5, not 1. "
 "Output JSON only.")

def _rubric():
    return (
 "SCORE EACH SUPPLEMENTAL REQUEST 0/0.5/1. Judge the justification against the VIGNETTE and any data "
 "the agent already retrieved in EARLIER requests. IMPORTANT: at request time the agent has NOT yet "
 "seen the value of the item it is requesting, so do NOT require it to cite that value -- patient-"
 "specificity here means grounding in the vignette (a documented comorbidity, the presentation, prior "
 "findings) or an already-retrieved lab.\n"
 "  0   = irrelevant to the question, nonsensical, or inaccurate given the vignette\n"
 "  0.5 = accurate but generic/textbook reasoning, not tied to THIS patient's vignette\n"
 "  1   = ties the item's necessity to a SPECIFIC feature of THIS patient's vignette (or an already-"
 "retrieved value); credit reasoning that combines multiple relevant items\n"
 "SCORE THE ANSWER 0/0.5/1. By answer time the agent HAS the retrieved values, so specificity here "
 "means citing them:\n"
 "  0   = nonsensical / irrelevant / inaccurate\n"
 "  0.5 = generic causal links; does not actually use the retrieved lab values\n"
 "  1   = patient-specific causal links that cite the RETRIEVED lab values (and any external evidence) as support")

def score_item(item, requests, final_answer):
    mc_correct = str(final_answer.get("letter","")).strip().upper()[:1] == item["answer"]
    e = T._load()[0].get(item["case_id"], {})
    gt = e.get("ground_truth", {})
    sup = T._sliced(e, item.get("window","pretreatment")) if e else {}
    reqs = "\n".join(f'  - {r["name"]}: "{r.get("causal_justification","")}"' for r in requests) or "  (none)"
    prompt=(f"VIGNETTE (the ONLY patient information the agent had when it made its requests):\n"
            f"{item.get('vignette','(none)')}\n\n"
            f"QUESTION: {item['question']}\nOPTIONS: "
            + "; ".join(f"{L}={t}" for L,t in item["options"].items())
            + f"\nCORRECT ANSWER: {item['answer']} = {item.get('answer_text','')}\n"
            f"TRUE INTERVENTION (ground truth): {gt.get('intervention',{}).get('type','?')}\n\n"
            f"PATIENT SUPPLEMENTAL DATA (truth, for judging accuracy/specificity):\n{json.dumps(sup, default=str)[:6000]}\n\n"
            f"AGENT SUPPLEMENTAL REQUESTS (name: justification):\n{reqs}\n\n"
            f"AGENT FINAL ANSWER: {final_answer.get('letter')} -- justification: \"{final_answer.get('causal_justification','')}\"\n\n"
            f"{_rubric()}\n\n"
            'Output ONLY JSON: {"request_scores":[{"name":"<name>","score":<0|0.5|1>,"reason":"<short>"}],'
            '"answer_score":<0|0.5|1>,"answer_reason":"<short>"}')
    try:
        obj=_extract_json(chat(SCORER_SYS, prompt))
        rs=[{"name":x.get("name"),"score":float(x.get("score")),"reason":x.get("reason","")}
            for x in obj.get("request_scores",[]) if float(x.get("score",-1)) in (0,0.5,1)]
        ans=float(obj.get("answer_score"))
        if ans not in (0,0.5,1): ans=None
    except Exception as ex:
        return {"error":str(ex),"mc_correct":mc_correct}
    req_mean = round(sum(r["score"] for r in rs)/len(rs),3) if rs else None
    composite = round((req_mean+ans)/2,3) if (req_mean is not None and ans is not None) else None
    return {"mc_correct":mc_correct,"n_requests":len(requests),
            "request_scores":rs,"request_mean":req_mean,
            "answer_score":ans,"answer_reason":obj.get("answer_reason",""),
            "reasoning_composite":composite}

def build_mock(item):
    good={"requests":[
            {"name":"Creatinine","causal_justification":"This patient developed AKI during a cardiogenic-shock HF admission; the creatinine trend tells me whether renal failure is progressing toward needing renal replacement despite diuretics."},
            {"name":"Potassium","causal_justification":"Refractory hyperkalemia in this AKI+shock patient would be a hard indication for urgent dialysis rather than continued diuresis."},
            {"name":"Bicarbonate","causal_justification":"Worsening metabolic acidosis here would indicate the kidneys cannot clear the acid load, pushing toward RRT."}],
          "final_answer":{"letter":item["answer"],"causal_justification":"Given this patient's AKI with rising creatinine, hyperkalemia, and acidosis not responding to IV diuretics in cardiogenic shock, solute/fluid removal requires renal replacement therapy rather than more diuretic."}}
    lazy={"requests":[
            {"name":"Hemoglobin","causal_justification":"Hemoglobin is generally important in heart failure patients."}],
          "final_answer":{"letter":item["answer"],"causal_justification":"Dialysis is a treatment used in heart failure, so that is the answer."}}
    return good, lazy

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--transcripts")
    ap.add_argument("--questions", default="/tmp/bencha_qtreat.jsonl")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),"scores.json"))
    args=ap.parse_args()
    global _M,_TK,_DV
    _M,_TK,_DV=load_local("openai/gpt-oss-20b")

    if args.mock:
        item=json.loads(open(args.questions).readline())
        for label,tr in [("GOOD agent",),("LAZY agent",)] and [("GOOD agent",build_mock(item)[0]),("LAZY agent",build_mock(item)[1])]:
            r=score_item(item,tr["requests"],tr["final_answer"])
            print(f"\n===== {label} =====")
            print(f"  MC correct: {r.get('mc_correct')}")
            for x in r.get("request_scores",[]): print(f"  request {x['name']}: {x['score']}  ({x['reason']})")
            print(f"  request_mean: {r.get('request_mean')}   answer_score: {r.get('answer_score')}  ({r.get('answer_reason')})")
            print(f"  >> reasoning_composite: {r.get('reasoning_composite')}")
        return

    rows=[json.loads(l) for l in open(args.transcripts)]
    out=[{"case_id":t["item"]["case_id"], **score_item(t["item"], t.get("requests",[]), t.get("final_answer",{}))} for t in rows]
    import statistics as st
    ok=[r for r in out if "error" not in r]
    acc=sum(1 for r in ok if r["mc_correct"])/len(ok) if ok else 0
    comp=[r["reasoning_composite"] for r in ok if r.get("reasoning_composite") is not None]
    rq=[r["request_mean"] for r in ok if r.get("request_mean") is not None]
    an=[r["answer_score"] for r in ok if r.get("answer_score") is not None]
    print(f"\nscored {len(ok)}/{len(out)} items")
    print(f"  MC accuracy            : {acc:.2f}")
    print(f"  mean reasoning composite: {st.mean(comp):.2f}" if comp else "  mean reasoning composite: n/a")
    print(f"    (mean request={st.mean(rq):.2f}, mean answer={st.mean(an):.2f})" if rq and an else "")
    json.dump(out, open(args.out,"w"), indent=1)
    print(f"  wrote {args.out}")

if __name__=="__main__":
    main()
