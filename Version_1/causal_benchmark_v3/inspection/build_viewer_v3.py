"""build_viewer_v3.py — local self-contained HTML viewer for golden_v3.json.
Shows, per pair/marker/model, the predicted benefit, the parsed vs logit-argmax direction,
and a PROBABILITY BAR over {rising,falling,stable} (the activation-function probabilities).
Local only (MIMIC DUA — not uploaded)."""
import json, html
from pathlib import Path
V3 = Path("/scratch/users/karun09/causal_benchmark_v3/inspection")
d = json.loads((V3/"golden_v3.json").read_text())

def bar(probs):
    if not probs: return '<span class="muted">no logit probs (non-primary marker)</span>'
    seg = lambda k,c: f'<span class="seg {c}" style="width:{probs[k]*100:.0f}%" title="{k} {probs[k]:.2f}">{k[0].upper()} {probs[k]:.2f}</span>'
    return f'<div class="bar">{seg("rising","r")}{seg("falling","f")}{seg("stable","s")}</div>'

def flagchips(mm):
    c=""
    if mm["benefit_correct"] is True: c+='<span class="chip ok">benefit ✓</span>'
    elif mm["benefit_correct"] is False: c+='<span class="chip bad">benefit ✗</span>'
    if mm["parse_ne_logit"]: c+='<span class="chip warn">answer≠logit</span>'
    if mm["scale_off"]: c+='<span class="chip warn">scale-off</span>'
    if mm["garbage"]: c+='<span class="chip bad">garbage 0/0</span>'
    return c

secs=[]
for g in d["samples"]:
    blocks=[]
    for m,md in g["per_marker"].items():
        gt=md["gt"]
        rows=[]
        for name,mm in md["models"].items():
            A=mm["A"]
            if not A:
                rows.append(f'<tr><td>{html.escape(name)}</td><td colspan="3" class="muted">missing</td></tr>'); continue
            rows.append(
                f'<tr><td>{html.escape(name)}</td>'
                f'<td><b>{(mm["pred_benefit"] or "?")}</b><br><span class="muted">A {A["start"]}→{A["final"]} · B {mm["B"]["final"] if mm["B"] else "?"}</span></td>'
                f'<td>answer:<b>{A["parsed_dir"]}</b><br>logit-argmax:<b>{A["logit_argmax"]}</b><br>{bar(A["logit_probs"])}</td>'
                f'<td>{flagchips(mm)}</td></tr>')
        gtlab=(gt["benefit_label"] or "?").upper()
        blocks.append(
            f'<div class="marker"><div class="mname">{html.escape(m)} '
            f'<span class="role">{md["role"]}</span></div>'
            f'<div class="gt">GROUND TRUTH benefit: <b class="bl-{gt["benefit_label"]}">{gtlab}</b> '
            f'(DiD={gt["did"]}) &nbsp; A {gt["baseline_a"]}→{gt["final_a"]} &nbsp; B {gt["baseline_b"]}→{gt["final_b"]}</div>'
            f'<table><tr><th>model</th><th>predicted benefit</th><th>answer vs logit belief</th><th>flags</th></tr>{"".join(rows)}</table></div>')
    secs.append(f'<section><h2>{g["pair_id"]} <span class="tag">{html.escape(g["tag"])}</span> '
                f'<span class="sub">{g["arm_a"]} vs {g["arm_b"]} · match={g["match_quality"]["score"]}</span></h2>{"".join(blocks)}</section>')

intro="""<div class="flaws"><h2>What the probability recording exposes</h2><ol>
<li><b>The emitted answer contradicts the model's own logit belief.</b> Models <i>write</i> "falling"
while their activation-function probability mass sits on "rising" (e.g. P[rising]=0.55–0.78). The
generated trajectory and the logit probe measure different beliefs — so v3 reads the answer and its
probability from ONE mechanism.</li>
<li><b>96h injury-marker "benefit" is inverted by periprocedural injury.</b> Big-infarct PCI cases are
labelled HURTS because troponin rises from the procedure, though PCI is correct. Troponin@96h cannot
measure treatment usefulness — v3 uses a resolution-at-longer-horizon outcome.</li>
<li><b>Negative control gets a benefit label from noise.</b> Sodium ±6 mEq/L trips the DiD threshold and
is mislabelled HELPS/HURTS. v3 fixes the negative control's truth to ALWAYS no-different.</li>
<li><b>Garbage (0/0) and scale-off outputs</b> still appear (DeepSeek). v3 gates them as abstentions.</li>
</ol></div>"""

css="""body{font:14px/1.5 system-ui,sans-serif;margin:0;background:#0d1117;color:#e6edf3}
.wrap{max-width:1150px;margin:0 auto;padding:24px}h1{font-size:22px}h2{font-size:16px}
section{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:16px;margin:14px 0}
.tag{font-size:11px;background:#1f6feb33;color:#79c0ff;padding:2px 8px;border-radius:10px}
.sub{font-size:12px;color:#8b949e;margin-left:8px}.role{font-size:10px;color:#8b949e}
.marker{margin:10px 0;border-left:3px solid #30363d;padding-left:12px}
.mname{font-weight:700;color:#d2a8ff}.gt{background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:6px 10px;margin:6px 0;font-size:13px}
.bl-helps{color:#3fb950}.bl-hurts{color:#ff7b72}.bl-no-different{color:#e3b341}
table{width:100%;border-collapse:collapse;font-size:12px}th{text-align:left;color:#8b949e;font-weight:600;border-bottom:1px solid #30363d;padding:4px 8px}
td{border-top:1px solid #21262d;padding:6px 8px;vertical-align:top}td:first-child{font-weight:600;width:170px}
.bar{display:flex;height:18px;border-radius:4px;overflow:hidden;margin-top:3px;font-size:9px;line-height:18px;color:#000}
.seg{text-align:center;overflow:hidden;white-space:nowrap}.seg.r{background:#ff7b72}.seg.f{background:#58a6ff}.seg.s{background:#e3b341}
.chip{display:inline-block;font-size:10px;padding:2px 6px;border-radius:8px;margin:1px;font-weight:700}
.ok{background:#2ea04333;color:#3fb950}.bad{background:#f8514933;color:#ff7b72}.warn{background:#d2992233;color:#e3b341}
.muted{color:#6e7681}.flaws{background:#161b22;border:1px solid #f85149;border-radius:10px;padding:16px;margin:14px 0}.flaws li{margin:6px 0}"""

doc=f"""<!doctype html><html><head><meta charset="utf-8"><title>v3 Golden + Probabilities</title><style>{css}</style></head>
<body><div class="wrap"><h1>Causal Benchmark v3 — Golden Samples + Activation Probabilities ({d['n']} pairs × {len(d['models'])} models)</h1>
<p class="sub">Local file (MIMIC DUA — not uploaded). Bars = softmax over the answer tokens from the model's logits.</p>
{intro}{''.join(secs)}</div></body></html>"""
out=Path("/scratch/users/karun09/causal_benchmark_v3/inspection/golden_viewer_v3.html")
out.write_text(doc); print(f"wrote {out} ({len(doc)//1024} KB)")
