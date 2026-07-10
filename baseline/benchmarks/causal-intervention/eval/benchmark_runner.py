"""
benchmark_runner.py

Main evaluation harness for the causal intervention benchmark.

Runs:
1. Episode loading
2. LLM inference (all models)
3. Metric computation
4. Report generation
"""

import json
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple
import logging
from datetime import datetime
import sys

# Add parent paths
BENCHMARK_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BENCHMARK_DIR / "models"))
sys.path.insert(0, str(BENCHMARK_DIR / "metrics"))

from llm_inference import create_predictor
from causal_metrics import CausalMetrics

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent.parent.parent
BENCHMARK_DIR = Path(__file__).parent.parent
DATA_DIR = BENCHMARK_DIR / "data"
EPISODES_FILE = DATA_DIR / "episodes.json"
FEATURES_FILE = DATA_DIR / "encoded_features.json"
PAIRS_FILE = DATA_DIR / "matched_pairs.json"
OUTPUT_DIR = BENCHMARK_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Model Configurations ──────────────────────────────────────────────────────
MODELS_TO_TEST = [
    # For testing, use mock predictors
    # In production, replace with actual models:
    ("mock_qwen", "mock"),
    ("mock_deepseek", "mock"),
    ("mock_llama", "mock"),
    ("mock_mistral", "mock"),

    # Uncomment to use actual Hugging Face models (requires GPU + disk space):
    # ("Qwen/Qwen2-7B-Instruct", "huggingface"),
    # ("deepseek-ai/deepseek-llm-7b-chat", "huggingface"),
    # ("meta-llama/Llama-2-7b-chat-hf", "huggingface"),
    # ("mistralai/Mistral-7B-Instruct-v0.1", "huggingface"),
]

PROMPT_STYLES = ["zero_shot", "cot", "few_shot"]


