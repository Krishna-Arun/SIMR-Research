"""
build_viewer.py — render golden_samples.json into a self-contained LOCAL html file
for side-by-side manual inspection across models. No external upload (MIMIC DUA).
"""
import json, html
from pathlib import Path

V2 = Path("/scratch/users/karun09/causal_benchmark_v2/inspection")
d = json.loads((V2/"golden_samples.json").read_text())
models = d["models"]

def chip(txt, cls): return f'<span class="chip {cls}">{html.escape(txt)}</span>'

rows = []
for g in d["samples"]:
    head = (f'<h2>{g["pair_id"]} '
            f'<span class="tag">{html.escape(g["tag"])}</span> '
            f'<span class="sub">{g["intervention_a"]} vs {g["intervention_b"]} · '
            f'match={g["match_quality"]["score"]} · comorbid Δ={g["match_quality"]["comorbidity_distance"]}</span>')
    if g["hpi_leak_a"]:
        head += chip("HPI LEAKS POST-PROCEDURE", "bad")
    head += "</h2>"

    marker_blocks = []
    for m in g["scored_markers"]:
        gtA = g["ground_truth"][m]["A"]; gtB = g["ground_truth"][m]["B"]
        if not gtA or not gtB: continue
        truth = "A_final &gt; B_final" if gtA["post_final"] > gtB["post_final"] else "A_final &lt; B_final"
        th = (f'<div class="gt">GT &nbsp; '
              f'<b>A</b> {gtA["baseline"]}→{gtA["post_final"]} <i>({gtA["direction"]})</i> &nbsp;|&nbsp; '
              f'<b>B</b> {gtB["baseline"]}→{gtB["post_final"]} <i>({gtB["direction"]})</i> &nbsp; '
              f'<span class="truth">truth: {truth}</span></div>')
        mrows = []
        for name in models:
            mm = g["models"].get(name, {}).get(m)
            if not mm or not mm["A"] or not mm["B"]:
                mrows.append(f'<tr><td>{html.escape(name)}</td><td colspan="3" class="muted">(missing / unparsed)</td></tr>')
                continue
            A, B = mm["A"], mm["B"]
            flags = ""
            if mm["mccs_correct"]: flags += chip("MCCS ✓", "ok")
            else: flags += chip("MCCS ✗", "bad")
            if mm["dir_conf_disagree_A"]: flags += chip("dir≠conf", "warn")
            if mm["scale_off_A"]: flags += chip("scale-off", "warn")
            ac = "off" if mm["scale_off_A"] else ""
            mrows.append(
                f'<tr><td>{html.escape(name)}</td>'
                f'<td class="{ac}">A {A["start"]}→<b>{A["final"]}</b><br><i>{A["parsed_dir"]} / conf:{A["conf_dir"]}</i></td>'
                f'<td>B {B["start"]}→<b>{B["final"]}</b><br><i>{B["parsed_dir"]}</i></td>'
                f'<td>{flags}</td></tr>')
        marker_blocks.append(
            f'<div class="marker"><div class="mname">{html.escape(m)}</div>{th}'
            f'<table>{"".join(mrows)}</table></div>')

    hpi = html.escape(g["hpi_a"])
    for t in ["after the procedure","post procedure","post-procedure","was transferred","underwent",
              "stent was","during the procedure","successfully","cath showed","s/p PCI","s/p pci"]:
        hpi = hpi.replace(t, f'<mark>{t}</mark>').replace(t.capitalize(), f'<mark>{t.capitalize()}</mark>')
    detail = f'<details><summary>HPI shown to model (episode A) — leak terms highlighted</summary><pre>{hpi}</pre></details>'

    rows.append(f'<section>{head}{"".join(marker_blocks)}{detail}</section>')

