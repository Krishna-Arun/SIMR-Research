"""Phase-2 evaluation — Benchmark A (lab-request + causal answer).

For each question the agent-under-test gets the leak-free stem + two tools:
  request_all_labs_no_values()  -> the patient's available lab names + dates (pre-time-zero), NO values
  request_a_lab(name, justification) -> all pre-time-zero values for that lab
Optionally (--pubmed) it also gets search_articles (PubMed MCP). It then answers.
The ruthless-mentor judge (gpt-oss) scores lab-request 0/0.5/1 and answer 0/0.5/1.

Usage:
  python -m eval.run_eval_a --model <id> --endpoint http://localhost:8000/v1 [--pubmed] [--n 100]
"""
from __future__ import annotations
import argparse, json, sys, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eval.llm import LLM
from eval import scorer

GEN = Path("/scratch/users/karun09/Version_2/Benchmark_A/Question_Generation/outputs")
_LOCK = threading.Lock()   # serialize PubMed MCP (stdio not thread-safe); LLM calls stay concurrent


class Chart:
    """Per-patient pre-time-zero labs from the generation slices (serves the agent's data tools)."""
    def __init__(self):
        d = pd.read_parquet(GEN / "eligible_labs.parquet")
        d["charttime"] = pd.to_datetime(d["charttime"], errors="coerce")
        self.by = {h: g for h, g in d.groupby("hadm_id")}

    def _pre(self, hadm, anchor):
        g = self.by.get(int(hadm))
        if g is None: return g
        return g[g["charttime"] <= pd.to_datetime(anchor)]

    def list_labs(self, hadm, anchor):
        g = self._pre(hadm, anchor)
        if g is None or not len(g): return []
        out = []
        for lbl, gg in g.groupby("label"):
            dates = sorted({str(t.date()) for t in gg["charttime"] if pd.notna(t)})
            out.append({"lab": str(lbl), "n": int(len(gg)), "dates": dates[:8]})
        return out

    def get_lab(self, hadm, anchor, name):
        g = self._pre(hadm, anchor)
        if g is None or not len(g): return []
        gg = g[g["label"].astype(str).str.lower() == str(name).strip().lower()].sort_values("charttime")
        return [{"value": (None if pd.isna(v) else float(v)), "unit": str(u) if pd.notna(u) else "",
                 "time": str(t)} for v, u, t in zip(gg["valuenum"], gg["valueuom"], gg["charttime"])]


TOOLS = [
    {"type": "function", "function": {"name": "request_all_labs_no_values",
        "description": "List all lab/microbiology types available for this patient (names + dates, NO values).",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "request_a_lab",
        "description": "Get all values for ONE lab (after listing). Provide the lab name and a patient-specific justification.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"}, "justification": {"type": "string"}},
            "required": ["name", "justification"]}}},
    {"type": "function", "function": {"name": "answer",
        "description": "Submit the final answer.",
        "parameters": {"type": "object", "properties": {
            "answer": {"type": "string"}, "confidence": {"type": "number", "description": "0..1"}},
            "required": ["answer", "confidence"]}}},
]

SYS = """You are a careful cardiologist taking a benchmark. You are given a clinical question about ONE
patient but NO lab values up front. Use request_all_labs_no_values once to see what's available, then
request_a_lab for each lab you need (with a patient-specific justification). When ready, call answer with
your diagnosis/intervention (with patient-specific causal reasoning) and a confidence in [0,1]."""


def run_one(llm, chart, rec, use_pubmed, mcp_tools=None, dispatcher=None):
    hadm, anchor = rec["hadm_id"], rec["time_zero"]
    tools = list(TOOLS) + (mcp_tools or [])
    msgs = [{"role": "system", "content": SYS}, {"role": "user", "content": rec["question_text"]}]
    requested, answer, conf = [], None, None
    for _ in range(12):
        r = llm.chat(msgs, tools=tools)
        if not r.tool_calls:
            answer = answer or r.text; break
        msgs.append({"role": "assistant", "content": r.text or None,
                     "tool_calls": [{"id": t.id, "type": "function",
                                     "function": {"name": t.name, "arguments": json.dumps(t.args)}} for t in r.tool_calls]})
        for t in r.tool_calls:
            if t.name == "request_all_labs_no_values":
                obs = json.dumps(chart.list_labs(hadm, anchor))[:4000]
            elif t.name == "request_a_lab":
                requested.append(t.args.get("name", ""))
                obs = json.dumps(chart.get_lab(hadm, anchor, t.args.get("name", "")))[:2000]
            elif t.name == "answer":
                answer, conf = t.args.get("answer"), t.args.get("confidence")
                obs = "ok"
            elif dispatcher is not None:
                with _LOCK:
                    obs = dispatcher.dispatch(t.name, t.args, None)[:2000]
            else:
                obs = "unknown tool"
            msgs.append({"role": "tool", "tool_call_id": t.id, "content": obs})
        if answer is not None: break
    return {"requested": requested, "answer": answer or "", "confidence": conf}


