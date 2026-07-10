#!/usr/bin/env python3
"""Live generation dashboard for Benchmark A/B/C question generation.

Stdlib only. Reads each benchmark's newest *.log + questions.jsonl on every page
load and renders an auto-refreshing status page. Nothing is cached — what you see
is the real on-disk state of the running generators.

Run:  python3 Version_2/dashboard.py   then open http://localhost:8765
"""
from __future__ import annotations

import glob
import html
import json
import os
import re
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
BENCHES = {
    "A": ("Benchmark_A/Question_Generation", "diagnosis / intervention (request labs+micro)"),
    "B": ("Benchmark_B/Question_Generation", "post-procedure lab trajectory (Rising/Falling/Stable)"),
    "C": ("Benchmark_C/Question_Generation", "counterfactual: which patient got the intervention"),
}
PORT = 8765

_re_target = re.compile(r"generating up to (\d+)")
_re_resume = re.compile(r"resume from (\d+)")
_re_draft = re.compile(r"draft (\d+)s")
_re_refine = re.compile(r"refine (\d+)s")
_re_eval = re.compile(r"eval#(\d+) (\d+)s accept=(True|False)")
_re_accept = re.compile(r"ACCEPT (\S+).*?\[(\d+)/(\d+)\]")
_re_prog = re.compile(r"\[(\d+)/(\d+)\]\s*$")


def _runs_active() -> bool:
    try:
        out = subprocess.run(["pgrep", "-f", "qgen.run_generate"], capture_output=True, text=True)
        return bool(out.stdout.strip())
    except Exception:
        return False


def newest_log(outdir: str) -> str | None:
    logs = glob.glob(os.path.join(outdir, "*.log"))
    gen_logs = [l for l in logs if _has(l, "generating up to") or _has(l, "[4] generating")]
    pool = gen_logs or logs
    return max(pool, key=os.path.getmtime) if pool else None


def _has(path: str, needle: str) -> bool:
    try:
        with open(path, errors="ignore") as fh:
            return needle in fh.read()
    except Exception:
        return False


def parse_log(path: str) -> dict:
    d = {"target": None, "resume": 0, "drafts": [], "evals": [], "refines": [],
         "accepts": 0, "rejects": 0, "written_log": 0, "lines": [], "last_mtime": 0,
         "startup": [], "in_generation": False}
    try:
        with open(path, errors="ignore") as fh:
            lines = fh.read().splitlines()
        d["last_mtime"] = os.path.getmtime(path)
    except Exception:
        return d
    d["lines"] = lines[-18:]
    for ln in lines:
        if (m := _re_target.search(ln)):
            d["target"] = int(m.group(1)); d["in_generation"] = True
        if (m := _re_resume.search(ln)):
            d["resume"] = int(m.group(1))
        if (m := _re_draft.search(ln)):
            d["drafts"].append(int(m.group(1)))
        if (m := _re_refine.search(ln)):
            d["refines"].append(int(m.group(1)))
        if (m := _re_eval.search(ln)):
            d["evals"].append(int(m.group(2)))
        if (m := _re_accept.search(ln)):
            d["accepts"] += 1; d["written_log"] = int(m.group(2))
        elif ln.strip().startswith("reject"):
            d["rejects"] += 1
        if ln.startswith("["):
            d["startup"].append(ln)
    return d


def read_questions(outdir: str) -> list[dict]:
    p = os.path.join(outdir, "questions.jsonl")
    out = []
    try:
        with open(p, errors="ignore") as fh:
            for ln in fh:
                ln = ln.strip()
                if ln:
                    out.append(json.loads(ln))
    except Exception:
        pass
    return out


def _avg(xs):
    return f"{sum(xs)/len(xs):.0f}s" if xs else "–"


def stem_of(q: dict) -> str:
    return q.get("question_text") or q.get("stem") or "(no stem)"


def gold_of(q: dict) -> str:
    # A: gold_labs with patient values + verified-citation tick
    gl = q.get("gold_labs") or []
    if gl:
        return ", ".join(f"{g.get('label')}={g.get('patient_value','?')}"
                         f"{'✓' if (g.get('guideline_citation') or {}).get('verified') else ''}" for g in gl[:6])
    # B: target_labs_detail (record key) or per_lab (candidate key) — label:direction
    det = q.get("target_labs_detail") or q.get("per_lab") or []
    if det:
        return ", ".join(f"{d.get('label')}:{d.get('true_direction') or d.get('expected_direction')}"
                         f"{'✓' if (d.get('guideline_citation') or {}).get('pmid') else ''}" for d in det[:6])
    # C: which patient is the answer + the contrasted procedures
    if q.get("predicted_owner"):
        proc = q.get("procA") and q.get("procB") and f" ({q.get('procA')} vs {q.get('procB')})" or ""
        return f"answer = patient {q.get('predicted_owner')}{proc}"
    return "–"


