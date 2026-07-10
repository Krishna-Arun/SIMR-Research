"""Build the results deck: scans results_*.json -> plots + a self-contained HTML slide deck.
Robust to partial data (only renders models/benchmarks present). Re-runnable any time.

Deliverables (in Eval/):
  plots/accuracy_{nopubmed,pubmed}.png        accuracy per model x benchmark
  plots/confidence_{nopubmed,pubmed}.png      recorded confidence vs actual accuracy
  plots/calibration_{nopubmed,pubmed}.png     reliability diagrams (recorded vs actual, binned) + ECE
  deck.html                                   neat self-contained slide deck (embeds all plots + tables)
"""
import json, glob, os, base64
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

ED = "/scratch/users/karun09/Version_2/Eval"
PLOTS = os.path.join(ED, "plots"); os.makedirs(PLOTS, exist_ok=True)
BMS = ["A", "B", "C"]
BM_TITLE = {"A": "A — Lab-request + Dx/Rx", "B": "B — Post-proc trajectory", "C": "C — Counterfactual"}
# scoring rows shown in accuracy plot/tables — A is judged on TWO axes (answer + lab-request)
METRIC_ROWS = [("A", "A: Dx/Rx answer"), ("A_lab", "A: lab-request"),
               ("B", "B: trajectory"), ("C", "C: counterfactual")]
def get_metric(data, key, m, cond):
    if key == "A_lab":
        return (data.get(("A", m, cond)) or {}).get("extra", {}).get("lab_request")
    return (data.get((key, m, cond)) or {}).get("acc")
def get_ece(data, key, m, cond):
    if key == "A_lab": return None
    return (data.get((key, m, cond)) or {}).get("ece")
NAME = {"Qwen3-32B": "Qwen3-32B", "Meta-Llama-3.1-8B-Instruct": "Llama-3.1-8B", "gemma-3-27b-it": "Gemma-3-27B"}
COLORS = {"Qwen3-32B": "#4477aa", "Llama-3.1-8B": "#ee6677", "Gemma-3-27B": "#228833"}
def disp(m): return NAME.get(m, m)
def col(m): return COLORS.get(disp(m), "#888888")


def parse(fn):
    b = os.path.basename(fn)[len("results_"):-len(".json")]
    t = b.split("_"); return t[0], "_".join(t[1:-1]), t[-1]   # bm, model, cond


def ece(pairs, nb=10):
    if not pairs: return None
    conf = np.array([p[0] for p in pairs], float); acc = np.array([p[1] for p in pairs], float)
    e = 0.0; n = len(pairs)
    for i in range(nb):
        lo, hi = i / nb, (i + 1) / nb
        m = (conf > lo) & (conf <= hi) if i > 0 else (conf >= lo) & (conf <= hi)
        if m.sum(): e += abs(acc[m].mean() - conf[m].mean()) * m.sum() / n
    return e


def gather():
    data = {}
    for fn in glob.glob(os.path.join(ED, "results_[ABC]_*pubmed.json")):
        bm, model, cond = parse(fn)
        if cond not in ("pubmed", "nopubmed"): continue
        try: d = json.load(open(fn))
        except Exception: continue
        s = d.get("summary", {}); res = d.get("results", [])
        rec = {"pairs": [], "n": s.get("n"), "acc": None, "extra": {}}
        if bm == "A":
            rec["acc"] = s.get("mean_answer"); rec["extra"]["lab_request"] = s.get("mean_lab_request")
            for r in res:
                c, a = r.get("confidence"), r.get("answer_score")
                if c is not None and a is not None: rec["pairs"].append((float(c), float(a)))
        elif bm == "B":
            rec["acc"] = s.get("mean_direction_score")
            for r in res:
                pl = r.get("per_lab", {})
                for lab, dc in (r.get("preds", {}) or {}).items():
                    conf = dc[1] if isinstance(dc, (list, tuple)) and len(dc) > 1 else None
                    if conf is None: continue
                    rec["pairs"].append((float(conf), 1.0 if pl.get(lab) == 1.0 else 0.0))
        elif bm == "C":
            rec["acc"] = s.get("accuracy")
            for r in res:
                c = r.get("confidence")
                if c is not None: rec["pairs"].append((float(c), float(r.get("correct", 0))))
        rec["ece"] = ece(rec["pairs"])
        rec["mean_conf"] = float(np.mean([p[0] for p in rec["pairs"]])) if rec["pairs"] else None
        data[(bm, model, cond)] = rec
    return data


