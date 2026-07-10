"""Phase-2 evaluation — Benchmark C (counterfactual intervention identification).

Agent gets BOTH patients' pre-procedure state + procedures + ONE patient's observed post-procedure labs
(owner hidden). It picks which patient (A/B) produced the post-state + confidence. Optionally (--pubmed)
it may call search_articles. Scoring: deterministic 0/1 + ECE.

Usage: python -m eval.run_eval_c --model <id> --endpoint http://localhost:8000/v1 [--pubmed] [--n 100]
"""
from __future__ import annotations
import argparse, json, sys, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eval.llm import LLM
from eval import scorer

GEN = Path("/scratch/users/karun09/Version_2/Benchmark_C/Question_Generation/outputs")
_LOCK = threading.Lock()

SYS = """You are a careful cardiologist. Two patients (A and B) each underwent a DIFFERENT procedure. You
see both patients' PRE-procedure states and ONE patient's OBSERVED post-procedure labs (owner hidden).
Decide which patient (A or B) — i.e. which procedure — produced that post-state, using the causal effects
of each procedure on the labs that moved. Call choose once with "A" or "B" and a confidence in [0,1]."""

CHOOSE = [{"type": "function", "function": {"name": "choose",
    "description": "Submit which patient produced the shown post-state.",
    "parameters": {"type": "object", "properties": {
        "patient": {"type": "string", "enum": ["A", "B"]}, "confidence": {"type": "number"},
        "rationale": {"type": "string"}}, "required": ["patient", "confidence"]}}}]

def _labs(d):
    return ", ".join(f"{k}={v.get('latest')}" for k, v in sorted((d or {}).items())) or "(none)"

def context(rec):
    A, B = rec["patient_A"], rec["patient_B"]
    post = ", ".join(f"{k}: " + "->".join(str(p['value']) for p in v) for k, v in sorted(rec["shown_post_labs"].items())) or "(none)"
    def blk(name, p):
        return (f"PATIENT {name} — procedure: {p['procedure']}; "
                f"comorbidities: {', '.join(p.get('comorbidities',{})) or 'none'}; "
                f"prior procedures: {', '.join(p.get('prior_procedures',[])[:6]) or 'none'}\n"
                f"  pre-procedure labs: {_labs(p.get('pre_labs'))}")
    return (blk("A", A) + "\n" + blk("B", B) +
            f"\n\nOBSERVED POST-PROCEDURE LABS (from exactly ONE patient): {post}\n\n{rec.get('question_text','')}")

def run_one(llm, rec, mcp_tools=None, dispatcher=None):
    tools = CHOOSE + (mcp_tools or [])
    msgs = [{"role": "system", "content": SYS}, {"role": "user", "content": context(rec)}]
    choice = conf = None
    for _ in range(10):
        r = llm.chat(msgs, tools=tools)
        if not r.tool_calls: break
        msgs.append({"role": "assistant", "content": r.text or None, "tool_calls": [
            {"id": t.id, "type": "function", "function": {"name": t.name, "arguments": json.dumps(t.args)}} for t in r.tool_calls]})
        done = False
        for t in r.tool_calls:
            if t.name == "choose":
                choice, conf = t.args.get("patient"), t.args.get("confidence"); obs = "ok"; done = True
            elif dispatcher is not None:
                with _LOCK:
                    obs = dispatcher.dispatch(t.name, t.args, None)[:2000]
            else:
                obs = "unknown tool"
            msgs.append({"role": "tool", "tool_call_id": t.id, "content": obs})
        if done: break
    return choice, conf

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
        sys.path.insert(0, "/scratch/users/karun09/Version_2/Benchmark_C/Question_Generation")
        from qgen.config import load_config
        from qgen.mcp_client import MCPClient
        from qgen.tools import ToolDispatcher, to_openai_tools
        cfg = load_config("/scratch/users/karun09/Version_2/Benchmark_C/Question_Generation/config/qgen.yaml")
        mcp = MCPClient(cfg).start(); dispatcher = ToolDispatcher(cfg, mcp); mcp_tools = to_openai_tools(mcp.tools)
    def work(rec):
        choice, conf = run_one(agent, rec, mcp_tools, dispatcher)
        sc = scorer.score_c(rec["shown_post_owner"], choice or "")
        row = {"qid": rec["question_id"], "choice": choice, "true": rec["shown_post_owner"], "confidence": conf, **sc}
        return row, sc["correct"], ((conf, sc["correct"]) if conf is not None else None)
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        out = list(ex.map(work, rows))
    results = [o[0] for o in out]; correct = sum(o[1] for o in out); ece_pairs = [o[2] for o in out if o[2] is not None]
    summ = {"benchmark": "C", "model": a.model, "pubmed": a.pubmed, "n": len(rows),
            "accuracy": correct/len(rows) if rows else 0.0, "ece": scorer.ece(ece_pairs)}
    out = a.out or f"/scratch/users/karun09/Version_2/Eval/results_C_{a.model.split('/')[-1]}_{'pubmed' if a.pubmed else 'nopubmed'}.json"
    Path(out).write_text(json.dumps({"summary": summ, "results": results}, indent=2))
    print("SUMMARY:", json.dumps(summ)); print("wrote", out)

if __name__ == "__main__":
    main()
