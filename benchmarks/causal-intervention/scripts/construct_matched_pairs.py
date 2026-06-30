"""
construct_matched_pairs.py

Construct matched pairs of episodes for causal evaluation.

Matching criteria:
1. Same severity bin (e.g., both "moderate")
2. Similar pre-trend (direction match, slope magnitude <20% diff)
3. Different interventions
4. Similar comorbidity profile

Output: matched_pairs.json with (episode_a, episode_b, intervention_pair)
"""

import json
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import logging
from itertools import combinations

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent.parent.parent
IN_DIR = Path(__file__).parent.parent / "data"
FEATURES_FILE = IN_DIR / "encoded_features.json"
EPISODES_FILE = IN_DIR / "episodes.json"
OUT_DIR = IN_DIR
OUT_FILE = OUT_DIR / "matched_pairs.json"

# ── Matching parameters ───────────────────────────────────────────────────────
MAX_SLOPE_DIFF = 0.20  # Allow 20% difference in pre-trend slope
MAX_COMORBIDITY_DISTANCE = 2  # Hamming distance on comorbidity vector
PREFER_SAME_HOSPITAL_WINDOW = True  # Within 30 days


def euclidean_distance(v1: Dict[str, int], v2: Dict[str, int]) -> float:
    """Compute Euclidean distance between two comorbidity vectors."""
    keys = set(v1.keys()) | set(v2.keys())
    diff_sq = sum((v1.get(k, 0) - v2.get(k, 0)) ** 2 for k in keys)
    return np.sqrt(diff_sq)


def hamming_distance(v1: Dict[str, int], v2: Dict[str, int]) -> int:
    """Compute Hamming distance (mismatches) between two binary vectors."""
    keys = set(v1.keys()) | set(v2.keys())
    return sum(1 for k in keys if v1.get(k, 0) != v2.get(k, 0))


def standardized_mean_diff(v1: float, v2: float, std1: float, std2: float) -> float:
    """
    Compute Standardized Mean Difference (SMD).
    SMD < 0.1 indicates good covariate balance.
    """
    if std1 == 0 and std2 == 0:
        return 0.0
    pooled_std = np.sqrt((std1 ** 2 + std2 ** 2) / 2.0)
    if pooled_std == 0:
        return 0.0
    return abs(v1 - v2) / pooled_std


def pre_trend_compatible(trend1: Dict, trend2: Dict, lab: str) -> bool:
    """
    Check if two pre-trend features are compatible for matching.
    """
    if lab not in trend1 or lab not in trend2:
        return True

    t1 = trend1[lab]
    t2 = trend2[lab]

    # Must match direction
    if t1["direction"] != t2["direction"]:
        return False

    # Slope magnitude must be within 20%
    if t1["slope"] == 0 and t2["slope"] == 0:
        return True

    max_slope = max(abs(t1["slope"]), abs(t2["slope"]))
    if max_slope < 0.001:
        return True

    diff = abs(t1["slope"] - t2["slope"]) / max_slope
    return diff <= MAX_SLOPE_DIFF


def compute_match_score(feat1: Dict, feat2: Dict, lab_names: List[str]) -> Optional[float]:
    """
    Compute match score between two encoded feature sets.
    Lower score = better match.
    Returns None if incompatible.
    """
    # Check severity bin match
    if feat1["severity"]["severity_bin"] != feat2["severity"]["severity_bin"]:
        return None

    # Check intervention types differ
    int1 = feat1["intervention"]["type"]
    int2 = feat2["intervention"]["type"]
    if int1 == int2:
        return None

    # Check pre-trend compatibility for key labs
    for lab in ["Troponin I", "Creatinine", "BNP"]:
        if not pre_trend_compatible(feat1["pre_trend"], feat2["pre_trend"], lab):
            return None

    # Compute composite score
    score = 0.0

    # Comorbidity distance (lower is better)
    comorbid_dist = hamming_distance(feat1["comorbidities"], feat2["comorbidities"])
    score += comorbid_dist * 10.0  # Weight: 10 points per mismatch

    # Severity score proximity
    sev_diff = abs(feat1["severity"]["sofa_score"] - feat2["severity"]["sofa_score"])
    score += sev_diff * 1.0  # Weight: 1 point per SOFA point difference

    # Pre-trend slope difference (normalized)
    for lab in feat1["pre_trend"]:
        if lab in feat2["pre_trend"]:
            s1 = feat1["pre_trend"][lab]["slope"]
            s2 = feat2["pre_trend"][lab]["slope"]
            if abs(s1) + abs(s2) > 0.001:
                max_s = max(abs(s1), abs(s2))
                diff = abs(s1 - s2) / max_s
                score += diff * 5.0

    return score