flaws = """
<div class="flaws">
<h2>Systemic flaws this view exposes (that aggregate MCCS hides)</h2>
<ol>
<li><b>The MCCS label rewards the WRONG clinical reasoning.</b> For PCI episodes troponin <i>rises</i>
(periprocedural injury, e.g. 2.29→2.77) while matched controls fall. So a model that correctly reasons
"PCI lowers troponin" is marked <b>WRONG</b>. The benchmark scores the acute-hump artifact, not whether
the model understands the intervention's purpose.</li>
<li><b>Pairs are not independent.</b> The same treated episode (e.g. ep_pci_00000) appears in many pairs
(reused ×3). n=654 "pairs" ≈ 218 unique PCI episodes. Aggregate significance is inflated ~3×.</li>
<li><b>The Sodium negative control is trivially gamed.</b> Every model just echoes the baseline and predicts
"stable", so Sodium-MCCS collapses to "is baseline_A &gt; baseline_B" — it measures input copying, not causality.</li>
<li><b>Two contradictory "directions" are recorded.</b> The parsed-text direction disagrees with the
logit-confidence direction in 68–83% of episodes. ECE (uses conf-dir) and MCCS (uses trajectory) grade
incompatible signals.</li>
<li><b>Broken/garbage outputs are scored as real.</b> DeepSeek frequently emits 0.0 or wrong-scale values
(e.g. troponin 0.0→0.0, or 24→96); these enter MCCS as if valid, so its score is mostly a broken-output rate.</li>
<li><b>MCCS credit on near-zero noise.</b> "Best match" pairs distinguish 0.01 vs 0.05 troponin — within
assay noise, clinically meaningless — yet score full credit.</li>
<li><b>Raw model text is NOT stored.</b> Only parsed trajectories survive, so a wrong score can't be
attributed to model vs parser. v2 must capture raw text.</li>
</ol>
</div>"""

css = """
body{font:14px/1.5 -apple-system,system-ui,sans-serif;margin:0;background:#0d1117;color:#e6edf3}
.wrap{max-width:1100px;margin:0 auto;padding:24px}
h1{font-size:22px} h2{font-size:16px;margin:18px 0 8px}
section{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:16px;margin:16px 0}
.tag{font-size:11px;background:#1f6feb33;color:#79c0ff;padding:2px 8px;border-radius:10px;margin-left:6px}
.sub{font-size:12px;color:#8b949e;font-weight:400;margin-left:8px}
.marker{margin:10px 0;border-left:3px solid #30363d;padding-left:12px}
.mname{font-weight:700;color:#d2a8ff;margin-bottom:4px}
.gt{background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:6px 10px;margin-bottom:6px;font-size:13px}
.truth{color:#f0883e;font-weight:700;margin-left:8px}
table{width:100%;border-collapse:collapse;font-size:12.5px}
td{border-top:1px solid #21262d;padding:6px 8px;vertical-align:top}
td:first-child{font-weight:600;width:200px;color:#adbac7}
.off{background:#f8514922;border-radius:4px}
.chip{display:inline-block;font-size:10.5px;padding:2px 7px;border-radius:9px;margin:1px 2px;font-weight:700}
.ok{background:#2ea04333;color:#3fb950} .bad{background:#f8514933;color:#ff7b72}
.warn{background:#d2992233;color:#e3b341} .muted{color:#6e7681}
details{margin-top:8px} summary{cursor:pointer;color:#8b949e;font-size:12px}
pre{white-space:pre-wrap;background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:10px;font-size:11.5px;color:#adbac7}
mark{background:#bb800933;color:#e3b341;padding:0 2px}
.flaws{background:#161b22;border:1px solid #f85149;border-radius:10px;padding:16px;margin:16px 0}
.flaws li{margin:7px 0}
</style>"""

doc = f"""<!doctype html><html><head><meta charset="utf-8"><title>Golden Sample Inspection</title><style>{css}</head>
<body><div class="wrap">
<h1>Causal Benchmark — Golden Sample Inspection ({d['n']} pairs × {len(models)} models)</h1>
<p class="sub">Side-by-side raw inputs, predictions, and ground truth. Local file (MIMIC DUA — not uploaded externally).</p>
{flaws}
{"".join(rows)}
</div></body></html>"""

out = V2/"golden_viewer.html"
out.write_text(doc)
print(f"wrote {out}  ({len(doc)//1024} KB)")
