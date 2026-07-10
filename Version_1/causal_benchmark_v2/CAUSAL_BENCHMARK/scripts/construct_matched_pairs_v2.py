"""
construct_matched_pairs_v2.py

Create matched pairs directly from episodes with measurement alignment enforcement.

Key requirement: Both episodes in a pair MUST have identical shared_markers lists.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging
from itertools import combinations

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

IN_DIR = Path(__file__).parent.parent / "data"
EPISODES_FILE = IN_DIR / "episodes.json"
OUT_FILE = IN_DIR / "matched_pairs.json"


def compute_marker_similarity(ep_a: Dict, ep_b: Dict) -> Optional[float]:
    """
    Compare two episodes for matching.
    Score lower is better.
    Returns None if incompatible.
    """
    # CRITICAL: Must have identical shared markers
    markers_a = set(ep_a.get("shared_markers", []))
    markers_b = set(ep_b.get("shared_markers", []))

    if not markers_a or not markers_b or markers_a != markers_b:
        return None

    # Different interventions required
    int_a = ep_a["intervention"]["type"]
    int_b = ep_b["intervention"]["type"]
    if int_a == int_b:
        return None

    # Score: penalize marker count mismatch (even though we require exact match)
    marker_match_penalty = 0.0 if markers_a == markers_b else 100.0

    # Penalize measurement density differences
    pre_density_diff = 0.0
    post_density_diff = 0.0

    for marker in markers_a:
        pre_a = ep_a["pre_context"]["measurement_density"][marker]
        pre_b = ep_b["pre_context"]["measurement_density"][marker]
        pre_density_diff += abs(pre_a - pre_b)

        post_a = ep_a["post_trajectory"]["measurement_density"][marker]
        post_b = ep_b["post_trajectory"]["measurement_density"][marker]
        post_density_diff += abs(post_a - post_b)

    score = marker_match_penalty + pre_density_diff + post_density_diff

    return score


def main():
    logger.info(f"Loading episodes from {EPISODES_FILE}...")
    with open(EPISODES_FILE, "r") as f:
        data = json.load(f)

    episodes = data["episodes"]
    logger.info(f"Loaded {len(episodes)} episodes")

    # Group by intervention type
    by_intervention = {}
    for ep in episodes:
        int_type = ep["intervention"]["type"]
        if int_type not in by_intervention:
            by_intervention[int_type] = []
        by_intervention[int_type].append(ep)

    logger.info(f"Intervention types: {list(by_intervention.keys())}")
    for int_type, eps in by_intervention.items():
        logger.info(f"  {int_type}: {len(eps)} episodes")

    # Construct pairs
    matched_pairs = []
    pair_id = 0

    # For each pair of intervention types
    int_types = list(by_intervention.keys())
    for i, int_type_a in enumerate(int_types):
        for int_type_b in int_types[i+1:]:
            episodes_a = by_intervention[int_type_a]
            episodes_b = by_intervention[int_type_b]

            logger.info(f"\nMatching {int_type_a} vs {int_type_b}...")

            # Find all compatible pairs
            candidates = []
            for ep_a in episodes_a:
                for ep_b in episodes_b:
                    score = compute_marker_similarity(ep_a, ep_b)
                    if score is not None:
                        candidates.append((score, ep_a, ep_b))

            # Sort by score (lower is better)
            candidates.sort(key=lambda x: x[0])

            # Greedily match without replacement
            matched_a = set()
            matched_b = set()

            for score, ep_a, ep_b in candidates:
                if ep_a["episode_id"] not in matched_a and ep_b["episode_id"] not in matched_b:
                    pair_id += 1
                    matched_a.add(ep_a["episode_id"])
                    matched_b.add(ep_b["episode_id"])

                    # Verify final alignment
                    shared_markers = ep_a["shared_markers"]
                    labs_a = shared_markers
                    labs_b = ep_b["shared_markers"]

                    if set(labs_a) != set(labs_b):
                        logger.warning(f"Alignment check failed! {labs_a} vs {labs_b}")
                        continue

                    pair = {
                        "pair_id": f"pair_{pair_id:06d}",
                        "episode_a_id": ep_a["episode_id"],
                        "episode_b_id": ep_b["episode_id"],
                        "intervention_a": int_type_a,
                        "intervention_b": int_type_b,
                        "shared_markers": shared_markers,
                        "episode_a": {
                            "hadm_id": ep_a["hadm_id"],
                            "intervention": ep_a["intervention"],
                            "pre_measurements": ep_a["pre_context"]["measurement_density"],
                            "post_measurements": ep_a["post_trajectory"]["measurement_density"],
                        },
                        "episode_b": {
                            "hadm_id": ep_b["hadm_id"],
                            "intervention": ep_b["intervention"],
                            "pre_measurements": ep_b["pre_context"]["measurement_density"],
                            "post_measurements": ep_b["post_trajectory"]["measurement_density"],
                        },
                        "match_quality": {
                            "score": round(score, 3),
                            "measurement_alignment": "ALIGNED",
                        }
                    }

                    matched_pairs.append(pair)
                    logger.info(
                        f"  Pair {pair_id}: {ep_a['episode_id']} ({int_type_a}) "
                        f"+ {ep_b['episode_id']} ({int_type_b}) - "
                        f"Markers: {shared_markers}"
                    )

    logger.info(f"\nTotal matched pairs: {len(matched_pairs)}")

    # Save
    output_data = {
        "benchmark": "causal_intervention_matched_pairs_mimic_v2",
        "n_episodes": len(episodes),
        "n_pairs": len(matched_pairs),
        "requirement": "Both episodes must have identical shared_markers (measurement alignment enforced)",
        "pairs": matched_pairs,
    }

    with open(OUT_FILE, "w") as f:
        json.dump(output_data, f, indent=2)

    logger.info(f"✓ Wrote {OUT_FILE}")


if __name__ == "__main__":
    main()
