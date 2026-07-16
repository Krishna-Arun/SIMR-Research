#!/usr/bin/env python3
"""
Benchmark A - answering agent (component #3).

A gpt-oss-20b multi-turn agent that, given a vignette + MC question, REQUESTS the
supplemental data it needs (each with a patient-specific causal justification),
then answers with causal justification. Emits a transcript the scorer consumes.

Tools (called as JSON actions; executed in-process via supplemental_tools, the
same logic the MCP server wraps):
  {"action":"request_supplemental","name":"<lab/med/etc>","justification":"<why THIS patient>"}
  {"action":"answer","letter":"<A|B|C|D>","justification":"<patient-specific causal reasoning>"}
(The catalog of available supplementals -- names + timestamps, NO values -- is
provided up front, i.e. the result of request_all_supplementals_no_values.)

Output transcript (one JSON per item), scored by scorer.py:
  {"item": {...}, "requests": [{"name","causal_justification"}], "final_answer": {"letter","causal_justification"}}

Usage:
  python answer_agent.py --questions /tmp/bencha_qtreat.jsonl --out transcripts.jsonl [--limit N]
"""
import argparse, json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "benchmark_b"))
from evaluate import load_local, _final_channel, _extract_json
import supplemental_tools as T

_M=_TK=_DV=None
def chat(messages, effort="low", max_new_tokens=1400):
    import torch
    kw=dict(add_generation_prompt=True, return_tensors="pt", return_dict=True)
    try: enc=_TK.apply_chat_template(messages, reasoning_effort=effort, **kw)
    except TypeError: enc=_TK.apply_chat_template(messages, **kw)
    enc={k:v.to(_DV) for k,v in enc.items()}
    with torch.no_grad():
        out=_M.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False, pad_token_id=_TK.eos_token_id)
    return _final_channel(_TK.decode(out[0][enc["input_ids"].shape[1]:], skip_special_tokens=False))

SYSTEM=(
 "You are a critical-care physician answering a multiple-choice question about a hospitalized acute "
 "heart-failure patient. You do NOT have the patient's quantitative data (labs, doses, values) -- you "
 "must REQUEST what you need. A catalog of AVAILABLE supplementals (names + timestamps, no values) is "
 "given. Each turn respond with EXACTLY ONE JSON action:\n"
 '  {"action":"request_supplemental","name":"<exact catalog name>","justification":"<why THIS patient needs it>"}\n'
 '  {"action":"answer","letter":"<A|B|C|D>","justification":"<patient-specific causal reasoning using the data you gathered>"}\n'
 "Request the specific labs/data you need, each with a justification tied to THIS patient (not generic "
 "textbook facts), then answer. Output JSON only -- no prose outside the JSON.")

def _catalog_text(case_ref):
    cat=T.request_all_supplementals_no_values(case_ref).get("catalog",{})
    labs=", ".join(l["name"] for l in cat.get("labs",[]))
    return (f"AVAILABLE SUPPLEMENTALS (names only; request values with request_supplemental):\n"
            f"  labs: {labs}\n"
            f"  other: medications, coronary_contrast, demographics, comorbidities")

def run_item(item, effort="low", max_turns=8, max_requests=8):
    case_ref=item.get("case_ref", item["case_id"])
    opts="\n".join(f"{L}. {t}" for L,t in item["options"].items())
    user=(f"VIGNETTE: {item['vignette']}\n\nQUESTION: {item['question']}\nOPTIONS:\n{opts}\n\n"
          f"{_catalog_text(case_ref)}\n\nBegin: request the supplementals you need, then answer.")
    messages=[{"role":"system","content":SYSTEM},{"role":"user","content":user}]
    requests=[]; final=None
    for turn in range(max_turns):
        try:
            act=_extract_json(chat(messages, effort))
        except Exception:
            messages.append({"role":"user","content":'Respond with ONE valid JSON action only.'})
            continue
        messages.append({"role":"assistant","content":json.dumps(act)})
        a=act.get("action")
        if a=="request_supplemental" and len(requests)<max_requests:
            name=str(act.get("name","")).strip(); just=str(act.get("justification","")).strip()
            res=T.request_a_supplemental(case_ref, name, just or "(none)")
            requests.append({"name":name,"causal_justification":just})
            messages.append({"role":"user","content":f"RESULT for '{name}':\n{json.dumps(res, default=str)[:4000]}"})
        elif a=="answer":
            final={"letter":str(act.get("letter","")).strip().upper()[:1],
                   "causal_justification":str(act.get("justification","")).strip()}
            break
        else:
            messages.append({"role":"user","content":'Either request_supplemental or answer. Output JSON only.'})
    if final is None:  # force an answer from what it gathered
        messages.append({"role":"user","content":'You must now answer. Output {"action":"answer","letter":"<A|B|C|D>","justification":"..."} only.'})
        try:
            act=_extract_json(chat(messages, effort))
            final={"letter":str(act.get("letter","")).strip().upper()[:1],
                   "causal_justification":str(act.get("justification","")).strip()}
        except Exception:
            final={"letter":"","causal_justification":"(no valid answer produced)"}
    return {"item":item,"requests":requests,"final_answer":final}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--questions", default="/tmp/bencha_qtreat.jsonl")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),"transcripts.jsonl"))
    ap.add_argument("--effort", default="low", choices=["low","medium","high"])
    ap.add_argument("--limit", type=int, default=0)
    args=ap.parse_args()
    items=[json.loads(l) for l in open(args.questions) if l.strip()]
    if args.limit: items=items[:args.limit]
    global _M,_TK,_DV
    _M,_TK,_DV=load_local("openai/gpt-oss-20b")
    t0=time.monotonic()
    with open(args.out,"w") as fo:
        for i,it in enumerate(items,1):
            tr=run_item(it, args.effort)
            fo.write(json.dumps(tr)+"\n"); fo.flush()
            fa=tr["final_answer"]
            print(f"  [{i}/{len(items)}] {it['type']}/{it['cohort']}  "
                  f"requested {len(tr['requests'])} supps -> answered {fa['letter']} "
                  f"(truth {it['answer']})  {(time.monotonic()-t0)/i:.0f}s/item", flush=True)
    print(f"wrote {args.out}")

if __name__=="__main__":
    main()
