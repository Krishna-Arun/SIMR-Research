"""Aggregate Phase-2 results_*.json into a with-vs-without-PubMed Δ table + summary.json."""
import json, glob, re
from pathlib import Path
from collections import defaultdict

E = Path("/scratch/users/karun09/Version_2/Eval")
METRIC = {"A": ("mean_answer", "mean_lab_request"), "B": ("mean_direction_score", "ece"), "C": ("accuracy", "ece")}
data = defaultdict(dict)   # (bench,model) -> {cond: summary}
for f in glob.glob(str(E / "results_*.json")):
    try:
        s = json.load(open(f))["summary"]
    except Exception:
        continue
    cond = "pubmed" if s.get("pubmed") else "nopubmed"
    data[(s["benchmark"], s["model"])][cond] = s

rows = []
print(f"\n{'BENCH':<6}{'MODEL':<16}{'METRIC':<20}{'no-PubMed':>10}{'PubMed':>10}{'Δ':>9}")
print("-" * 71)
for (b, m), conds in sorted(data.items()):
    for metric in METRIC.get(b, ()):
        npm = conds.get("nopubmed", {}).get(metric)
        pm = conds.get("pubmed", {}).get(metric)
        d = (pm - npm) if (isinstance(npm, (int, float)) and isinstance(pm, (int, float))) else None
        rows.append({"benchmark": b, "model": m, "metric": metric,
                     "nopubmed": npm, "pubmed": pm, "delta": d})
        fmt = lambda x: f"{x:.3f}" if isinstance(x, (int, float)) else "  -  "
        print(f"{b:<6}{m:<16}{metric:<20}{fmt(npm):>10}{fmt(pm):>10}{(('%+.3f'%d) if d is not None else '  -  '):>9}")
print("\nNote: for ECE lower is better; the headline reasoning metric is mean_answer (A) / "
      "mean_direction_score (B) / accuracy (C). Δ = PubMed − no-PubMed.")
(E / "summary.json").write_text(json.dumps(rows, indent=2))
print(f"\nwrote {E/'summary.json'}")