def b64(path):
    with open(path, "rb") as f: return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def acc_plot(data, models, cond, path):
    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    keys = [k for k, _ in METRIC_ROWS]; labels = [l for _, l in METRIC_ROWS]
    x = np.arange(len(keys)); w = 0.8 / max(1, len(models))
    for i, m in enumerate(models):
        vals = [get_metric(data, k, m, cond) for k in keys]
        ax.bar(x + i * w, [v if v is not None else 0 for v in vals], w, label=disp(m), color=col(m))
        for j, v in enumerate(vals):
            if v is not None: ax.text(x[j] + i * w, v + 0.02, f"{v:.2f}", ha="center", fontsize=7)
    ax.set_xticks(x + w * (len(models) - 1) / 2); ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylim(0, 1.05); ax.set_ylabel("accuracy / mean score")
    ax.set_title(f"Accuracy by model & benchmark — {'WITH' if cond=='pubmed' else 'WITHOUT'} PubMed tool")
    ax.legend(fontsize=9); ax.grid(axis="y", alpha=0.3)
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def conf_plot(data, models, cond, path):
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.3))
    for ax, bm in zip(axes, BMS):
        ms = [m for m in models if data.get((bm, m, cond), {}).get("pairs")]
        x = np.arange(len(ms))
        conf = [data[(bm, m, cond)]["mean_conf"] for m in ms]
        acc = [np.mean([p[1] for p in data[(bm, m, cond)]["pairs"]]) for m in ms]
        ax.bar(x - 0.2, conf, 0.4, label="recorded confidence", color="#cc6677")
        ax.bar(x + 0.2, acc, 0.4, label="actual accuracy", color="#4477aa")
        ax.set_xticks(x); ax.set_xticklabels([disp(m) for m in ms], rotation=18, ha="right", fontsize=8)
        ax.set_ylim(0, 1.05); ax.set_title(f"Benchmark {bm}")
        if ax is axes[0]: ax.legend(fontsize=8); ax.set_ylabel("value")
    fig.suptitle(f"Recorded confidence vs actual accuracy — {'WITH' if cond=='pubmed' else 'WITHOUT'} PubMed")
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def calib_plot(data, models, cond, path):
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.3))
    for ax, bm in zip(axes, BMS):
        ax.plot([0, 1], [0, 1], "k--", lw=1, alpha=0.5)
        for m in models:
            r = data.get((bm, m, cond))
            if not r or not r["pairs"]: continue
            conf = np.array([p[0] for p in r["pairs"]]); acc = np.array([p[1] for p in r["pairs"]])
            xs, ys = [], []
            for i in range(10):
                lo, hi = i / 10, (i + 1) / 10
                mask = (conf > lo) & (conf <= hi) if i > 0 else (conf >= 0) & (conf <= hi)
                if mask.sum() >= 3: xs.append(conf[mask].mean()); ys.append(acc[mask].mean())
            if xs:
                lbl = f"{disp(m)} (ECE {r['ece']:.2f})" if r["ece"] is not None else disp(m)
                ax.plot(xs, ys, marker="o", ms=4, color=col(m), label=lbl)
        ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.set_title(f"Benchmark {bm}")
        ax.set_xlabel("recorded confidence")
        if ax is axes[0]: ax.set_ylabel("actual accuracy")
        ax.legend(fontsize=7)
    fig.suptitle(f"Calibration / reliability — {'WITH' if cond=='pubmed' else 'WITHOUT'} PubMed (diagonal = perfect)")
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def table(data, models, cond):
    rows = ["<tr><th>Benchmark (score)</th>" + "".join(f"<th>{disp(m)}</th>" for m in models) + "</tr>"]
    for key, label in METRIC_ROWS:
        cells = []
        for m in models:
            v = get_metric(data, key, m, cond); e = get_ece(data, key, m, cond)
            if v is not None:
                cells.append(f"<td>{v:.3f}<br><span class=sub>ECE {e:.2f}</span></td>" if e is not None else f"<td>{v:.3f}</td>")
            else:
                cells.append("<td class=pending>—</td>")
        rows.append(f"<tr><td class=bm>{label}</td>" + "".join(cells) + "</tr>")
    return "<table>" + "".join(rows) + "</table>"


def delta_table(data, models):
    rows = ["<tr><th>Benchmark (score)</th>" + "".join(f"<th>{disp(m)}</th>" for m in models) + "</tr>"]
    for key, label in METRIC_ROWS:
        cells = []
        for m in models:
            a = get_metric(data, key, m, "pubmed")
            b = get_metric(data, key, m, "nopubmed")
            if a is not None and b is not None:
                d = a - b; cls = "pos" if d > 0.005 else ("neg" if d < -0.005 else "")
                cells.append(f"<td class={cls}>{d:+.3f}</td>")
            else:
                cells.append("<td class=pending>—</td>")
        rows.append(f"<tr><td class=bm>{label}</td>" + "".join(cells) + "</tr>")
    return "<table>" + "".join(rows) + "</table>"


