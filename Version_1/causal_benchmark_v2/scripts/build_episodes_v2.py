"""
build_episodes_v2.py — produce a cleaned episode set from the v1 extraction.

Two fixes requested (B):
  1. LEAKAGE SCRUB — the v1 HPI comes from the discharge summary and in 33% of PCI cases
     narrates the procedure/aftermath ("after the procedure...", "stent was placed",
     "transferred to CCU"). We drop any sentence containing post-index leak terms so the
     prompt only describes the PRESENTATION, not the outcome.
  2. COMORBIDITY INJECTION — v1 stores a comorbidity vector but never shows it to the model.
     We render it into clinical_context as a text field (safe: chronic, pre-index) so the
     prompt builder surfaces it.

Also records provenance (what was scrubbed) for audit. Structural fixes (sub-day anchoring,
pair de-duplication, DiD scoring, raw-text capture) are handled elsewhere in v2; this script
only does the two prompt-content fixes that don't require re-extraction from raw MIMIC.

Output: data/episodes_v2.json  +  data/scrub_report.json
"""
import json, re
from pathlib import Path

V1 = Path("/scratch/users/karun09/CAUSAL_BENCHMARK/data/episodes.json")
OUT = Path("/scratch/users/karun09/causal_benchmark_v2/data/episodes_v2.json")
REPORT = Path("/scratch/users/karun09/causal_benchmark_v2/data/scrub_report.json")

LEAK_TERMS = [
    "after the procedure", "post procedure", "post-procedure", "post-pci", "post pci",
    "was transferred", "transferred to", "tolerated the procedure", "tolerated well",
    "underwent", "cath showed", "catheterization showed", "was taken to", "taken to the cath",
    "stent was", "stents were", "during the procedure", "successfully", "s/p pci", "s/p cabg",
    "post-cath", "post cath", "following the procedure", "intra-procedure", "periprocedural",
    "ccu for", "was extubated", "drug-eluting", "ballooning", "angioplasty was",
]
COMORBID_LABELS = {
    "diabetes":"diabetes","hypertension":"hypertension","ckd":"chronic kidney disease",
    "heart_failure":"heart failure","afib":"atrial fibrillation","prior_mi":"prior MI",
    "hyperlipidemia":"hyperlipidemia","copd":"COPD","cad":"coronary artery disease","valve":"valvular disease",
}

def split_sentences(text):
    # split on sentence boundaries and newlines; keep it simple and robust
    parts = re.split(r'(?<=[.!?])\s+|\n+', text)
    return [p for p in parts if p.strip()]

def scrub_hpi(hpi):
    if not hpi: return hpi, 0, 0
    sents = split_sentences(hpi)
    kept, dropped = [], 0
    for s in sents:
        low = s.lower()
        if any(t in low for t in LEAK_TERMS):
            dropped += 1
            continue
        kept.append(s)
    return " ".join(kept).strip(), dropped, len(sents)

def comorbidity_text(vec):
    present = [COMORBID_LABELS[k] for k,v in vec.items() if v and k in COMORBID_LABELS]
    return ("Documented comorbidities: " + ", ".join(present) + ".") if present else "Documented comorbidities: none coded."

def main():
    data = json.loads(V1.read_text())
    eps = data["episodes"]
    total_dropped = total_sents = n_with_leak = 0
    per_ep = []
    for e in eps:
        cc = e.setdefault("clinical_context", {})
        hpi = cc.get("hpi", "") or ""
        scrubbed, dropped, nsent = scrub_hpi(hpi)
        cc["hpi"] = scrubbed
        cc["hpi_scrubbed_sentences"] = dropped
        # inject comorbidities as a prompt-visible text field
        cc["comorbidity_text"] = comorbidity_text(e.get("comorbidities", {}))
        total_dropped += dropped; total_sents += nsent
        if dropped: n_with_leak += 1
        per_ep.append({"episode_id": e["episode_id"], "arm": e["intervention"]["type"],
                       "sentences": nsent, "dropped": dropped})

    data["benchmark"] = data.get("benchmark","") + "+v2clean"
    data["v2_fixes"] = {
        "leakage_scrub": "dropped HPI sentences containing post-index/procedure narrative",
        "comorbidity_injection": "added clinical_context.comorbidity_text (chronic, pre-index)",
        "leak_terms": LEAK_TERMS,
    }
    OUT.write_text(json.dumps(data, indent=2))
    REPORT.write_text(json.dumps({
        "n_episodes": len(eps),
        "episodes_with_leak_sentences": n_with_leak,
        "pct_episodes_scrubbed": round(100*n_with_leak/len(eps),1),
        "total_sentences": total_sents,
        "total_sentences_dropped": total_dropped,
        "pct_sentences_dropped": round(100*total_dropped/max(total_sents,1),1),
        "per_episode": per_ep,
    }, indent=2))
    print(f"wrote {OUT}")
    print(f"episodes: {len(eps)} | with leak sentences: {n_with_leak} ({100*n_with_leak/len(eps):.0f}%) | "
          f"sentences dropped: {total_dropped}/{total_sents} ({100*total_dropped/max(total_sents,1):.1f}%)")

if __name__ == "__main__":
    main()
