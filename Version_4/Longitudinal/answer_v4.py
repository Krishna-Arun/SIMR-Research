#!/usr/bin/env python3
"""
Version_4 answering harness — runs a test-subject LLM over the leak-safe chained views and
produces the structured answers that score_chain.py grades.

`a` is AGENTIC (two-turn, justification-capturing):
  turn 1  the model sees the supplemental catalog by NAME + DATE only (NO values) and must
          output JSON {requests:[{item, justification}]} — deciding what evidence to gather
          and why, specific to this patient;
  turn 2  we return the requested items' VALUES (from the bundle) and the model outputs the
          final JSON {answer, causal_chain:[...], evidence:[{item,value}], confidence}.
This mirrors the gated Access_All_supplementals_no_values -> Request_* tool flow while cleanly
recording each request's justification for the agent judge.

`b`/`c`/`d` are single structured turns over the leak-safe view.

Usage:
  SIMR_BACKEND=ollama python answer_v4.py --model gemma-4-e4b --n 10
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "outputs_v4"
ANSWER_VIEWS = OUT / "answering"
BUNDLES = HERE.parent / "Benchmark_a" / "MCP_Server" / "supplementals"
sys.path.insert(0, str(HERE.parent / "Benchmark_a"))


def _json(text):
    text = (text or "").replace("▁", " ")     # gemma3n emits SentencePiece meta-space
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        # tolerate trailing junk: trim to last balanced brace
        s = m.group(0)
        depth = 0; end = None
        for i, ch in enumerate(s):
            depth += (ch == "{") - (ch == "}")
            if depth == 0:
                end = i + 1; break
        try:
            return json.loads(s[:end]) if end else {}
        except Exception:
            return {}


SYSTEM = ("You are an ICU clinical-reasoning agent working through a chained case about ONE "
          "patient. Reason internally but keep it brief. When asked for an answer you MUST reply "
          "with ONLY a single, COMPLETE, valid JSON object matching the requested schema — no "
          "analysis, no <think> blocks, no prose, no markdown/code fences, nothing before or "
          "after the JSON. Put any reasoning INSIDE the JSON's justification/rationale fields.")


def _ask(llm, msgs, user, max_new_tokens=1400):
    """Append a user turn, get a JSON reply, keep the assistant turn in history (chained)."""
    msgs.append({"role": "user", "content": user})
    raw = llm.chat(msgs, temperature=0.2, max_new_tokens=max_new_tokens)
    if not _json(raw):                                   # one strict retry if it drifted to prose
        msgs.append({"role": "assistant", "content": raw})
        msgs.append({"role": "user", "content": "Output ONLY the JSON object now, nothing else."})
        raw = llm.chat(msgs, temperature=0.0, max_new_tokens=max_new_tokens)
        msgs.pop(); msgs.pop()
    msgs.append({"role": "assistant", "content": raw})
    return _json(raw)


def chained_answer(llm, view, qid):
    """Answer a -> b -> c -> d in ONE conversation so patient context carries across steps."""
    msgs = [{"role": "system", "content": SYSTEM}]
    steps = {}
    va = view["steps"]["a"]

    # a — agentic: catalog (names only) -> request w/ justification -> values -> answer
    bundle = json.loads((BUNDLES / f"{qid}.json").read_text())
    supp = bundle.get("supplementals", {})
    catalog, seen = [], set()
    for cat, rows in supp.items():
        for r in rows:
            name = r.get("item_name") or r.get("test_name") or r.get("title")
            if name and (cat, name) not in seen:
                seen.add((cat, name)); catalog.append({"category": cat, "item": name})
    r1 = _ask(llm, msgs, va["stem"] + "\n\nAVAILABLE SUPPLEMENTAL ITEMS (names only — values "
              "hidden until you request them):\n" + json.dumps(catalog)[:6000] +
              '\n\nRequest ONLY the items you need, each with a patient-specific justification. '
              'JSON schema: {"requests":[{"item":"<name>","justification":"<why for THIS patient>"}]}',
              max_new_tokens=1400)
    requests = r1.get("requests", []) if isinstance(r1, dict) else []

    def values_for(item):
        out = []
        for cat, rows in supp.items():
            for r in rows:
                nm = r.get("item_name") or r.get("test_name") or r.get("title")
                if nm and str(item).lower() in nm.lower() and "value" in r:
                    out.append({"value": r.get("value"), "unit": r.get("unit"),
                                "ref_low": r.get("ref_low"), "ref_high": r.get("ref_high"),
                                "charttime": r.get("charttime")})
        return out[:12]
    fulfilled = {r.get("item"): values_for(r.get("item")) for r in requests[:12] if r.get("item")}
    a = _ask(llm, msgs, "RETRIEVED VALUES:\n" + json.dumps(fulfilled, default=str)[:6000] +
             '\n\nNow answer the question. JSON schema: {"answer":"<single most likely next '
             'intervention>","causal_chain":["step1","step2",...],"evidence":[{"item":"<lab>",'
             '"value":<v>}],"confidence":0-1}', max_new_tokens=1800)
    a = a if isinstance(a, dict) else {}
    a["requests"] = requests
    steps["a"] = a

    # b — trajectory (same conversation)
    b = view["steps"].get("b")
    if b:
        steps["b"] = _ask(llm, msgs, b["stem"] + "\n\nCANDIDATE LABS:\n" +
                          json.dumps(b["candidate_labs"])[:4000] +
                          '\n\nJSON schema: {"selected":[{"lab":"<name>","direction":"Rising|'
                          'Falling|Stable","justification":"<causal, patient-specific>",'
                          '"confidence":0-1}]}', max_new_tokens=1800)
    # c — attribution
    c = view["steps"].get("c")
    if c:
        steps["c"] = _ask(llm, msgs, c["stem"] + "\n\n" +
                          json.dumps({k: c[k] for k in c if k != "stem"})[:6000] +
                          '\n\nJSON schema: {"chosen":"A|B","mechanism":"<causal physiology>",'
                          '"confidence":0-1}', max_new_tokens=1400)
    # d — outcome
    d = view["steps"].get("d")
    if d:
        steps["d"] = _ask(llm, msgs, d["stem"] + "\n\nOptions: Yes / No.\n\nJSON schema: "
                          '{"call":"Yes|No","confidence":0-1,"rationale":"<causal risk reasoning>"}',
                          max_new_tokens=1400)
    return steps


def run(model_key, n, all_cases):
    from backend import LocalLLM
    llm = LocalLLM(model_key)
    views = sorted(ANSWER_VIEWS.glob("*.json"))
    if not all_cases:
        views = views[:n]
    outp = OUT / f"answers_{model_key}.jsonl"
    t0 = time.time()
    with open(outp, "w") as f:
        for i, vp in enumerate(views, 1):
            view = json.loads(vp.read_text()); qid = view["question_id"]
            try:
                steps = chained_answer(llm, view, qid)
            except Exception as e:
                steps = {"a": {"answer": "", "error": f"{type(e).__name__}: {e}"}}
            f.write(json.dumps({"question_id": qid, "model": model_key, "steps": steps}) + "\n")
            f.flush()
            print(f"[{i}/{len(views)}] {qid}: a='{str(steps.get('a',{}).get('answer'))[:40]}' "
                  f"({time.time()-t0:.0f}s)", flush=True)
    print(f"\nwrote {outp}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemma-4-e4b")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    run(args.model, args.n, args.all)
