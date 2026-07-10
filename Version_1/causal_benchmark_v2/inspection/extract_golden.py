"""
extract_golden.py — pull N golden matched-pairs with FULL detail across every model,
side by side, so flaws that aggregate MCCS hides become visible.

For each golden pair we emit, per model:
  - episode A & B predicted trajectory (start, final), parsed direction, logit-confidence direction
  - MCCS correctness on each scored marker
  - ground-truth: baselines, post-final values, true direction
  - internal-coherence flags (parsed-dir vs confidence-dir disagreement; scale hallucination)
Plus the raw prompt + the HPI-leakage flag.

Output: inspection/golden_samples.json  (consumed by build_viewer.py)
"""
import json, re
import numpy as np
from pathlib import Path

BENCH = Path("/scratch/users/karun09/CAUSAL_BENCHMARK")
V2 = Path("/scratch/users/karun09/causal_benchmark_v2")

eps = {e["episode_id"]: e for e in json.loads((BENCH/"data/episodes.json").read_text())["episodes"]}
mp = json.loads((BENCH/"data/matched_pairs.json").read_text())
pairs = {p["pair_id"]: p for p in mp["pairs"]}

MODELS = [
    ("Qwen3-8B / cot",       "Qwen_Qwen3-8B_cot_ckpt.json"),
    ("Qwen3-8B / zero_shot", "Qwen_Qwen3-8B_zero_shot_ckpt.json"),
    ("DeepSeek-R1-7B / zero_shot", "deepseek-ai_DeepSeek-R1-Distill-Qwen-7B_zero_shot_ckpt.json"),
]
CKPT = {name: json.loads((BENCH/"answers"/fn).read_text()) for name, fn in MODELS if (BENCH/"answers"/fn).exists()}

LEAK_TERMS = ["after the procedure","post procedure","post-procedure","was transferred",
              "tolerated the procedure","underwent","cath showed","was taken to","stent was",
              "during the procedure","successfully","s/p pci"]

def series(vals):
    if isinstance(vals, dict): vals = vals.get("resampled_values", [])
    return [float(v["value"]) if isinstance(v, dict) else float(v) for v in vals]

def gt_for(eid, marker):
    e = eps[eid]
    pre = series(e["pre_context"]["markers"].get(marker, []))
    post = series(e["post_trajectory"]["markers"].get(marker, []))
    if not pre or not post: return None
    a, b = pre[-1], post[-1]
    ch = (b-a)/abs(a) if a else (b-a)
    d = "stable" if abs(ch) < 0.15 else ("rising" if ch>0 else "falling")
    return {"baseline": round(a,4), "post_final": round(b,4), "post_traj": [round(x,4) for x in post],
            "pct_change": round(ch*100,1), "direction": d}

def model_pred(ck, eid, marker):
    p = ck["predictions"].get(eid)
    if not p: return None
    tr = p["trajectories"].get(marker)
    if not tr: return None
    parsed_dir = p.get("directions",{}).get(marker)
    conf = p.get("confidence") or {}
    conf_dir = conf.get("direction") if conf.get("marker")==marker else None
    return {"start": round(float(tr[0]),4), "final": round(float(tr[-1]),4),
            "parsed_dir": parsed_dir, "conf_dir": conf_dir,
            "conf_p": round(float(conf["p"]),3) if conf.get("p") is not None else None}

def mccs_correct(predA, predB, gtA, gtB):
    if not (predA and predB and gtA and gtB): return None
    return bool(np.sign(predA["final"]-predB["final"]) == np.sign(gtA["post_final"]-gtB["post_final"]))

# ── choose 10 golden pairs deliberately spanning failure modes ──────────────
chosen = []
pci_pairs = [p for p in mp["pairs"] if p["contrast"]=="pci_vs_control"]
mv_pairs  = [p for p in mp["pairs"] if p["contrast"]=="multivessel_vs_singlevessel_pci"]

