"""
build_matched_pairs.py  —  1:k matched pairs for the two-arm causal benchmark.

Each PCI (treated) episode is matched to its K most-similar control episodes.
Matching is on the PRIMARY marker (troponin), which every episode has by construction.
Each pair records `scored_markers` = the markers BOTH episodes have (always troponin,
plus CK-MB / Sodium when both share them); per-marker metrics use that subset.

Compatibility (hard constraint):
  - different intervention arm (pci vs control)
Similarity (soft, lower=better):
  - comorbidity Hamming distance
  - |baseline troponin level| difference (relative)
  - pre-trend direction agreement on troponin

Controls are matched WITHOUT replacement within a treated patient's K slots, and
with limited global reuse (a control may serve a few treated units, capped by
MAX_CONTROL_REUSE) so the 1:K design stays balanced. This is a standard 1:K
matched-cohort construction.

Output: data/matched_pairs.json
"""

import json
import logging
from pathlib import Path
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

BENCH = Path(__file__).parent.parent
EPISODES = BENCH / "data" / "episodes.json"
OUT = BENCH / "data" / "matched_pairs.json"

K = 3                     # controls per treated unit (1:3 matched design -> ~500+ pairs)
MAX_CONTROL_REUSE = 3     # a control episode may appear in at most this many pairs
COMORBID_MAX = 4          # reject match if comorbidity Hamming distance exceeds this


def hamming(a, b):
    keys = set(a) | set(b)
    return sum(1 for k in keys if a.get(k, 0) != b.get(k, 0))


def baseline_level(ep, marker):
    return ep["baseline_summary"][marker]["last_pre_value"]


def baseline_dir(ep, marker):
    return ep["baseline_summary"][marker]["direction"]


def match_score(treated, control, marker):
    """Lower = better. None if incompatible. Matches on the primary marker (troponin)."""
    if treated["primary_marker"] != control["primary_marker"]:
        return None

    cdist = hamming(treated["comorbidities"], control["comorbidities"])
    if cdist > COMORBID_MAX:
        return None

    # relative baseline difference on the primary marker
    bt = baseline_level(treated, marker)
    bc = baseline_level(control, marker)
    denom = max(abs(bt), abs(bc), 1e-6)
    base_diff = abs(bt - bc) / denom

    dir_penalty = 0.0 if baseline_dir(treated, marker) == baseline_dir(control, marker) else 1.0

    return cdist * 1.0 + base_diff * 2.0 + dir_penalty * 1.5


# Each contrast selects arm A and arm B episodes via a (field, value) selector:
#   ("type", X)   -> episodes with intervention.type == X
#   ("vessel", X) -> PCI episodes whose pci_vessels == X  (treatment-vs-treatment within PCI)
# Treatment-vs-control uses the big control pool (K=3); treatment-vs-treatment K=1-2.
# A contrast is built only if BOTH arms have >= MIN_ARM episodes (else skipped).
CONTRASTS = [
    {"label": "pci_vs_control",                  "a": ("type", "pci"),     "b": ("type", "control"), "k": 3},
    {"label": "cabg_vs_control",                 "a": ("type", "cabg"),    "b": ("type", "control"), "k": 3},
    {"label": "pci_vs_cabg",                     "a": ("type", "pci"),     "b": ("type", "cabg"),    "k": 1},
    {"label": "multivessel_vs_singlevessel_pci", "a": ("vessel", "multi"), "b": ("vessel", "single"),"k": 2},
]
MIN_ARM = 30


def _select(episodes, sel):
    field, val = sel
    if field == "type":
        return [e for e in episodes if e["intervention"]["type"] == val], val
    if field == "vessel":
        return ([e for e in episodes if e["intervention"]["type"] == "pci" and e.get("pci_vessels") == val],
                f"pci_{val}vessel")
    return [], val