def main():
    logger.info(f"Loading encoded features from {FEATURES_FILE}...")
    with open(FEATURES_FILE, "r") as f:
        features_manifest = json.load(f)

    features_list = features_manifest["features"]
    logger.info(f"Loaded {len(features_list)} encoded features")

    logger.info(f"Loading episodes from {EPISODES_FILE}...")
    with open(EPISODES_FILE, "r") as f:
        episodes_manifest = json.load(f)

    episodes_by_id = {ep["episode_id"]: ep for ep in episodes_manifest["episodes"]}
    logger.info(f"Loaded {len(episodes_by_id)} episodes")

    # Group features by severity bin and intervention type
    by_severity_and_int = {}
    for feat in features_list:
        sev_bin = feat["severity"]["severity_bin"]
        int_type = feat["intervention"]["type"]
        key = (sev_bin, int_type)

        if key not in by_severity_and_int:
            by_severity_and_int[key] = []

        by_severity_and_int[key].append(feat)

    logger.info(f"Severity-intervention groups: {len(by_severity_and_int)}")
    for key, group in by_severity_and_int.items():
        logger.info(f"  {key}: {len(group)} episodes")

    # Construct pairs
    matched_pairs = []
    pair_id = 0

    # For each severity bin
    for sev_bin in ["mild", "moderate", "moderately_severe", "severe"]:
        candidates_by_int = {}
        for (sb, int_type), episodes in by_severity_and_int.items():
            if sb == sev_bin:
                if int_type not in candidates_by_int:
                    candidates_by_int[int_type] = []
                candidates_by_int[int_type].extend(episodes)

        if not candidates_by_int:
            continue

        logger.info(f"Matching for severity bin: {sev_bin} ({len(candidates_by_int)} intervention types)")

        # For each intervention type, find matches in other types
        int_types = list(candidates_by_int.keys())
        for i, int_type_a in enumerate(int_types):
            for int_type_b in int_types[i+1:]:
                episodes_a = candidates_by_int[int_type_a]
                episodes_b = candidates_by_int[int_type_b]

                # Match: greedily find best pairs without replacement
                matched_a = set()
                matched_b = set()

                candidates = []
                for feat_a in episodes_a:
                    for feat_b in episodes_b:
                        if feat_a["episode_id"] in matched_a or feat_b["episode_id"] in matched_b:
                            continue

                        score = compute_match_score(feat_a, feat_b, ["Troponin I", "Creatinine", "BNP"])
                        if score is not None:
                            candidates.append((score, feat_a, feat_b))

                # Sort by score and greedily match
                candidates.sort(key=lambda x: x[0])

                for score, feat_a, feat_b in candidates:
                    if feat_a["episode_id"] not in matched_a and feat_b["episode_id"] not in matched_b:
                        pair_id += 1
                        matched_a.add(feat_a["episode_id"])
                        matched_b.add(feat_b["episode_id"])

                        # Get full episode data
                        ep_a = episodes_by_id[feat_a["episode_id"]]
                        ep_b = episodes_by_id[feat_b["episode_id"]]

                        # Compute SMD for balance check
                        smd_sofa = standardized_mean_diff(
                            feat_a["severity"]["sofa_score"],
                            feat_b["severity"]["sofa_score"],
                            0.5,  # Assume std dev of 0.5 for simplicity
                            0.5,
                        )

                        pair = {
                            "pair_id": f"pair_{pair_id:06d}",
                            "episode_a_id": feat_a["episode_id"],
                            "episode_b_id": feat_b["episode_id"],
                            "intervention_a": feat_a["intervention"]["type"],
                            "intervention_b": feat_b["intervention"]["type"],
                            "severity_match": {
                                "bin": sev_bin,
                                "episode_a_score": feat_a["severity"]["sofa_score"],
                                "episode_b_score": feat_b["severity"]["sofa_score"],
                                "smd": round(smd_sofa, 3),
                            },
                            "match_quality": {
                                "score": round(score, 3),
                                "comorbidity_distance": hamming_distance(
                                    feat_a["comorbidities"], feat_b["comorbidities"]
                                ),
                            },
                            "episode_a": {
                                "patient_id": ep_a["patient_id"],
                                "intervention": ep_a["intervention"],
                                "demographics": ep_a["demographics"],
                            },
                            "episode_b": {
                                "patient_id": ep_b["patient_id"],
                                "intervention": ep_b["intervention"],
                                "demographics": ep_b["demographics"],
                            },
                            "y_a_labs": list(ep_a["post_trajectory"].keys()),
                            "y_b_labs": list(ep_b["post_trajectory"].keys()),
                        }
                        matched_pairs.append(pair)

    logger.info(f"\nTotal matched pairs: {len(matched_pairs)}")

    # Balance check
    good_balance = sum(1 for p in matched_pairs if p["severity_match"]["smd"] < 0.1)
    logger.info(f"Pairs with good balance (SMD < 0.1): {good_balance}/{len(matched_pairs)}")

    # Intervention pair distribution
    int_pair_dist = {}
    for pair in matched_pairs:
        key = tuple(sorted([pair["intervention_a"], pair["intervention_b"]]))
        int_pair_dist[str(key)] = int_pair_dist.get(str(key), 0) + 1
    logger.info(f"Intervention pair distribution: {int_pair_dist}")

    # Save
    output_manifest = {
        "name": "causal_intervention_matched_pairs_v1",
        "n_pairs": len(matched_pairs),
        "balance_check": {
            "n_good_balance": good_balance,
            "threshold": 0.1,
        },
        "intervention_pairs": int_pair_dist,
        "pairs": matched_pairs,
    }

    with open(OUT_FILE, "w") as f:
        json.dump(output_manifest, f, indent=2)

    logger.info(f"Wrote {OUT_FILE}")


if __name__ == "__main__":
    main()