def has_marker(p, m): return m in p.get("scored_markers", [])
def hpi_leak(eid):
    h = (eps[eid].get("clinical_context",{}).get("hpi","") or "").lower()
    return any(t in h for t in LEAK_TERMS)

# 1) the known scale-outlier pair
if "pair_000001" in pairs: chosen.append(("scale-anomaly + known GT", pairs["pair_000001"]))
# 2-3) pairs that score the SODIUM negative control
na = [p for p in pci_pairs if has_marker(p,"Sodium")][:2]
for p in na: chosen.append(("scores Sodium (neg control)", p))
# 4-5) pairs that score CK-MB too
ck = [p for p in pci_pairs if has_marker(p,"Creatine Kinase, MB Isoenzyme") and p not in [c[1] for c in chosen]][:2]
for p in ck: chosen.append(("scores CK-MB", p))
# 6-7) HPI-leakage PCI cases
lk = [p for p in pci_pairs if hpi_leak(p["episode_a_id"]) and p not in [c[1] for c in chosen]][:2]
for p in lk: chosen.append(("HPI leaks post-procedure", p))
# 8) best match-quality, 9) worst match-quality
rest = [p for p in pci_pairs if p not in [c[1] for c in chosen]]
rest.sort(key=lambda p: p["match_quality"]["score"])
if rest: chosen.append(("best match-quality", rest[0]))
if len(rest)>1: chosen.append(("worst match-quality", rest[-1]))
# 10) a multivessel-vs-single contrast
if mv_pairs: chosen.append(("multivessel vs single PCI", mv_pairs[0]))

golden = []
for tag, p in chosen[:10]:
    eidA, eidB = p["episode_a_id"], p["episode_b_id"]
    markers = p.get("scored_markers", ["Troponin T"])
    rec = {
        "pair_id": p["pair_id"], "tag": tag, "contrast": p["contrast"],
        "episode_a": eidA, "episode_b": eidB,
        "intervention_a": p["intervention_a"], "intervention_b": p["intervention_b"],
        "match_quality": p["match_quality"],
        "hpi_leak_a": hpi_leak(eidA), "hpi_leak_b": hpi_leak(eidB),
        "scored_markers": markers,
        "ground_truth": {m: {"A": gt_for(eidA,m), "B": gt_for(eidB,m)} for m in markers},
        "models": {},
        "hpi_a": (eps[eidA].get("clinical_context",{}).get("hpi","") or "")[:1200],
        "comorbidities_a": eps[eidA].get("comorbidities"),
        "comorbidities_b": eps[eidB].get("comorbidities"),
    }
    for name, ck_data in CKPT.items():
        rec["models"][name] = {}
        for m in markers:
            pA = model_pred(ck_data, eidA, m)
            pB = model_pred(ck_data, eidB, m)
            gtA = rec["ground_truth"][m]["A"]; gtB = rec["ground_truth"][m]["B"]
            rec["models"][name][m] = {
                "A": pA, "B": pB,
                "mccs_correct": mccs_correct(pA,pB,gtA,gtB),
                "dir_conf_disagree_A": bool(pA and pA["parsed_dir"] and pA["conf_dir"] and pA["parsed_dir"]!=pA["conf_dir"]),
                "scale_off_A": bool(pA and gtA and gtA["baseline"] and abs(pA["start"]-gtA["baseline"])/abs(gtA["baseline"])>0.5),
            }
    golden.append(rec)

out = V2/"inspection"/"golden_samples.json"
out.write_text(json.dumps({"n": len(golden), "models": list(CKPT.keys()), "samples": golden}, indent=2))
print(f"wrote {out}  ({len(golden)} golden pairs, {len(CKPT)} models)")
for g in golden:
    print(f"  {g['pair_id']}  [{g['tag']}]  {g['intervention_a']} vs {g['intervention_b']}  markers={g['scored_markers']}")
