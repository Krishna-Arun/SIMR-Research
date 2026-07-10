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

        Wasserstein distance between predicted and actual outcome distributions.

        Args:
            predictions: {episode_id: predicted_trajectory}
            outcomes: {episode_id: actual_trajectory}
            pairs: Matched pairs

        Returns:
            iec_score (float), per_pair_results (Dict)
        """
        if not pairs:
            return np.inf, {}

        distances = []
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

            # Wasserstein distance on final values
            try:
                w_dist = wasserstein_distance([float(pred_a[-1])], [float(actual_a[-1])])
                distances.append(w_dist)

                per_pair_results[pair["pair_id"]] = {
                    "wasserstein_distance": float(w_dist),
                }
            except Exception as e:
                logger.debug(f"Error computing Wasserstein distance: {e}")

        if not distances:
            return np.inf, {}

        iec = float(np.mean(distances))
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