def card(bid: str) -> str:
    rel, desc = BENCHES[bid]
    outdir = os.path.join(ROOT, rel, "outputs")
    log = newest_log(outdir)
    qs = read_questions(outdir)
    d = parse_log(log) if log else {}
    target = d.get("target")
    written = len(qs)
    accepts = d.get("accepts", 0)
    rejects = d.get("rejects", 0)
    attempts = accepts + rejects
    acc_rate = f"{100*accepts/attempts:.0f}%" if attempts else "–"
    pct = int(100 * written / target) if target else 0
    age = (time.time() - d["last_mtime"]) if d.get("last_mtime") else None
    fresh = age is not None and age < 25
    dot = "#39d353" if fresh else ("#d29922" if age and age < 180 else "#6e7681")
    status = "GENERATING" if fresh else ("idle" if written or attempts else "not started")

    loglines = "\n".join(html.escape(l) for l in d.get("lines", [])) or "(no log yet)"
    last = d["lines"][-1].strip() if d.get("lines") else "—"

    qrows = ""
    for q in qs[-6:][::-1]:
        s = stem_of(q)
        s = s if len(s) <= 320 else s[:320] + "…"
        qrows += (f"<div class=q><div class=qid>{html.escape(str(q.get('question_id','?')))} "
                  f"<span class=qt>{html.escape(str(q.get('type','')))}</span></div>"
                  f"<div class=qs>{html.escape(s)}</div>"
                  f"<div class=gl>{html.escape(gold_of(q))}</div></div>")
    if not qrows:
        qrows = "<div class=empty>no accepted questions yet</div>"

    bar = (f"<div class=barwrap><div class=bar style='width:{pct}%'></div>"
           f"<span class=barlbl>{written}/{target or '?'} accepted ({pct}%)</span></div>")

    return f"""
    <div class=card>
      <div class=hd><span class=dot style='background:{dot}'></span>
        <b>Benchmark {bid}</b><span class=status>{status}</span></div>
      <div class=desc>{html.escape(desc)}</div>
      {bar}
      <div class=stats>
        <div><span>{written}</span>written</div>
        <div><span>{accepts}</span>accepts</div>
        <div><span>{rejects}</span>rejects</div>
        <div><span>{acc_rate}</span>accept rate</div>
        <div><span>{_avg(d.get('drafts',[]))}</span>avg draft</div>
        <div><span>{_avg(d.get('evals',[]))}</span>avg eval</div>
      </div>
      <div class=now>▸ {html.escape(last)}{f" &nbsp;<i>({age:.0f}s ago)</i>" if age is not None else ""}</div>
      <div class=sec>recent questions</div>
      {qrows}
      <div class=sec>live log</div>
      <pre class=log>{loglines}</pre>
    </div>"""


def page() -> str:
    active = _runs_active()
    banner = ("<span class=on>● a generator process is RUNNING</span>" if active
              else "<span class=off>○ no generator process running (showing last state)</span>")
    cards = "".join(card(b) for b in ("A", "B", "C"))
    now = time.strftime("%H:%M:%S")
    return f"""<!doctype html><html><head><meta charset=utf-8>
<meta http-equiv=refresh content=3>
<title>SIMR Gen Dashboard</title>
<style>
 body{{background:#0d1117;color:#c9d1d9;font:13px/1.5 -apple-system,Segoe UI,Helvetica,Arial;margin:0;padding:18px}}
 h1{{font-size:17px;margin:0 0 2px}} .top{{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:14px}}
 .on{{color:#39d353;font-weight:600}} .off{{color:#8b949e}}
 .clock{{color:#6e7681}}
 .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:14px}}
 .card{{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:14px}}
 .hd{{display:flex;align-items:center;gap:8px;font-size:15px}}
 .dot{{width:10px;height:10px;border-radius:50%;display:inline-block}}
 .status{{margin-left:auto;font-size:11px;color:#8b949e;text-transform:uppercase;letter-spacing:.5px}}
 .desc{{color:#8b949e;font-size:11px;margin:4px 0 10px}}
 .barwrap{{position:relative;background:#21262d;border-radius:6px;height:20px;overflow:hidden;margin-bottom:10px}}
 .bar{{background:linear-gradient(90deg,#1f6feb,#39d353);height:100%}}
 .barlbl{{position:absolute;left:8px;top:1px;font-size:11px;color:#fff;text-shadow:0 0 3px #000}}
 .stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-bottom:10px}}
 .stats div{{background:#0d1117;border:1px solid #21262d;border-radius:6px;padding:5px 7px;font-size:10px;color:#8b949e}}
 .stats span{{display:block;font-size:16px;color:#c9d1d9;font-weight:600}}
 .now{{background:#0d1117;border-left:3px solid #1f6feb;padding:5px 8px;font-size:11px;border-radius:0 6px 6px 0;margin-bottom:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
 .now i{{color:#6e7681}}
 .sec{{font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:#6e7681;margin:8px 0 4px}}
 .q{{background:#0d1117;border:1px solid #21262d;border-radius:6px;padding:6px 8px;margin-bottom:5px}}
 .qid{{font-size:11px;color:#58a6ff;font-weight:600}} .qt{{color:#8b949e;font-weight:400}}
 .qs{{font-size:12px;margin:2px 0}} .gl{{font-size:10px;color:#3fb950}}
 .empty{{color:#6e7681;font-size:11px;font-style:italic}}
 pre.log{{background:#010409;border:1px solid #21262d;border-radius:6px;padding:8px;font-size:10px;
   max-height:200px;overflow:auto;white-space:pre-wrap;color:#8b949e;margin:0}}
</style></head><body>
<div class=top><div><h1>SIMR — Question Generation (live)</h1>{banner}</div>
<div class=clock>refreshing every 3s · {now}</div></div>
<div class=grid>{cards}</div>
</body></html>"""


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/index.html"):
            self.send_response(404); self.end_headers(); return
        body = page().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"SIMR dashboard → http://localhost:{PORT}  (Ctrl-C to stop)")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