def main():
    data = gather()
    models = sorted({k[1] for k in data}, key=lambda m: ("Qwen" not in m, "gemma" in m, m))
    imgs = {}
    for cond in ("nopubmed", "pubmed"):
        for kind, fn in (("accuracy", acc_plot), ("confidence", conf_plot), ("calibration", calib_plot)):
            p = os.path.join(PLOTS, f"{kind}_{cond}.png")
            try:
                fn(data, models, cond, p); imgs[(kind, cond)] = b64(p)
            except Exception as e:
                imgs[(kind, cond)] = None; print("plot err", kind, cond, e)

    done = sorted({(k[0], k[1], k[2]) for k in data})
    status = f"{len(done)} result files across {len(models)} models"
    def img(kind, cond):
        u = imgs.get((kind, cond))
        return f'<img src="{u}">' if u else '<p class=pending>(pending — not all runs finished)</p>'

    slides = []
    slides.append(f"""<section><div class=center>
      <h1>Causal Clinical Reasoning Benchmark</h1>
      <h2>Does a literature (PubMed) tool help LLMs reason about ICU interventions?</h2>
      <p class=meta>Models: {', '.join(disp(m) for m in models) or '(loading)'} &nbsp;·&nbsp; Benchmarks A/B/C &nbsp;·&nbsp; 100 Q each &nbsp;·&nbsp; with vs without PubMed</p>
      <p class=meta>Questions generated by gpt-oss-20B · graded by gpt-oss-20B (ruthless-mentor judge) · MIMIC-IV (PHI on-node)</p>
      <p class=sub>{status}</p></div></section>""")
    slides.append(f"""<section><h2>Setup</h2>
      <ul>
      <li><b>A — Lab-request + Dx/Rx:</b> agent requests labs (scored), then gives diagnosis/intervention (0/0.5/1).</li>
      <li><b>B — Post-procedure trajectory:</b> predict each lab Rising/Falling/Stable + confidence (1/0.5/0).</li>
      <li><b>C — Counterfactual:</b> which of two patients produced the observed post-state (0/1) + confidence.</li>
      <li><b>Tool condition:</b> "with tool" = agent may call the PubMed search tool; "without tool" = no retrieval.</li>
      <li><b>Confidence:</b> every answer carries a self-reported confidence → calibration vs actual accuracy (ECE).</li>
      </ul></section>""")
    slides.append(f"<section><h2>Accuracy — WITHOUT tool</h2>{img('accuracy','nopubmed')}{table(data,models,'nopubmed')}</section>")
    slides.append(f"<section><h2>Accuracy — WITH tool (PubMed)</h2>{img('accuracy','pubmed')}{table(data,models,'pubmed')}</section>")
    slides.append(f"<section><h2>Effect of the PubMed tool (Δ = with − without)</h2>{delta_table(data,models)}<p class=sub>green = tool helped, red = tool hurt.</p></section>")
    slides.append(f"<section><h2>Recorded confidence vs actual accuracy — WITHOUT tool</h2>{img('confidence','nopubmed')}</section>")
    slides.append(f"<section><h2>Recorded confidence vs actual accuracy — WITH tool</h2>{img('confidence','pubmed')}</section>")
    slides.append(f"<section><h2>Calibration / reliability — WITHOUT tool</h2>{img('calibration','nopubmed')}</section>")
    slides.append(f"<section><h2>Calibration / reliability — WITH tool</h2>{img('calibration','pubmed')}</section>")

    css = """
    *{box-sizing:border-box;margin:0;padding:0} html{scroll-snap-type:y mandatory;scroll-behavior:smooth}
    body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1a1a2e;background:#0f1226}
    section{min-height:100vh;scroll-snap-align:start;padding:5vh 7vw;background:#f7f8fc;
      border-bottom:6px solid #4477aa;display:flex;flex-direction:column;justify-content:center}
    section:nth-child(odd){background:#eef1f8}
    h1{font-size:2.6rem;margin-bottom:.5rem;color:#16213e} h2{font-size:1.7rem;margin-bottom:1rem;color:#16213e}
    .center{text-align:center} .meta{color:#445;margin:.3rem 0;font-size:1rem} .sub{color:#778;font-size:.85rem}
    ul{margin-left:1.4rem;line-height:2;font-size:1.05rem} li{margin-bottom:.2rem}
    img{max-width:100%;max-height:62vh;display:block;margin:0 auto 1rem;border-radius:8px;box-shadow:0 4px 18px rgba(0,0,0,.15);background:#fff}
    table{border-collapse:collapse;margin:1rem auto;font-size:.95rem;background:#fff;box-shadow:0 2px 10px rgba(0,0,0,.08)}
    th,td{border:1px solid #dde;padding:.5rem .9rem;text-align:center} th{background:#16213e;color:#fff}
    td.bm{text-align:left;font-weight:600} .sub{font-size:.72rem;color:#99a}
    td.pos{background:#d9f2d9;color:#161;font-weight:600} td.neg{background:#fcdcdc;color:#911;font-weight:600}
    td.pending,.pending{color:#bbb;font-style:italic}
    .nav{position:fixed;bottom:14px;right:18px;color:#fff;background:#16213e;padding:6px 12px;border-radius:20px;font-size:.8rem;opacity:.85}
    """
    html = f"<!doctype html><html><head><meta charset=utf-8><title>Causal Benchmark Results</title><style>{css}</style></head><body>{''.join(slides)}<div class=nav>scroll ↓ · {len(slides)} slides</div></body></html>"
    out = os.path.join(ED, "deck.html"); open(out, "w").write(html)
    print("wrote", out, "|", status, "| models:", [disp(m) for m in models])


if __name__ == "__main__":
    main()
