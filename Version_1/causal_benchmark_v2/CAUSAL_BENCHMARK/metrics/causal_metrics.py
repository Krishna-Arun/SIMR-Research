"""
causal_metrics.py

Implement core causal evaluation metrics:
- MCCS: Matched Counterfactual Consistency Score
- TCAE: Temporal Causal Alignment Error
- IEC: Intervention Effect Calibration
- Pre-trend invariance test
- Shape similarity (auxiliary)
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
from scipy.stats import wasserstein_distance
from scipy.spatial.distance import euclidean
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CausalMetrics:
    """Compute causal evaluation metrics for trajectory predictions."""

    def __init__(self):
        """Initialize metrics container."""
        pass

    @staticmethod
    def mccs(predictions: Dict[str, np.ndarray],
            outcomes: Dict[str, np.ndarray],
            pairs: List[Dict]) -> Tuple[float, Dict]:
        """
        Matched Counterfactual Consistency Score.

        For each matched pair:
          P(sign(pred_a - pred_b) == sign(actual_a - actual_b))

        Args:
            predictions: {episode_id: predicted_trajectory}
            outcomes: {episode_id: actual_trajectory}
            pairs: List of matched pairs with episode_a_id, episode_b_id

        Returns:
            mccs_score (0.0 to 1.0), per_pair_results (Dict)
        """
        if not pairs:
            return 0.5, {}

        correct_count = 0
        total_count = 0
        per_pair_results = {}

        for pair in pairs:
            ep_a_id = pair["episode_a_id"]
            ep_b_id = pair["episode_b_id"]

            # Check if we have predictions and outcomes for both
            if ep_a_id not in predictions or ep_b_id not in predictions:
                continue
            if ep_a_id not in outcomes or ep_b_id not in outcomes:
                continue

            pred_a = predictions[ep_a_id]
            pred_b = predictions[ep_b_id]
            actual_a = outcomes[ep_a_id]
            actual_b = outcomes[ep_b_id]

            # Compute final trajectory values (end of post-window)
            pred_diff = float(pred_a[-1] - pred_b[-1])
            actual_diff = float(actual_a[-1] - actual_b[-1])

            pred_sign = np.sign(pred_diff)
            actual_sign = np.sign(actual_diff)

            # Match if signs agree
            match = (pred_sign == actual_sign)
            correct_count += int(match)
            total_count += 1

            per_pair_results[pair["pair_id"]] = {
                "correct": bool(match),
                "pred_diff": float(pred_diff),
                "actual_diff": float(actual_diff),
                "pred_sign": int(pred_sign),
                "actual_sign": int(actual_sign),
            }

        if total_count == 0:
            return 0.5, {}

        mccs = correct_count / total_count
        return mccs, per_pair_results

    @staticmethod
    def tcae(predictions: Dict[str, np.ndarray],
            outcomes: Dict[str, np.ndarray],
            pairs: List[Dict],
            window_hours: int = 48) -> Tuple[float, Dict]:
        """
        Temporal Causal Alignment Error (TCAE).

        Measures alignment of inflection points (response timing).

        Args:
            predictions: {episode_id: predicted_trajectory}
            outcomes: {episode_id: actual_trajectory}
            pairs: Matched pairs
            window_hours: Post-intervention window length

        Returns:
            tcae_hours (float), per_pair_results (Dict)
        """
        if not pairs:
            return np.inf, {}

        errors = []
        per_pair_results = {}

        for pair in pairs:
            ep_a_id = pair["episode_a_id"]
            ep_b_id = pair["episode_b_id"]

            if ep_a_id not in predictions or ep_b_id not in predictions:
                continue
            if ep_a_id not in outcomes or ep_b_id not in outcomes:
                continue

            pred_a = predictions[ep_a_id]
            actual_a = outcomes[ep_a_id]

            # Find inflection points (max second derivative)
            if len(pred_a) > 2 and len(actual_a) > 2:
                pred_inflect = CausalMetrics._find_inflection(pred_a)
                actual_inflect = CausalMetrics._find_inflection(actual_a)

                # Convert index to hours
                pred_hours = (pred_inflect / len(pred_a)) * window_hours if len(pred_a) > 0 else 0
                actual_hours = (actual_inflect / len(actual_a)) * window_hours if len(actual_a) > 0 else 0

                error_hours = abs(pred_hours - actual_hours)
                errors.append(error_hours)

                per_pair_results[pair["pair_id"]] = {
                    "pred_inflection_hours": float(pred_hours),
                    "actual_inflection_hours": float(actual_hours),
                    "error_hours": float(error_hours),
                }

        if not errors:
            return np.inf, {}

        tcae = float(np.median(errors))
        return tcae, per_pair_results

    @staticmethod
    def _find_inflection(trajectory: np.ndarray) -> int:
        """
        Find inflection point as index of max absolute second derivative.
        """
        if len(trajectory) < 3:
            return len(trajectory) // 2

        first_deriv = np.diff(trajectory)
        second_deriv = np.diff(first_deriv)

        if len(second_deriv) == 0:
            return len(trajectory) // 2

        inflection_idx = int(np.argmax(np.abs(second_deriv))) + 1
        return min(inflection_idx, len(trajectory) - 1)

    @staticmethod
    def iec(predictions: Dict[str, np.ndarray],
           outcomes: Dict[str, np.ndarray],
           pairs: List[Dict]) -> Tuple[float, Dict]:
        """
        Intervention Effect Calibration (IEC).

        Scale-free relative calibration error on the final post-window value of
        the treated (arm A) trajectory. Because different pairs are scored on
        different markers (troponin ~0.05 vs NTproBNP ~thousands), a raw absolute
        error is dominated by large-magnitude markers and is not comparable across
        pairs. We therefore use a bounded symmetric relative error:

            e = |pred_final - actual_final| / (|pred_final| + |actual_final| + eps)

        which lies in [0, 1): 0 = perfectly calibrated magnitude, ->1 = maximally
        miscalibrated. IEC is the mean of e over scored pairs.

        Args:
            predictions: {episode_id: predicted_trajectory}
            outcomes: {episode_id: actual_trajectory}
            pairs: Matched pairs

        Returns:
            iec_score (float in [0,1)), per_pair_results (Dict)
        """
        if not pairs:
            return np.inf, {}

        eps = 1e-6
        rel_errors = []
        per_pair_results = {}

        for pair in pairs:
            ep_a_id = pair["episode_a_id"]
            ep_b_id = pair["episode_b_id"]

            if ep_a_id not in predictions or ep_b_id not in predictions:
                continue
            if ep_a_id not in outcomes or ep_b_id not in outcomes:
                continue

            pred_final = float(predictions[ep_a_id][-1])
            actual_final = float(outcomes[ep_a_id][-1])

            abs_err = abs(pred_final - actual_final)
            rel_err = abs_err / (abs(pred_final) + abs(actual_final) + eps)
            rel_errors.append(rel_err)

            per_pair_results[pair["pair_id"]] = {
                "relative_error": float(rel_err),
                "abs_error": float(abs_err),
                "pred_final": pred_final,
                "actual_final": actual_final,
            }

        if not rel_errors:
            return np.inf, {}

        iec = float(np.mean(rel_errors))
        return iec, per_pair_results

    @staticmethod
    def pre_trend_invariance(predictions: Dict[str, np.ndarray],
                            outcomes: Dict[str, np.ndarray],
                            pairs: List[Dict],
                            features: Dict) -> Tuple[float, Dict]:
        """
        Pre-trend invariance test.

        Shuffle interventions within same severity bin. If model is causal,
        MCCS should drop significantly.

        Args:
            predictions: {episode_id: predicted_trajectory}
            outcomes: {episode_id: actual_trajectory}
            pairs: Matched pairs with severity info
            features: {episode_id: encoded_features}

        Returns:
            delta_mccs (float), test_results (Dict)
        """
        # Compute real MCCS
        mccs_real, _ = CausalMetrics.mccs(predictions, outcomes, pairs)

        # Shuffle interventions within severity bins
        pairs_shuffled = []
        for pair in pairs:
            # Swap episode_a_id and episode_b_id
            shuffled_pair = pair.copy()
            shuffled_pair["episode_a_id"], shuffled_pair["episode_b_id"] = \
                pair["episode_b_id"], pair["episode_a_id"]
            shuffled_pair["intervention_a"], shuffled_pair["intervention_b"] = \
                pair["intervention_b"], pair["intervention_a"]
            pairs_shuffled.append(shuffled_pair)

        mccs_shuffled, _ = CausalMetrics.mccs(predictions, outcomes, pairs_shuffled)

        # Delta should be negative (shuffled should perform worse)
        delta_mccs = mccs_shuffled - mccs_real

        return delta_mccs, {
            "mccs_real": float(mccs_real),
            "mccs_shuffled": float(mccs_shuffled),
            "delta_mccs": float(delta_mccs),
            "test_passed": delta_mccs < -0.10,  # Should drop by 10+ points
        }

    @staticmethod
    def shape_similarity(predictions: Dict[str, np.ndarray],
                        outcomes: Dict[str, np.ndarray],
                        pairs: List[Dict]) -> Tuple[float, Dict]:
        """
        Shape similarity using Dynamic Time Warping (DTW) distance.

        Auxiliary metric (lower weight in final scoring).

        Args:
            predictions: {episode_id: predicted_trajectory}
            outcomes: {episode_id: actual_trajectory}
            pairs: Matched pairs

        Returns:
            dtw_distance (float), per_pair_results (Dict)
        """
        dtw_distances = []
        per_pair_results = {}

        for pair in pairs:
            ep_a_id = pair["episode_a_id"]

            if ep_a_id not in predictions or ep_a_id not in outcomes:
                continue

            pred = predictions[ep_a_id]
            actual = outcomes[ep_a_id]

            # Simple DTW-like distance (L2 on normalized trajectories)
            pred_norm = (pred - np.mean(pred)) / (np.std(pred) + 1e-6)
            actual_norm = (actual - np.mean(actual)) / (np.std(actual) + 1e-6)

            # Align lengths
            max_len = max(len(pred_norm), len(actual_norm))
            pred_padded = np.pad(pred_norm, (0, max_len - len(pred_norm)))
            actual_padded = np.pad(actual_norm, (0, max_len - len(actual_norm)))

            # L2 distance
            dist = float(np.linalg.norm(pred_padded - actual_padded))
            dtw_distances.append(dist)

            per_pair_results[pair["pair_id"]] = {
                "shape_distance": dist,
            }

        if not dtw_distances:
            return np.inf, {}

        shape_sim = float(np.mean(dtw_distances))
        return shape_sim, per_pair_results

    @staticmethod
    def nonstable_rate(directions: Dict[str, str], episode_ids) -> Tuple[float, int]:
        """Fraction of the given (treated) episodes whose predicted direction != 'stable'.
        For a POSITIVE marker this should be high (model expects an effect); for the
        NEGATIVE CONTROL it should be LOW (a good model invents no effect)."""
        ds = [directions.get(e) for e in episode_ids if e in directions]
        ds = [d for d in ds if d is not None]
        if not ds:
            return float("nan"), 0
        rate = sum(1 for d in ds if str(d).lower() != "stable") / len(ds)
        return rate, len(ds)

    @staticmethod
    def intervention_sensitivity(predictions: Dict, predictions_flipped: Dict, marker: str) -> Dict:
        """Causal-sensitivity test: hold the patient fixed, FLIP the intervention in the prompt,
        and measure how much the prediction changes. A causal model changes a lot; a
        pattern-matcher barely moves. (Replaces the inert A/B-swap invariance test.)
          mean_rel_change   — mean relative change in the marker's final value when flipped
          direction_flip_rate — fraction of episodes whose predicted direction changed
        Higher = the model genuinely conditions on the intervention."""
        rels, dirflip, n = [], 0, 0
        for eid, real in predictions.items():
            fl = predictions_flipped.get(eid)
            if not fl:
                continue
            rt = real.get("trajectories", {}).get(marker)
            ft = fl.get("trajectories", {}).get(marker)
            if rt is None or ft is None or len(rt) == 0 or len(ft) == 0:
                continue
            rf, ff = float(rt[-1]), float(ft[-1])
            rels.append(abs(rf - ff) / (abs(rf) + abs(ff) + 1e-6))
            if real.get("directions", {}).get(marker) != fl.get("directions", {}).get(marker):
                dirflip += 1
            n += 1
        if n == 0:
            return {"n": 0}
        return {"n": n,
                "mean_rel_change": round(float(np.mean(rels)), 4),
                "direction_flip_rate": round(dirflip / n, 4)}

    @staticmethod
    def calibration(pred_dirs: Dict[str, str], confidences: Dict[str, float],
                    actual_dirs: Dict[str, str], n_bins: int = 5) -> Dict:
        """Calibration of the primary-marker direction prediction against logit confidence.
        Uses the model's OWN probability (from logits) — not a self-reported number."""
        items = []
        for e, pd_ in pred_dirs.items():
            if e in actual_dirs and confidences.get(e) is not None:
                items.append((float(confidences[e]), int(str(pd_).lower() == str(actual_dirs[e]).lower())))
        if not items:
            return {"n": 0}
        conf = np.array([c for c, _ in items])
        corr = np.array([c for _, c in items])
        bins = np.linspace(0, 1, n_bins + 1)
        ece = 0.0
        rel = []
        for i in range(n_bins):
            hi = conf <= bins[i + 1] if i == n_bins - 1 else conf < bins[i + 1]
            m = (conf >= bins[i]) & hi
            if m.sum() == 0:
                continue
            acc, cf, w = corr[m].mean(), conf[m].mean(), m.mean()
            ece += w * abs(acc - cf)
            rel.append({"bin": [round(float(bins[i]), 2), round(float(bins[i + 1]), 2)],
                        "n": int(m.sum()), "mean_conf": round(float(cf), 3), "accuracy": round(float(acc), 3)})
        return {"n": len(items), "ece": round(float(ece), 4),
                "overall_accuracy": round(float(corr.mean()), 4),
                "overall_confidence": round(float(conf.mean()), 4),
                "reliability": rel}

    @staticmethod
    def compute_all(predictions: Dict[str, np.ndarray],
                   outcomes: Dict[str, np.ndarray],
                   pairs: List[Dict],
                   features: Optional[Dict] = None) -> Dict:
        """
        Compute all metrics in one call.

        Returns:
            {
                "mccs": float,
                "tcae_hours": float,
                "iec": float,
                "pre_trend_invariance": float,
                "shape_similarity": float,
                "detailed_results": {...}
            }
        """
        logger.info(f"Computing metrics for {len(pairs)} pairs...")

        mccs, mccs_results = CausalMetrics.mccs(predictions, outcomes, pairs)
        tcae, tcae_results = CausalMetrics.tcae(predictions, outcomes, pairs)
        iec, iec_results = CausalMetrics.iec(predictions, outcomes, pairs)
        delta_mccs, invariance_results = CausalMetrics.pre_trend_invariance(
            predictions, outcomes, pairs, features or {}
        )
        shape_sim, shape_results = CausalMetrics.shape_similarity(predictions, outcomes, pairs)

        logger.info(f"MCCS:     {mccs:.4f}")
        logger.info(f"TCAE:     {tcae:.2f} hours")
        logger.info(f"IEC:      {iec:.4f}")
        logger.info(f"Pre-trend invariance drop: {delta_mccs:.4f}")
        logger.info(f"Shape similarity: {shape_sim:.4f}")

        return {
            "mccs": float(mccs),
            "tcae_hours": float(tcae),
            "iec": float(iec),
            "pre_trend_invariance_delta": float(delta_mccs),
            "shape_similarity": float(shape_sim),
            "invariance_test_passed": invariance_results.get("test_passed", False),
            "detailed_results": {
                "mccs": mccs_results,
                "tcae": tcae_results,
                "iec": iec_results,
                "pre_trend_invariance": invariance_results,
                "shape_similarity": shape_results,
            },
        }