def build_contrast(A, B, k, label, a_name, b_name, pid_start):
    """Match each arm-A episode to up to k arm-B episodes. Returns (pairs, stats)."""
    reuse = defaultdict(int)
    pairs = []
    pid = pid_start
    scored_marker_counts = defaultdict(int)
    n_unmatched = 0
    for t in A:
        marker = t["primary_marker"]
        scored = []
        for c in B:
            if reuse[c["episode_id"]] >= MAX_CONTROL_REUSE:
                continue
            s = match_score(t, c, marker)
            if s is not None:
                scored.append((s, c))
        scored.sort(key=lambda x: x[0])
        chosen = scored[:k]
        if not chosen:
            n_unmatched += 1
            continue
        for s, c in chosen:
            pid += 1
            reuse[c["episode_id"]] += 1
            scored_markers = sorted(set(t["markers_present"]) & set(c["markers_present"]))
            for m in scored_markers:
                scored_marker_counts[m] += 1
            pairs.append({
                "pair_id": f"pair_{pid:06d}",
                "contrast": label,
                "episode_a_id": t["episode_id"],
                "episode_b_id": c["episode_id"],
                "intervention_a": a_name,
                "intervention_b": b_name,
                "primary_marker": marker,
                "scored_markers": scored_markers,
                "match_quality": {
                    "score": round(s, 3),
                    "comorbidity_distance": hamming(t["comorbidities"], c["comorbidities"]),
                    "baseline_a": round(baseline_level(t, marker), 4),
                    "baseline_b": round(baseline_level(c, marker), 4),
                    "dir_a": baseline_dir(t, marker),
                    "dir_b": baseline_dir(c, marker),
                },
            })
    stats = {"label": label, "n_pairs": len(pairs), "k": k,
             "n_a": len(A), "n_b": len(B), "scored_marker_pairs": dict(scored_marker_counts)}
    return pairs, stats


def main():
    data = json.loads(EPISODES.read_text())
    episodes = data["episodes"]
    from collections import Counter
    types = Counter(e["intervention"]["type"] for e in episodes)
    vessels = Counter(e.get("pci_vessels") for e in episodes if e["intervention"]["type"] == "pci")
    log.info("Arm sizes by type: " + dict(types).__repr__() + " | PCI vessels: " + dict(vessels).__repr__())

    all_pairs = []
    contrast_summaries = []
    skipped = []
    for spec in CONTRASTS:
        A, a_name = _select(episodes, spec["a"])
        B, b_name = _select(episodes, spec["b"])
        label, k = spec["label"], spec["k"]
        if len(A) < MIN_ARM or len(B) < MIN_ARM:
            skipped.append({"label": label, "n_a": len(A), "n_b": len(B), "reason": f"arm < MIN_ARM={MIN_ARM}"})
            log.warning(f"SKIP contrast {label}: arm sizes a={len(A)} b={len(B)} (< {MIN_ARM}) — underpowered")
            continue
        pairs, stats = build_contrast(A, B, k, label, a_name, b_name, len(all_pairs))
        all_pairs.extend(pairs)
        contrast_summaries.append(stats)
        log.info(f"Contrast {label}: {stats['n_pairs']} pairs ({a_name} a={stats['n_a']} vs {b_name} b={stats['n_b']}, 1:{k}); "
                 f"scorable markers {stats['scored_marker_pairs']}")

    OUT.write_text(json.dumps({
        "benchmark": "causal_intervention_matched_pairs_multicontrast_v6",
        "design": "per-contrast 1:K matching; treatment-vs-control and treatment-vs-treatment; per-marker scoring",
        "max_control_reuse": MAX_CONTROL_REUSE,
        "n_pairs": len(all_pairs),
        "contrasts": contrast_summaries,
        "skipped_contrasts": skipped,
        "pairs": all_pairs,
    }, indent=2))
    log.info(f"Total pairs: {len(all_pairs)} across {len(contrast_summaries)} contrast(s); skipped {len(skipped)}")
    log.info(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
