"""Export questions.jsonl -> a human-readable Markdown file per benchmark.
Usage: python export_readable.py A|B|C   (writes outputs/questions_readable.md)
"""
import json, sys
from pathlib import Path

X = sys.argv[1] if len(sys.argv) > 1 else "A"
base = Path(f"/scratch/users/karun09/Version_2/Benchmark_{X}/Question_Generation/outputs")
src = base / "questions.jsonl"
out = base / "questions_readable.md"
rows = [json.loads(l) for l in open(src)] if src.exists() else []

def cite(g):
    c = g.get("guideline_citation") or {}
    return f"PMID {c.get('pmid')}" if c.get("pmid") else "—"

L = [f"# Benchmark {X} — {len(rows)} questions\n"]
for i, r in enumerate(rows):
    qid = r.get("question_id", f"q{i:05d}")
    L.append(f"\n---\n\n## {qid}  ·  subject {r.get('subject_id')} / hadm {r.get('hadm_id') or r.get('pair_uid','')}")
    demo = r.get("demographics", {})
    if demo:
        L.append(f"*{demo.get('anchor_age','?')}{demo.get('gender','?')}, {', '.join(r.get('comorbidities',{}) ) or 'no comorbidities coded'}*")
    L.append(f"\n**Question:** {r.get('question_text','')}\n")
    if X == "A":
        L.append(f"**Type:** {r.get('type')}")
        L.append(f"**Reference answer:** {r.get('reference_answer','')}")
        L.append("**Causal chain:**")
        for s in r.get("causal_chain", []): L.append(f"- {s}")
        L.append("\n**Gold labs (the answer key — agent must REQUEST these):**")
        L.append("| lab | patient value | abnormal | in chart | citation | why |")
        L.append("|---|---|---|---|---|---|")
        for g in r.get("gold_labs", []):
            L.append(f"| {g.get('label')} | {g.get('patient_value')} {g.get('unit','')} | {g.get('abnormal_flag')} | {g.get('in_chart')} | {cite(g)} | {str(g.get('proposed_reason',''))[:120]} |")
        if r.get("gold_micro"):
            L.append("\n**Gold microbiology:** " + "; ".join(f"{m.get('specimen','')}/{m.get('organism','')}" for m in r.get("gold_micro", [])))
    elif X == "B":
        L.append(f"**Procedure (time-zero):** {(r.get('procedure') or {}).get('label', r.get('procedure',''))}")
        L.append("\n**Per-lab trajectory (gold = data-derived `true_direction`):**")
        L.append("| lab | expected (model) | TRUE direction | match | justification |")
        L.append("|---|---|---|---|---|")
        for p in r.get("per_lab", []):
            L.append(f"| {p.get('label')} | {p.get('expected_direction')} | {p.get('true_direction')} | {p.get('direction_match')} | {str(p.get('causal_justification',''))[:120]} |")
    elif X == "C":
        L.append(f"**Patient A procedure:** {(r.get('patient_A') or {}).get('procedure','')}  ·  **Patient B procedure:** {(r.get('patient_B') or {}).get('procedure','')}")
        L.append(f"**Shown post-state owner (GOLD):** {r.get('shown_post_owner')}  ·  **predicted_owner:** {r.get('predicted_owner')}")
        L.append(f"\n**Causal justification:** {r.get('causal_justification','')}")
        for d in r.get("distinguishing_features", []):
            L.append(f"- {d.get('procedure','')}: {d.get('expected_effect','')}")
    pc = r.get("pubmed_citations", [])
    if pc:
        L.append("\n**PubMed:** " + "; ".join(f"PMID {c.get('pmid')} ({str(c.get('title',''))[:60]})" for c in pc[:3]))

out.write_text("\n".join(L))
print(f"wrote {out}  ({len(rows)} questions)")
