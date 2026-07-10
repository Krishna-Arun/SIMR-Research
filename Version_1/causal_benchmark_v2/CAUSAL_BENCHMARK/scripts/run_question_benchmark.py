"""
run_question_benchmark.py

Evaluate LLMs on the 30 clinical questions benchmark.

Workflow:
1. Load questions (with hidden ground truth)
2. Get model predictions
3. Score responses against evaluation rubric
4. Compute causal metrics (MCCS, TCAE, IEC, etc)
5. Generate comparison report
"""

import json
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple
import logging
from datetime import datetime
import sys
import re

# Setup paths
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

# Paths
QUESTIONS_FILE = BENCHMARK_DIR / "questions" / "questions.json"
ANSWERS_DIR = BENCHMARK_DIR / "answers"
OUTPUTS_DIR = BENCHMARK_DIR / "outputs"
ANSWERS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# Model configurations - EDIT THIS TO ADD YOUR MODELS
MODELS_TO_TEST = [
    # Quick test: mock backend (runs immediately)
    ("mock", "mock"),
]

PROMPT_STYLES = ["zero_shot"]  # Just zero-shot for quick test


class QuestionBenchmarkRunner:
    """Run evaluation on clinical questions benchmark."""

    def __init__(self):
        """Initialize runner."""
        self.questions = []
        self.results = {}

    def load_questions(self):
        """Load questions with hidden ground truth."""
        if not QUESTIONS_FILE.exists():
            raise FileNotFoundError(f"Questions file not found: {QUESTIONS_FILE}")

        with open(QUESTIONS_FILE) as f:
            data = json.load(f)

        self.questions = data["questions"]
        logger.info(f"Loaded {len(self.questions)} questions")
        return self.questions

    def run_inference(
        self, model_name: str, backend: str, prompt_style: str
    ) -> Dict[str, dict]:
        """
        Run inference on all questions.

        Returns:
            {question_id: {'response': str, 'question_id': str, ...}}
        """
        logger.info(f"Running inference: {model_name} ({backend}, {prompt_style})")

        try:
            predictor = create_predictor(model_name, prompt_style, backend)
        except Exception as e:
            logger.error(f"Failed to create predictor: {e}")
            return {}

        predictions = {}
        errors = 0

        for i, question in enumerate(self.questions):
            if (i + 1) % 5 == 0:
                logger.info(f"  Progress: {i+1}/{len(self.questions)} ({errors} errors)")

            try:
                q_id = question["question_id"]
                question_stem = question["question_stem"]

                # Get model response (this should be text, not trajectory)
                # For this version, we'll do a simple text-based approach
                # In production, parse structured output

                response = predictor.predict(question)  # Returns trajectory
                if response is not None:
                    predictions[q_id] = {
                        "question_id": q_id,
                        "response": str(response),  # Store as string
                        "trajectory": response.tolist() if isinstance(response, np.ndarray) else response,
                    }

            except Exception as e:
                errors += 1
                logger.debug(f"Error predicting {q_id}: {e}")

        logger.info(f"Generated {len(predictions)} predictions ({errors} errors)")
        return predictions

    def score_predictions(
        self, predictions: Dict[str, dict], model_name: str
    ) -> Dict:
        """
        Score model predictions against ground truth.

        Returns:
            {question_id: {scores...}}
        """
        logger.info(f"Scoring predictions for {model_name}...")
        scores = {}

        for question in self.questions:
            q_id = question["question_id"]

            if q_id not in predictions:
                continue

            pred = predictions[q_id]
            ground_truth = question["ground_truth"]
            rubric = question["evaluation_rubric"]

            # Parse prediction (simplified scoring)
            # In production, use LLM to evaluate response against rubric

            try:
                trajectory = pred.get("trajectory", [])
                if not trajectory:
                    continue

                # Compare against ground truth trajectories
                gt_a = ground_truth["case_a"]["trajectory_48h"]
                gt_b = ground_truth["case_b"]["trajectory_48h"]

                # Simplified scoring: check direction
                # Real scoring would use the full rubric
                final_a = gt_a[-1] if gt_a else 0
                final_b = gt_b[-1] if gt_b else 0

                # Simple metric: did model predict correct direction?
                pred_final = trajectory[-1] if trajectory else 0
                gt_direction = np.sign(final_a - final_b)
                pred_direction = np.sign(pred_final - 0.5)  # Simplified

                direction_correct = (gt_direction == pred_direction)

                scores[q_id] = {
                    "question_id": q_id,
                    "direction_correct": bool(direction_correct),
                    "ground_truth_a_change": ground_truth["case_a"]["change"],
                    "ground_truth_b_change": ground_truth["case_b"]["change"],
                    "rubric_weights": {
                        k: v["weight"] for k, v in rubric.items()
                    },
                }

            except Exception as e:
                logger.debug(f"Error scoring {q_id}: {e}")

        logger.info(f"Scored {len(scores)} questions")
        return scores

    def compute_metrics(self, scores: Dict, model_name: str) -> Dict:
        """Compute causal metrics."""
        if not scores:
            return {
                "model": model_name,
                "mccs": 0.0,
                "n_scored": 0,
            }

        # Direction accuracy
        correct = sum(1 for s in scores.values() if s.get("direction_correct", False))
        total = len(scores)
        mccs = correct / total if total > 0 else 0

        return {
            "model": model_name,
            "mccs": float(mccs),
            "n_scored": total,
            "n_correct": correct,
            "accuracy": f"{mccs*100:.1f}%",
        }

    def run_all_models(self):
        """Run all model configurations."""
        logger.info(f"Running benchmark with {len(MODELS_TO_TEST)} models...")

        all_results = []

        for model_name, backend in MODELS_TO_TEST:
            for prompt_style in PROMPT_STYLES:
                try:
                    # Run inference
                    predictions = self.run_inference(model_name, backend, prompt_style)

                    if not predictions:
                        logger.warning(
                            f"No predictions for {model_name} ({prompt_style})"
                        )
                        continue

                    # Score predictions
                    scores = self.score_predictions(predictions, model_name)

                    # Compute metrics
                    metrics = self.compute_metrics(scores, model_name)
                    metrics["backend"] = backend
                    metrics["prompt_style"] = prompt_style
                    metrics["timestamp"] = datetime.now().isoformat()

                    all_results.append(metrics)

                    logger.info(f"  MCCS: {metrics['mccs']:.4f}")

                    # Save model responses
                    response_file = (
                        ANSWERS_DIR
                        / f"{model_name.replace('/', '_')}_{prompt_style}_responses.json"
                    )
                    with open(response_file, "w") as f:
                        json.dump(
                            {
                                "model": model_name,
                                "prompt_style": prompt_style,
                                "predictions": predictions,
                                "scores": scores,
                                "metrics": metrics,
                            },
                            f,
                            indent=2,
                        )

                except Exception as e:
                    logger.error(f"Error with {model_name} ({prompt_style}): {e}")

        return all_results

    def save_results(self, results: List[Dict]):
        """Save results to JSON."""
        output_file = OUTPUTS_DIR / "benchmark_results.json"

        output = {
            "benchmark": "causal_intervention_questions_v1",
            "timestamp": datetime.now().isoformat(),
            "n_questions": len(self.questions),
            "results": sorted(results, key=lambda r: r.get("mccs", 0), reverse=True),
        }

        with open(output_file, "w") as f:
            json.dump(output, f, indent=2)

        logger.info(f"Saved results to {output_file}")

    def generate_report(self, results: List[Dict]):
        """Generate markdown report."""
        report_file = OUTPUTS_DIR / "RESULTS.md"

        lines = [
            "# Causal Intervention Benchmark - Results",
            "",
            f"**Timestamp:** {datetime.now().isoformat()}",
            f"**Questions:** {len(self.questions)}",
            f"**Models Tested:** {len(results)}",
            "",
            "## Model Comparison",
            "",
            "| Model | Backend | Prompt | MCCS | Questions Correct | Status |",
            "|-------|---------|--------|------|-------------------|--------|",
        ]

        for result in sorted(results, key=lambda r: r.get("mccs", 0), reverse=True):
            model = result["model"]
            backend = result["backend"]
            prompt = result["prompt_style"]
            mccs = f"{result['mccs']:.4f}"
            correct = f"{result['n_correct']}/{result['n_scored']}"
            status = (
                "✓ Good"
                if result["mccs"] > 0.65
                else ("~ Medium" if result["mccs"] > 0.55 else "✗ Poor")
            )

            lines.append(f"| {model} | {backend} | {prompt} | {mccs} | {correct} | {status} |")

        lines.extend(
            [
                "",
                "## Metric Definitions",
                "",
                "- **MCCS** (Matched Counterfactual Consistency Score): % of questions where model predicts correct direction",
                "  - 0.50 = Random guessing",
                "  - 0.65+ = Good causal understanding",
                "  - 0.75+ = Excellent",
                "",
                "## Interpretation Guide",
                "",
                "| MCCS | Interpretation |",
                "|------|-----------------|",
                "| 0.50-0.55 | No better than random, doesn't understand causality |",
                "| 0.55-0.65 | Weak causal understanding, try different prompts |",
                "| 0.65-0.75 | Good causal understanding ✓ |",
                "| 0.75+ | Excellent causal reasoning ✓✓ |",
                "",
                "## Conclusions",
                "",
                "TODO: Add interpretation of results",
                "",
            ]
        )

        report = "\n".join(lines)
        with open(report_file, "w") as f:
            f.write(report)

        logger.info(f"Saved report to {report_file}")
        print("\n" + report)


def main():
    """Run full benchmark."""
    runner = QuestionBenchmarkRunner()

    try:
        runner.load_questions()
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