class BenchmarkRunner:
    """Run full evaluation pipeline."""

    def __init__(self):
        """Initialize benchmark runner."""
        self.episodes = {}
        self.features = {}
        self.pairs = []
        self.results = {}

    def load_data(self):
        """Load episodes, features, and matched pairs."""
        logger.info("Loading data...")

        if not EPISODES_FILE.exists():
            logger.error(f"Episodes file not found: {EPISODES_FILE}")
            raise FileNotFoundError(f"Run extract_episodes.py first")

        with open(EPISODES_FILE) as f:
            episodes_data = json.load(f)
        self.episodes = {ep["episode_id"]: ep for ep in episodes_data["episodes"]}
        logger.info(f"Loaded {len(self.episodes)} episodes")

        if not FEATURES_FILE.exists():
            logger.warning(f"Features file not found: {FEATURES_FILE}")
        else:
            with open(FEATURES_FILE) as f:
                features_data = json.load(f)
            self.features = {f["episode_id"]: f for f in features_data["features"]}
            logger.info(f"Loaded {len(self.features)} feature sets")

        if not PAIRS_FILE.exists():
            logger.error(f"Pairs file not found: {PAIRS_FILE}")
            raise FileNotFoundError(f"Run construct_matched_pairs.py first")

        with open(PAIRS_FILE) as f:
            pairs_data = json.load(f)
        self.pairs = pairs_data["pairs"]
        logger.info(f"Loaded {len(self.pairs)} matched pairs")

    def run_inference(self, model_name: str, backend: str, prompt_style: str) -> Dict[str, np.ndarray]:
        """
        Run inference with a specific model.

        Returns:
            {episode_id: predicted_trajectory}
        """
        logger.info(f"Running inference: {model_name} ({backend}, {prompt_style})")

        try:
            predictor = create_predictor(model_name, prompt_style, backend)
        except Exception as e:
            logger.error(f"Failed to create predictor: {e}")
            return {}

        predictions = {}
        errors = 0

        # Only predict for episodes that appear in pairs
        episode_ids_in_pairs = set()
        for pair in self.pairs:
            episode_ids_in_pairs.add(pair["episode_a_id"])
            episode_ids_in_pairs.add(pair["episode_b_id"])

        logger.info(f"Predicting for {len(episode_ids_in_pairs)} episodes in pairs...")

        for i, episode_id in enumerate(episode_ids_in_pairs):
            if episode_id not in self.episodes:
                continue

            if (i + 1) % 10 == 0:
                logger.info(f"  Progress: {i+1}/{len(episode_ids_in_pairs)} ({errors} errors)")

            try:
                episode = self.episodes[episode_id]
                trajectory = predictor.predict(episode)

                if trajectory is not None and len(trajectory) > 0:
                    predictions[episode_id] = trajectory
                else:
                    errors += 1
                    logger.debug(f"No prediction for {episode_id}")

            except Exception as e:
                errors += 1
                logger.debug(f"Error predicting {episode_id}: {e}")

        logger.info(f"Generated {len(predictions)} predictions ({errors} errors)")
        return predictions

    def extract_outcomes(self) -> Dict[str, np.ndarray]:
        """
        Extract actual outcomes from episodes.

        Returns:
            {episode_id: actual_trajectory}
        """
        logger.info("Extracting actual outcomes...")
        outcomes = {}

        for episode_id, episode in self.episodes.items():
            # For now, use Troponin I trajectory if available
            if "Troponin I" in episode["post_trajectory"]:
                trop_data = episode["post_trajectory"]["Troponin I"]
                trajectory = np.array(trop_data["resampled_values"])
                outcomes[episode_id] = trajectory

        logger.info(f"Extracted {len(outcomes)} outcomes")
        return outcomes

    def evaluate_model(self,
                      model_name: str,
                      backend: str,
                      prompt_style: str,
                      predictions: Dict[str, np.ndarray],
                      outcomes: Dict[str, np.ndarray]) -> Dict:
        """
        Evaluate a single model configuration.

        Returns:
            Metrics dict
        """
        logger.info(f"Evaluating {model_name} ({prompt_style})...")

        metrics = CausalMetrics.compute_all(predictions, outcomes, self.pairs, self.features)
        metrics["model"] = model_name
        metrics["backend"] = backend
        metrics["prompt_style"] = prompt_style
        metrics["timestamp"] = datetime.now().isoformat()

        return metrics

    def run_all_models(self):
        """Run all model configurations."""
        logger.info(f"Running benchmark with {len(MODELS_TO_TEST)} models...")

        outcomes = self.extract_outcomes()
        if not outcomes:
            logger.error("No outcomes extracted. Cannot continue.")
            return

        results = []

        for model_name, backend in MODELS_TO_TEST:
            for prompt_style in PROMPT_STYLES:
                try:
                    predictions = self.run_inference(model_name, backend, prompt_style)

                    if not predictions:
                        logger.warning(f"No predictions for {model_name} ({prompt_style})")
                        continue

                    metrics = self.evaluate_model(
                        model_name, backend, prompt_style, predictions, outcomes
                    )
                    results.append(metrics)

                    logger.info(f"  MCCS: {metrics['mccs']:.4f}")
                    logger.info(f"  TCAE: {metrics['tcae_hours']:.2f}h")
                    logger.info(f"  IEC: {metrics['iec']:.4f}")

                except Exception as e:
                    logger.error(f"Error with {model_name} ({prompt_style}): {e}")

        return results

    def save_results(self, results: List[Dict]):
        """Save results to JSON."""
        output_file = OUTPUT_DIR / "benchmark_results.json"

        output = {
            "benchmark": "causal_intervention_benchmark_v1",
            "timestamp": datetime.now().isoformat(),
            "n_pairs": len(self.pairs),
            "n_episodes": len(self.episodes),
            "results": results,
        }

        with open(output_file, "w") as f:
            json.dump(output, f, indent=2)

        logger.info(f"Saved results to {output_file}")

    def generate_report(self, results: List[Dict]):
        """Generate markdown report."""
        report_file = OUTPUT_DIR / "RESULTS.md"

        lines = [
            "# Causal Intervention Benchmark Results",
            "",
            f"**Timestamp:** {datetime.now().isoformat()}",
            f"**Pairs:** {len(self.pairs)}",
            f"**Episodes:** {len(self.episodes)}",
            "",
            "## Metric Summary",
            "",
            "| Model | Backend | Prompt | MCCS | TCAE (h) | IEC | Invariance | Status |",
            "|-------|---------|--------|------|----------|-----|-----------|--------|",
        ]

        for result in sorted(results, key=lambda r: r.get("mccs", 0), reverse=True):
            model = result["model"]
            backend = result["backend"]
            prompt = result["prompt_style"]
            mccs = f"{result['mccs']:.4f}"
            tcae = f"{result['tcae_hours']:.2f}"
            iec = f"{result['iec']:.4f}"
            invariance = "✓" if result.get("invariance_test_passed") else "✗"
            status = "✓ Good" if result["mccs"] > 0.65 else "~ Medium" if result["mccs"] > 0.55 else "✗ Poor"

            lines.append(
                f"| {model} | {backend} | {prompt} | {mccs} | {tcae} | {iec} | {invariance} | {status} |"
            )

        lines.extend([
            "",
            "## Metric Definitions",
            "",
            "- **MCCS** (Matched Counterfactual Consistency Score): Proportion of matched pairs where predicted outcome ordering is correct. Higher is better. Baseline: 0.5 (random).",
            "- **TCAE** (Temporal Causal Alignment Error): Median error in inflection point timing (hours). Lower is better.",
            "- **IEC** (Intervention Effect Calibration): Wasserstein distance between predicted and actual outcome distributions. Lower is better.",
            "- **Invariance** (✓/✗): Pre-trend invariance test passed? Drop of 10+ MCCS points when interventions shuffled.",
            "",
            "## Key Findings",
            "",
            "TODO: Add interpretation",
            "",
        ])

        report = "\n".join(lines)

        with open(report_file, "w") as f:
            f.write(report)

        logger.info(f"Saved report to {report_file}")
        print("\n" + report)


def main():
    """Run full benchmark."""
    runner = BenchmarkRunner()

    try:
        runner.load_data()
        results = runner.run_all_models()

        if results:
            runner.save_results(results)
            runner.generate_report(results)
        else:
            logger.error("No results generated")

    except Exception as e:
        logger.error(f"Benchmark failed: {e}", exc_info=True)


if __name__ == "__main__":
    main()
