"""Live generation dashboard -> writes dashboard.html every few seconds (auto-refreshing page).
Open Version_2/h100_session/dashboard.html in code-server's browser preview to watch live.
"""
import time, subprocess, json, html, re
from pathlib import Path
from datetime import datetime

V2 = Path("/scratch/users/karun09/Version_2")
H = V2 / "h100_session"
OUT = H / "dashboard.html"
TARGET = 100
Bench = {"A": "Lab-request + causal Dx/Rx", "B": "Post-procedure trajectory", "C": "Counterfactual identification"}
prev = {}      # bench -> (count, ts) for rate

def count(x):
    p = V2 / f"Benchmark_{x}/Question_Generation/outputs/questions.jsonl"
    try: return sum(1 for _ in open(p))
    except FileNotFoundError: return 0

def sh(cmd):
    try: return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=8).stdout.strip()
    except Exception: return ""

def tail_accepts(x, n=6):
    log = H / f"run_{x}.log"
    if not log.exists(): return []
    out = []
    for line in sh(f"grep -E 'ACCEPT' {log} | tail -{n}").splitlines():
        out.append(line.strip())
    return out

def running_bench():
    o = sh("pgrep -af 'qgen.run_generate' | grep -oE 'Benchmark_[ABC]' | head -1")
    m = re.search(r"Benchmark_([ABC])", o)
    return m.group(1) if m else None

while True:
    now = time.time()
    run_b = running_bench()
    gpu = sh("nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader").splitlines()
    gpu = gpu[0] if gpu else "n/a"
    server_up = bool(sh("curl -sf http://localhost:8000/v1/models >/dev/null 2>&1 && echo up"))
    summary = (H / "RUN_SUMMARY.txt").read_text() if (H / "RUN_SUMMARY.txt").exists() else ""

    cards = []
    total = 0
    for x, desc in Bench.items():
        c = count(x); total += c
        pc, pts = prev.get(x, (c, now))
        rate = (c - pc) / ((now - pts) / 60.0) if now > pts and c >= pc else 0.0
        if c != pc: prev[x] = (c, now)
        elif x not in prev: prev[x] = (c, now)
        done = bool(re.search(rf"Benchmark {x}: \d+/{TARGET} in", summary))
        status = "DONE" if done else ("RUNNING" if run_b == x else ("done?" if c >= TARGET else ("running" if c > 0 else "pending")))
        color = {"DONE": "#22c55e", "RUNNING": "#3b82f6"}.get(status, "#64748b")
        pct = min(100, int(100 * c / TARGET))
        eta = ""
        if status == "RUNNING" and rate > 0.1:
            eta = f" · ~{int((TARGET-c)/rate)} min left · {rate:.1f}/min"
        feed = "".join(f"<div class='ln'>{html.escape(l[:110])}</div>" for l in tail_accepts(x))
        cards.append(f"""
        <div class="card">
          <div class="hd"><span class="b">Benchmark {x}</span><span class="st" style="background:{color}">{status}</span></div>
          <div class="desc">{desc}</div>
          <div class="bar"><div class="fill" style="width:{pct}%;background:{color}"></div></div>
          <div class="num">{c} / {TARGET}{eta}</div>
          <div class="feed">{feed or "<div class='ln dim'>waiting…</div>"}</div>
        </div>""")

    page = f"""<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="4">
<title>Benchmark generation — live</title>
<style>
 body{{background:#0b1020;color:#e2e8f0;font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:24px}}
 h1{{font-size:20px;margin:0 0 4px}} .sub{{color:#94a3b8;margin-bottom:18px}}
 .row{{display:flex;gap:16px;flex-wrap:wrap}}
 .card{{background:#111827;border:1px solid #1f2937;border-radius:12px;padding:16px;flex:1;min-width:300px}}
 .hd{{display:flex;justify-content:space-between;align-items:center}}
 .b{{font-weight:700;font-size:16px}} .st{{font-size:11px;font-weight:700;padding:3px 8px;border-radius:999px;color:#06210f}}
 .desc{{color:#94a3b8;font-size:12px;margin:2px 0 10px}}
 .bar{{height:10px;background:#1f2937;border-radius:999px;overflow:hidden}} .fill{{height:100%;transition:width .4s}}
 .num{{margin:8px 0;font-size:15px;font-weight:600}}
 .feed{{margin-top:8px;background:#0b1020;border-radius:8px;padding:8px;max-height:160px;overflow:auto}}
 .ln{{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:#a7f3d0;white-space:nowrap}}
 .dim{{color:#475569}}
 .meta{{margin-top:18px;color:#94a3b8;font-size:12px;display:flex;gap:24px;flex-wrap:wrap}}
 .pill{{background:#111827;border:1px solid #1f2937;border-radius:8px;padding:6px 12px}}
</style></head><body>
 <h1>Benchmark Question Generation — live</h1>
 <div class="sub">gpt-oss-20b · single-shot + leak guard · target {TARGET}/benchmark · {datetime.now().strftime('%H:%M:%S')}</div>
 <div class="row">{''.join(cards)}</div>
 <div class="meta">
   <span class="pill">Total: <b>{total}/{TARGET*3}</b></span>
   <span class="pill">Server: <b style="color:{'#22c55e' if server_up else '#ef4444'}">{'UP' if server_up else 'DOWN'}</b></span>
   <span class="pill">GPU: {html.escape(gpu)}</span>
   <span class="pill">auto-refresh 4s</span>
 </div>
</body></html>"""
    OUT.write_text(page)
    time.sleep(4)
