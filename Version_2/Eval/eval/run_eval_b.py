"""Phase-2 evaluation — Benchmark B (post-procedure trajectory prediction).

Agent gets: procedure + pre-procedure state + the list of target labs (with baseline, NO post/true value).
It predicts each lab's direction (Rising/Falling/Stable) + confidence. Optionally (--pubmed) it may call
search_articles. Scoring is deterministic vs the data-derived true_direction (1 / 0.5 / 0) + ECE.

Usage: python -m eval.run_eval_b --model <id> --endpoint http://localhost:8000/v1 [--pubmed] [--n 100]
"""
from __future__ import annotations
import argparse, json, sys, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eval.llm import LLM
from eval import scorer

GEN = Path("/scratch/users/karun09/Version_2/Benchmark_B/Question_Generation/outputs")
_LOCK = threading.Lock()

SYS = """You are a careful cardiologist. Given a patient's PRE-procedure state and the procedure performed,
predict how EACH listed core lab will move AFTERWARD: Rising, Falling, or Stable (Stable = stays within the
lab's reference range). Give patient-specific causal reasoning. Call predict exactly once with a direction
and a confidence in [0,1] for every listed lab."""

def predict_tool(labs):
    return [{"type": "function", "function": {"name": "predict",
        "description": "Submit a direction + confidence for every target lab.",
        "parameters": {"type": "object", "properties": {"predictions": {"type": "array", "items": {
            "type": "object", "properties": {
                "label": {"type": "string", "enum": labs},
                "direction": {"type": "string", "enum": ["Rising", "Falling", "Stable"]},
                "confidence": {"type": "number"}},
            "required": ["label", "direction", "confidence"]}}}, "required": ["predictions"]}}}]

def context(rec):
    tl = rec.get("target_labs_detail", [])
    labs = [t["label"] for t in tl]
    pre = "\n".join(f"  - {t['label']}: baseline {t.get('baseline')} {t.get('unit','')} "
                    f"(ref {t.get('ref_lower')}–{t.get('ref_upper')})" for t in tl)
    proc = (rec.get("procedure") or {}); proc = proc.get("label", proc) if isinstance(proc, dict) else proc
    demo = rec.get("demographics", {})
    txt = (f"PROCEDURE (time-zero): {proc}\n"
           f"PATIENT: {demo.get('anchor_age','?')}{demo.get('gender','?')}; "
           f"comorbidities: {', '.join(rec.get('comorbidities',{})) or 'none'}; "
           f"prior procedures: {', '.join(rec.get('prior_procedures',[])[:6]) or 'none'}\n"
           f"TARGET LABS (predict each; baselines given, post-procedure values hidden):\n{pre}\n\n"
           f"{rec.get('question_text','')}")
    return txt, labs

def run_one(llm, rec, mcp_tools=None, dispatcher=None):
    txt, labs = context(rec)
    tools = predict_tool(labs) + (mcp_tools or [])
    msgs = [{"role": "system", "content": SYS}, {"role": "user", "content": txt}]
    preds = {}
    for _ in range(10):
        r = llm.chat(msgs, tools=tools)
        if not r.tool_calls: break
        msgs.append({"role": "assistant", "content": r.text or None, "tool_calls": [
            {"id": t.id, "type": "function", "function": {"name": t.name, "arguments": json.dumps(t.args)}} for t in r.tool_calls]})
        done = False
        for t in r.tool_calls:
            if t.name == "predict":
                for p in t.args.get("predictions", []):
                    preds[p.get("label")] = (p.get("direction"), p.get("confidence"))
                obs = "ok"; done = True
            elif dispatcher is not None:
                with _LOCK:
                    obs = dispatcher.dispatch(t.name, t.args, None)[:2000]
            else:
                obs = "unknown tool"
            msgs.append({"role": "tool", "tool_call_id": t.id, "content": obs})
        if done: break
    return preds

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True); ap.add_argument("--endpoint", default="http://localhost:8000/v1")
    ap.add_argument("--pubmed", action="store_true"); ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--out", default=None); ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(GEN / "questions.jsonl")][: a.n]
    agent = LLM(a.model, a.endpoint)
    mcp_tools = dispatcher = None
    if a.pubmed:
        sys.path.insert(0, "/scratch/users/karun09/Version_2/Benchmark_B/Question_Generation")
        from qgen.config import load_config
        from qgen.mcp_client import MCPClient
        from qgen.tools import ToolDispatcher, to_openai_tools
        cfg = load_config("/scratch/users/karun09/Version_2/Benchmark_B/Question_Generation/config/qgen.yaml")
        mcp = MCPClient(cfg).start(); dispatcher = ToolDispatcher(cfg, mcp); mcp_tools = to_openai_tools(mcp.tools)
    def work(rec):
        preds = run_one(agent, rec, mcp_tools, dispatcher)
        true = {t["label"]: t["true_direction"] for t in rec.get("target_labs_detail", [])}
        sc = scorer.score_b(true, {k: v[0] for k, v in preds.items()})
        ece = [(preds[lab][1], 1 if str(preds[lab][0]).capitalize() == str(trued).capitalize() else 0)
               for lab, trued in true.items() if lab in preds and preds[lab][1] is not None]
        return {"qid": rec["question_id"], "preds": {k: list(v) for k, v in preds.items()}, **sc}, sc["mean"], ece
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        out = list(ex.map(work, rows))
    results = [o[0] for o in out]; scores = [o[1] for o in out]; ece_pairs = [p for o in out for p in o[2]]
    summ = {"benchmark": "B", "model": a.model, "pubmed": a.pubmed, "n": len(rows),
            "mean_direction_score": sum(scores)/len(scores) if scores else 0.0,
            "ece": scorer.ece(ece_pairs)}
    out = a.out or f"/scratch/users/karun09/Version_2/Eval/results_B_{a.model.split('/')[-1]}_{'pubmed' if a.pubmed else 'nopubmed'}.json"
    Path(out).write_text(json.dumps({"summary": summ, "results": results}, indent=2))
    print("SUMMARY:", json.dumps(summ)); print("wrote", out)

if __name__ == "__main__":
    main()
