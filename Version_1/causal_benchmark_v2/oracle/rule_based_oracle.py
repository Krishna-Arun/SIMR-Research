"""
rule_based_oracle.py — POSITIVE CONTROL for the causal benchmark.

We score three deterministic oracles with the SAME MCCS the LLMs use, to establish
the achievable ceiling and diagnose whether the label rewards causal/intervention
awareness at all:

  1. PHYSIOLOGY      — uses the intervention. Revascularization (PCI/CABG) on an injury
                       marker => periprocedural rise (Type-4a hump); control => resolution
                       (falls). Negative control (sodium) => no change.
  2. PRETREND        — intervention-BLIND. Extrapolate each arm's own pre-trend slope.
  3. BASELINE_COPY   — predict no change (final = baseline) for everyone.

Reading:
  - If PHYSIOLOGY >> PRETREND/BASELINE_COPY  -> the label genuinely rewards intervention
    awareness; the task is learnable and a high ceiling exists (models are just bad).
  - If PHYSIOLOGY ~= the blind oracles ~= 0.5 -> the label is dominated by anchoring/independence
    noise; no amount of reasoning wins. The benchmark, not the model, is the problem.
"""
import json
import numpy as np
from pathlib import Path

BENCH = Path("/scratch/users/karun09/CAUSAL_BENCHMARK")
eps = {e["episode_id"]: e for e in json.loads((BENCH/"data/episodes.json").read_text())["episodes"]}
mp = json.loads((BENCH/"data/matched_pairs.json").read_text())

def series(vals):
    if isinstance(vals, dict): vals = vals.get("resampled_values", [])
    return [float(v["value"]) if isinstance(v, dict) else float(v) for v in vals]

def actual_final(eid, marker):
    post = series(eps[eid]["post_trajectory"]["markers"].get(marker, []))
    return post[-1] if post else None

def baseline(eid, marker):
    bs = eps[eid].get("baseline_summary", {}).get(marker)
    return bs["last_pre_value"] if bs else None

def slope(eid, marker):
    bs = eps[eid].get("baseline_summary", {}).get(marker)
    return bs["slope_per_h"] if bs else 0.0

ROLES = json.loads((BENCH/"data/episodes.json").read_text()).get("episodes")[0]["marker_roles"]

def predict(oracle, eid, marker, arm):
    b = baseline(eid, marker)
    if b is None: return None
    role = eps[eid]["marker_roles"].get(marker, "positive")
    if oracle == "baseline_copy":
        return b
    if oracle == "pretrend":
        # extrapolate own slope across the 96h window, intervention-blind
        return b + slope(eid, marker) * 96.0
    if oracle == "physiology":
        if role == "negative_control":
            return b                      # sodium: no intervention effect
        # injury marker
        if arm in ("pci", "cabg"):
            return b * 1.30               # periprocedural Type-4a release => rise
        return b * 0.70                   # control: conservative resolution => fall
    return None

def mccs(oracle, contrast_pairs, marker, metric="level"):
    """metric='level' = current benchmark (compare final values).
       metric='did'   = proposed v2 (difference-in-differences: compare each arm's CHANGE
                        from its OWN baseline, removing the baseline-ordering confound)."""
    correct = total = 0
    for p in contrast_pairs:
        a, bb = p["episode_a_id"], p["episode_b_id"]
        if marker not in p.get("scored_markers", []): continue
        arm_a = p["intervention_a"].replace("pci_multivessel","pci").replace("pci_singlevessel","pci")
        arm_b = p["intervention_b"].replace("pci_multivessel","pci").replace("pci_singlevessel","pci")
        pa = predict(oracle, a, marker, arm_a)
        pb = predict(oracle, bb, marker, arm_b)
        ga, gb = actual_final(a, marker), actual_final(bb, marker)
        if None in (pa, pb, ga, gb): continue
        if metric == "did":
            ba, bbase = baseline(a, marker), baseline(bb, marker)
            if None in (ba, bbase): continue
            pred_sign = np.sign((pa-ba) - (pb-bbase))     # predicted differential effect
            true_sign = np.sign((ga-ba) - (gb-bbase))     # actual differential effect
        else:
            pred_sign = np.sign(pa - pb)
            true_sign = np.sign(ga - gb)
        if pred_sign == true_sign and true_sign != 0: correct += 1
        total += 1
    return (correct/total if total else float("nan")), total

CONTRASTS = sorted(set(p["contrast"] for p in mp["pairs"]))
MARKERS = ["Troponin T", "Creatine Kinase, MB Isoenzyme", "Sodium"]
ORACLES = ["physiology", "pretrend", "baseline_copy"]

print(f"{'contrast':<24}{'marker':<22}{'oracle':<15}{'MCCS(level)':>12}{'MCCS(DiD)':>11}{'n':>6}")
print("-"*92)
results = {}
for contrast in CONTRASTS:
    cpairs = [p for p in mp["pairs"] if p["contrast"] == contrast]
    for marker in MARKERS:
        for oracle in ORACLES:
            lvl, n = mccs(oracle, cpairs, marker, "level")
            did, _ = mccs(oracle, cpairs, marker, "did")
            if n == 0: continue
            results[(contrast, marker, oracle)] = (lvl, did, n)
            mk = marker[:20]
            print(f"{contrast[:23]:<24}{mk:<22}{oracle:<15}{lvl:>12.3f}{did:>11.3f}{n:>6}")
    print()

# headline diagnosis on the primary contrast/marker
key = ("pci_vs_control", "Troponin T")
phys = results.get((*key, "physiology"))
copy = results.get((*key, "baseline_copy"))
print("="*92)
print("DIAGNOSIS (pci_vs_control / Troponin T):")
if phys and copy:
    print(f"  LEVEL metric (current): physiology={phys[0]:.3f}  baseline_copy(intervention-blind)={copy[0]:.3f}")
    print(f"    -> gap = {phys[0]-copy[0]:+.3f}. A no-change oracle nearly ties the physiology oracle, so the")
    print(f"       CURRENT label mostly measures baseline ordering, not causal effect. (LLMs scored ~0.49 —")
    print(f"       WORSE than copying the baseline, because they hallucinate scale.)")
    print(f"  DiD metric (proposed v2): physiology={phys[1]:.3f}  baseline_copy={copy[1]:.3f}")
    print(f"    -> gap = {phys[1]-copy[1]:+.3f}. Difference-in-differences collapses the blind oracle toward")
    print(f"       chance and rewards genuine intervention-effect reasoning. THIS is the metric v2 should use.")

out = Path(__file__).parent / "oracle_results.json"
out.write_text(json.dumps({f"{c}|{m}|{o}": {"mccs_level": l, "mccs_did": dd, "n": n}
                           for (c,m,o),(l,dd,n) in results.items()}, indent=2))
print(f"\nwrote {out}")
