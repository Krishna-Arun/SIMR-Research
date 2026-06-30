"""Pretty-print the last generated question record from any benchmark's questions.jsonl.
Usage: python show_question.py <path/to/questions.jsonl> [n_last]
"""
import json, sys

path = sys.argv[1]
n = int(sys.argv[2]) if len(sys.argv) > 2 else 1
recs = [json.loads(l) for l in open(path) if l.strip()]
if not recs:
    print("(no questions yet)"); sys.exit(0)

def line(k, v): print(f"  {k}: {v}")

for r in recs[-n:]:
    print("=" * 90)
    print(f"[{r.get('question_id')}]  pipeline={r.get('pipeline_version')}")
    print(f"QUESTION:\n  {r.get('question_text','').strip()}")
    # Benchmark A
    if "gold_labs" in r:
        line("type", r.get("type"))
        print("  gold labs:")
        for g in r.get("gold_labs", []):
            print(f"    - {g.get('label')}: value={g.get('patient_value')} {g.get('unit','')} "
                  f"abnormal={g.get('abnormal_flag')} cite={ (g.get('guideline_citation') or {}).get('pmid')}")
        print("  reference_answer:", str(r.get("reference_answer",""))[:300])
        print("  causal_chain:", [str(x)[:80] for x in (r.get("causal_chain") or [])][:4])
    # Benchmark B
    if "target_labs_detail" in r:
        line("procedure", (r.get("procedure") or {}).get("label"))
        print("  predicted lab trajectories (ground truth):")
        for d in r.get("target_labs_detail", []):
            print(f"    - {d.get('label')}: TRUE={d.get('true_direction')} (base {d.get('baseline')}->post {d.get('post_rep')}, "
                  f"ref [{d.get('ref_lower')},{d.get('ref_upper')}]) | optimizer={d.get('expected_direction')} match={d.get('direction_match')}")
            print(f"        justification: {str(d.get('causal_justification',''))[:160]}")
    # Benchmark C
    if "shown_post_owner" in r:
        line("procA (patient A)", r.get("procA")); line("procB (patient B)", r.get("procB"))
        line("shown_post_owner (GROUND TRUTH)", r.get("shown_post_owner"))
        line("optimizer_predicted_owner", r.get("optimizer_predicted_owner"))
        line("match_quality", r.get("match_quality"))
        print("  causal_justification:", str(r.get("causal_justification",""))[:300])
    # common
    ev = r.get("evaluator_scores", {})
    print("  evaluator dims:", {k: v.get("pass") for k, v in ev.items()})
    line("n_iterations", r.get("n_iterations"))
    line("pubmed_citations", [c.get("pmid") for c in (r.get("pubmed_citations") or [])][:6])
print("=" * 90)
print(f"total questions in file: {len(recs)}")