def _qid_index():
    return {json.loads(l)["question_id"]: json.loads(l) for l in open(GEN / "questions.jsonl")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None)
    ap.add_argument("--endpoint", default="http://localhost:8000/v1")
    ap.add_argument("--judge-model", default="gpt-oss:20b")
    ap.add_argument("--judge-endpoint", default="http://localhost:8000/v1")
    ap.add_argument("--pubmed", action="store_true")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-judge", action="store_true", help="phase 1: collect agent answers only")
    ap.add_argument("--judge-file", default=None, help="phase 2: judge an existing results file")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()

    # ── phase 2: judge a collected file (GPU exclusive-mode: judge runs after agent model is freed) ──
    if a.judge_file:
        by = _qid_index()
        judge = LLM(a.judge_model, a.judge_endpoint, temperature=0.0)
        blob = json.loads(Path(a.judge_file).read_text())
        def jud(r):
            rec = by.get(r["qid"])
            if rec is None:
                return r
            r.update(scorer.judge_a(judge, rec["question_text"], rec, r.get("requested", []), r.get("answer", "")))
            return r
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            blob["results"] = list(ex.map(jud, blob["results"]))
        lab_s = [float(r.get("lab_request_score", 0)) for r in blob["results"]]
        ans_s = [float(r.get("answer_score", 0)) for r in blob["results"]]
        blob["summary"]["mean_lab_request"] = sum(lab_s) / len(lab_s) if lab_s else 0.0
        blob["summary"]["mean_answer"] = sum(ans_s) / len(ans_s) if ans_s else 0.0
        Path(a.judge_file).write_text(json.dumps(blob, indent=2))
        print("SUMMARY:", json.dumps(blob["summary"])); print("judged", a.judge_file); return

    # ── phase 1: run the agent-under-test, collect responses ──
    rows = [json.loads(l) for l in open(GEN / "questions.jsonl")][: a.n]
    agent = LLM(a.model, a.endpoint)
    judge = None if a.no_judge else LLM(a.judge_model, a.judge_endpoint, temperature=0.0)
    mcp_tools = dispatcher = None
    if a.pubmed:
        sys.path.insert(0, "/scratch/users/karun09/Version_2/Benchmark_A/Question_Generation")
        from qgen.config import load_config
        from qgen.mcp_client import MCPClient
        from qgen.tools import ToolDispatcher, to_openai_tools
        cfg = load_config("/scratch/users/karun09/Version_2/Benchmark_A/Question_Generation/config/qgen.yaml")
        mcp = MCPClient(cfg).start(); dispatcher = ToolDispatcher(cfg, mcp); mcp_tools = to_openai_tools(mcp.tools)

    chart = Chart()
    done = [0]
    def work(rec):
        resp = run_one(agent, chart, rec, a.pubmed, mcp_tools, dispatcher)
        row = {"qid": rec["question_id"], **resp}
        if judge is not None:
            sc = scorer.judge_a(judge, rec["question_text"], rec, resp["requested"], resp["answer"]); row.update(sc)
        with _LOCK:
            done[0] += 1
            if done[0] % 10 == 0: print(f"  {done[0]}/{len(rows)}", flush=True)
        return row
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        results = list(ex.map(work, rows))
    summ = {"benchmark": "A", "model": a.model, "pubmed": a.pubmed, "n": len(rows)}
    if judge is not None:
        lab_s = [float(r.get("lab_request_score", 0)) for r in results]; ans_s = [float(r.get("answer_score", 0)) for r in results]
        summ["mean_lab_request"] = sum(lab_s)/len(lab_s) if lab_s else 0.0
        summ["mean_answer"] = sum(ans_s)/len(ans_s) if ans_s else 0.0
    out = a.out or f"/scratch/users/karun09/Version_2/Eval/results_A_{a.model.split('/')[-1]}_{'pubmed' if a.pubmed else 'nopubmed'}.json"
    Path(out).write_text(json.dumps({"summary": summ, "results": results}, indent=2))
    print("SUMMARY:", json.dumps(summ)); print("wrote", out)


if __name__ == "__main__":
    main()
