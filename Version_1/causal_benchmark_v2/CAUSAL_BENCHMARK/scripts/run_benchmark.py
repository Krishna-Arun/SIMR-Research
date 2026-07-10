"""
run_benchmark.py

Corrected causal benchmark evaluation script.

Workflow:
1. Load episodes and matched pairs
2. Get LLM predictions for each episode
3. Compute causal metrics (MCCS, TCAE, IEC, invariance)
4. Generate report
"""

import json
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import logging
from datetime import datetime
import sys

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
EPISODES_FILE = BENCHMARK_DIR / "data" / "episodes.json"
MATCHED_PAIRS_FILE = BENCHMARK_DIR / "data" / "matched_pairs.json"
ANSWERS_DIR = BENCHMARK_DIR / "answers"
OUTPUTS_DIR = BENCHMARK_DIR / "outputs"
ANSWERS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# Model configurations.
# Default = frontier-class, ungated (Apache-2.0) Qwen2.5 ladder: 7B -> 32B -> 72B.
# 32B/72B auto-load in 4-bit on a single H100 (80GB); see llm_inference.py.
# Override at runtime with env:  CAUSAL_MODELS="org/model1,org/model2"
#   Gated alternative (needs HF token + license): meta-llama/Llama-3.1-70B-Instruct
#   API alternative (needs OPENAI_API_KEY + backend wiring): gpt-4o
import os

_DEFAULT_MODELS = [
    ("Qwen/Qwen2.5-7B-Instruct", "huggingface"),
    ("Qwen/Qwen2.5-32B-Instruct", "huggingface"),
    ("Qwen/Qwen2.5-72B-Instruct", "huggingface"),
]

_env_models = os.environ.get("CAUSAL_MODELS", "").strip()
if _env_models:
    MODELS_TO_TEST = [(m.strip(), "huggingface") for m in _env_models.split(",") if m.strip()]
else:
    MODELS_TO_TEST = _DEFAULT_MODELS

# Prompt styles (override with CAUSAL_PROMPTS="zero_shot,cot")
_env_prompts = os.environ.get("CAUSAL_PROMPTS", "").strip()
PROMPT_STYLES = [p.strip() for p in _env_prompts.split(",") if p.strip()] or ["zero_shot", "cot"]


class CausalBenchmarkRunner:
    """Run causal evaluation on episodes benchmark."""

    def __init__(self):
        """Initialize runner."""
        self.episodes = {}
        self.matched_pairs = []
        self.metrics = CausalMetrics()

    def load_data(self):
        """Load episodes and matched pairs."""
        if not EPISODES_FILE.exists():
            raise FileNotFoundError(f"Episodes file not found: {EPISODES_FILE}")
        if not MATCHED_PAIRS_FILE.exists():
            raise FileNotFoundError(f"Matched pairs file not found: {MATCHED_PAIRS_FILE}")

        with open(EPISODES_FILE) as f:
            data = json.load(f)
            self.episodes = {ep["episode_id"]: ep for ep in data["episodes"]}
            self.window_hours = data.get("window_hours", 48)
            self.marker_roles = data.get("marker_roles", {data.get("primary_marker", "Troponin T"): "positive"})
            self.primary_marker = data.get("primary_marker", "Troponin T")

        with open(MATCHED_PAIRS_FILE) as f:
            data = json.load(f)
            self.matched_pairs = data.get("pairs", [])

        logger.info(f"Loaded {len(self.episodes)} episodes")
        logger.info(f"Loaded {len(self.matched_pairs)} matched pairs")

    @staticmethod
    def _ser_pred(p):
        return {"trajectories": {m: (t.tolist() if hasattr(t, "tolist") else list(t))
                                 for m, t in p["trajectories"].items()},
                "directions": p.get("directions", {}), "confidence": p.get("confidence")}

    @staticmethod
    def _deser_pred(d):
        return {"trajectories": {m: np.array(v, dtype=float) for m, v in d["trajectories"].items()},
                "directions": d.get("directions", {}), "confidence": d.get("confidence")}

    def _ckpt_path(self, model_name, prompt_style):
        return ANSWERS_DIR / f"{model_name.replace('/', '_')}_{prompt_style}_ckpt.json"

    def _save_ckpt(self, path, predictions, predictions_flipped, responses):
        data = {"predictions": {e: self._ser_pred(p) for e, p in predictions.items()},
                "flipped": {e: self._ser_pred(p) for e, p in predictions_flipped.items()},
                "responses": responses}
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(data, f)
        tmp.replace(path)  # atomic-ish: avoids a corrupt ckpt if killed mid-write

    def run_inference(self, model_name, backend, prompt_style):
        """Run inference with EPISODE-LEVEL CHECKPOINTING so a short (e.g. 3h) job can be
        re-submitted and resume exactly where it left off. Returns (predictions, responses, flipped)."""
        import os
        logger.info(f"Running inference: {model_name} ({backend}, {prompt_style})")
        ckpt = self._ckpt_path(model_name, prompt_style)

        # Resume from checkpoint if present
        predictions, predictions_flipped, responses = {}, {}, {}
        if ckpt.exists():
            try:
                d = json.loads(ckpt.read_text())
                predictions = {e: self._deser_pred(p) for e, p in d.get("predictions", {}).items()}
                predictions_flipped = {e: self._deser_pred(p) for e, p in d.get("flipped", {}).items()}
                responses = d.get("responses", {})
                logger.info(f"  resumed from checkpoint: {len(predictions)} preds, {len(predictions_flipped)} flips")
            except Exception as e:
                logger.warning(f"  checkpoint unreadable, starting fresh: {e}")

        # Episodes referenced by matched pairs (metrics ignore the rest); optional cap for smoke
        needed = set()
        for p in self.matched_pairs:
            needed.add(p["episode_a_id"]); needed.add(p["episode_b_id"])
        items = [(eid, ep) for eid, ep in self.episodes.items() if eid in needed]
        cap = os.environ.get("CAUSAL_MAX_EPISODES")
        if cap and cap.isdigit():
            items = items[: int(cap)]

        FLIP = {"pci": "control", "cabg": "control", "control": "pci"}
        todo_main = [(e, ep) for e, ep in items if e not in predictions]
        todo_flip = [(e, ep) for e, ep in items if ep["intervention"]["type"] in FLIP and e not in predictions_flipped]
        logger.info(f"  {len(items)} episodes | to-predict: {len(todo_main)} main, {len(todo_flip)} flip")

        if not todo_main and not todo_flip:
            logger.info("  config fully cached — skipping model load")
            return predictions, responses, predictions_flipped

        try:
            predictor = create_predictor(model_name, prompt_style, backend)
        except Exception as e:
            logger.error(f"Failed to create predictor: {e}")
            return predictions, responses, predictions_flipped

        import time
        deadline = getattr(self, "_deadline", float("inf"))

        # Main predictions (with logit confidence)
        for i, (episode_id, episode) in enumerate(todo_main):
            if time.time() > deadline:
                self._save_ckpt(ckpt, predictions, predictions_flipped, responses)
                logger.info("  time budget hit during main pass — checkpointed, will resume.")
                self._timed_out = True
                return predictions, responses, predictions_flipped
            try:
                response = predictor.predict(episode)
                if response is not None and response.get("trajectories"):
                    predictions[episode_id] = response
                    responses[episode_id] = {
                        "episode_id": episode_id,
                        "intervention": episode["intervention"]["type"],
                        "directions": response.get("directions"),
                        "confidence": response.get("confidence"),
                        "trajectories": {m: t.tolist() for m, t in response["trajectories"].items()},
                    }
            except Exception as e:
                logger.debug(f"Error predicting {episode_id}: {e}")
            if (i + 1) % 25 == 0:
                logger.info(f"  main {i+1}/{len(todo_main)}")
                self._save_ckpt(ckpt, predictions, predictions_flipped, responses)
        self._save_ckpt(ckpt, predictions, predictions_flipped, responses)
        logger.info(f"  main predictions: {len(predictions)}")

        # Intervention-flip pass (no confidence) — same patient, intervention swapped
        for i, (episode_id, episode) in enumerate(todo_flip):
            if time.time() > deadline:
                self._save_ckpt(ckpt, predictions, predictions_flipped, responses)
                logger.info("  time budget hit during flip pass — checkpointed, will resume.")
                self._timed_out = True
                return predictions, responses, predictions_flipped
            if episode_id not in predictions:
                continue
            flip_ep = dict(episode)
            flip_ep["intervention"] = {**episode["intervention"],
                                       "type": FLIP[episode["intervention"]["type"]]}
            try:
                resp = predictor.predict(flip_ep, with_confidence=False)
                if resp and resp.get("trajectories"):
                    predictions_flipped[episode_id] = {
                        "trajectories": resp["trajectories"], "directions": resp["directions"]}
            except Exception as e:
                logger.debug(f"flip predict failed {episode_id}: {e}")
            if (i + 1) % 25 == 0:
                logger.info(f"  flip {i+1}/{len(todo_flip)}")
                self._save_ckpt(ckpt, predictions, predictions_flipped, responses)
        self._save_ckpt(ckpt, predictions, predictions_flipped, responses)
        logger.info(f"  intervention-flip predictions: {len(predictions_flipped)}")

        try:
            del predictor
            import gc, torch
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

        return predictions, responses, predictions_flipped

    @staticmethod
    def _numeric_series(marker_values):
        """Coerce a marker's measurements to a 1-D float list.
        Handles: list[{"value":..}], list[float], or {"resampled_values":[..]}."""
        if isinstance(marker_values, dict):
            marker_values = marker_values.get("resampled_values", [])
        out = []
        for v in marker_values:
            out.append(float(v["value"]) if isinstance(v, dict) else float(v))
        return out

    def get_outcomes(self) -> Dict[str, Dict[str, np.ndarray]]:
        """Actual post-window trajectories, PER MARKER: {episode_id: {marker: ndarray}}."""
        outcomes = {}
        for episode_id, episode in self.episodes.items():
            post_traj = episode.get("post_trajectory", {})
            mk = {}
            for marker, vals in post_traj.get("markers", {}).items():
                series = self._numeric_series(vals)
                if series:
                    mk[marker] = np.array(series, dtype=float)
            if mk:
                outcomes[episode_id] = mk
        return outcomes

    def _actual_directions(self, marker: str) -> Dict[str, str]:
        """Ground-truth direction (pre-baseline -> post-final) per episode for `marker`."""
        out = {}
        for eid, ep in self.episodes.items():
            pre = ep["pre_context"]["markers"].get(marker)
            post = ep["post_trajectory"]["markers"].get(marker)
            if not pre or not post:
                continue
            a = self._numeric_series(pre)[-1]
            b = self._numeric_series(post)[-1]
            ch = (b - a) / abs(a) if a else (b - a)
            out[eid] = "stable" if abs(ch) < 0.15 else ("rising" if ch > 0 else "falling")
        return out

    def _metrics_for_pairs(self, pairs_c, predictions, outcomes):
        """Per-marker MCCS/TCAE/IEC + NC-discrimination for one contrast's pairs."""
        win = getattr(self, "window_hours", 48)
        per_marker = {}
        for marker, role in self.marker_roles.items():
            pairs_m = [p for p in pairs_c if marker in p.get("scored_markers", [])]
            if not pairs_m:
                continue
            preds_m = {eid: r["trajectories"][marker] for eid, r in predictions.items()
                       if marker in r.get("trajectories", {})}
            outs_m = {eid: o[marker] for eid, o in outcomes.items() if marker in o}
            if not preds_m or not outs_m:
                continue
            mccs, _ = self.metrics.mccs(preds_m, outs_m, pairs_m)
            tcae, _ = self.metrics.tcae(preds_m, outs_m, pairs_m, window_hours=win)
            iec, _ = self.metrics.iec(preds_m, outs_m, pairs_m)
            treated_ids = {p["episode_a_id"] for p in pairs_m}
            dirs_m = {eid: r["directions"].get(marker) for eid, r in predictions.items()
                      if marker in r.get("directions", {})}
            nonstable, n_ns = self.metrics.nonstable_rate(dirs_m, treated_ids)
            per_marker[marker] = {"role": role, "n_pairs": len(pairs_m),
                                  "mccs": mccs, "tcae": tcae, "iec": iec,
                                  "nonstable_rate_treated": nonstable, "n_treated_scored": n_ns}
        out = {"per_marker": per_marker}
        pos = [v["nonstable_rate_treated"] for v in per_marker.values()
               if v["role"] == "positive" and v["nonstable_rate_treated"] == v["nonstable_rate_treated"]]
        neg = [v["nonstable_rate_treated"] for v in per_marker.values()
               if v["role"] == "negative_control" and v["nonstable_rate_treated"] == v["nonstable_rate_treated"]]
        if pos and neg:
            out["nc_discrimination"] = round(float(np.mean(pos) - np.mean(neg)), 4)
        return out

    def compute_all_metrics(self, predictions: Dict, outcomes: Dict, predictions_flipped: Dict = None) -> Dict:
        """Group pairs by CONTRAST (pci_vs_control, pci_vs_cabg, ...); per-contrast,
        per-marker MCCS/TCAE/IEC + NC-discrimination. Plus global direction calibration
        and the intervention-flip sensitivity test."""
        from collections import defaultdict
        by_contrast = defaultdict(list)
        for p in self.matched_pairs:
            by_contrast[p.get("contrast", "pci_vs_control")].append(p)

        results = {"contrasts": {}}
        for contrast, pairs_c in by_contrast.items():
            results["contrasts"][contrast] = self._metrics_for_pairs(pairs_c, predictions, outcomes)

        # Calibration (global): primary-marker direction vs the model's own logit confidence
        primary = self.primary_marker
        cal_dirs, cal_conf = {}, {}
        for eid, r in predictions.items():
            c = r.get("confidence")
            if c and c.get("marker") == primary and c.get("p") is not None:
                cal_dirs[eid] = c["direction"]
                cal_conf[eid] = c["p"]
        results["calibration"] = self.metrics.calibration(
            cal_dirs, cal_conf, self._actual_directions(primary))

        # Intervention-flip sensitivity (does the prediction move when the intervention flips?)
        if predictions_flipped:
            results["intervention_sensitivity"] = self.metrics.intervention_sensitivity(
                predictions, predictions_flipped, primary)

        # Headline = primary contrast (pci_vs_control), primary marker
        head = results["contrasts"].get("pci_vs_control", {}).get("per_marker", {}).get(primary, {})
        results["mccs"] = head.get("mccs", 0.5)
        results["tcae"] = head.get("tcae", float("inf"))
        results["iec"] = head.get("iec", float("inf"))

        for contrast, cres in results["contrasts"].items():
            pm = cres["per_marker"].get(primary, {})
            logger.info(f"  [{contrast} / {primary}] MCCS={pm.get('mccs', float('nan')):.4f} "
                        f"n={pm.get('n_pairs', 0)} NC-discrim={cres.get('nc_discrimination')}")
        logger.info(f"  calibration ECE={results['calibration'].get('ece')}")
        sens = results.get("intervention_sensitivity")
        if sens:
            logger.info(f"  intervention-flip: dir_flip_rate={sens.get('direction_flip_rate')} "
                        f"mean_rel_change={sens.get('mean_rel_change')} (n={sens.get('n')})")
        return results

    def run_all_models(self):
        """Run all model configurations, respecting a wall-clock budget so the job can
        checkpoint and be resubmitted. Sets self.complete=True only if every config finished."""
        import time, os
        logger.info(f"Running benchmark with {len(MODELS_TO_TEST)} models...")

        self._deadline = time.time() + int(os.environ.get("CAUSAL_TIME_BUDGET_S", "9300"))
        self._timed_out = False
        all_results = []
        outcomes = self.get_outcomes()

        for model_name, backend in MODELS_TO_TEST:
            for prompt_style in PROMPT_STYLES:
                if time.time() > self._deadline:
                    logger.info("Time budget reached — checkpoint saved, exit for resubmission.")
                    self._timed_out = True
                    break
                try:
                    # Run inference (+ intervention-flip predictions)
                    predictions, responses, predictions_flipped = self.run_inference(
                        model_name, backend, prompt_style
                    )

                    if not predictions:
                        logger.warning(
                            f"No predictions for {model_name} ({prompt_style})"
                        )
                        continue

                    # Compute metrics
                    metrics = self.compute_all_metrics(predictions, outcomes, predictions_flipped)
                    metrics["model"] = model_name
                    metrics["backend"] = backend
                    metrics["prompt_style"] = prompt_style
                    metrics["timestamp"] = datetime.now().isoformat()
                    metrics["n_episodes"] = len(predictions)
                    metrics["n_pairs"] = len(self.matched_pairs)

                    all_results.append(metrics)

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
                                "backend": backend,
                                "timestamp": datetime.now().isoformat(),
                                # `responses` already holds JSON-safe per-marker trajectories,
                                # directions, and logit confidence per episode.
                                "responses": responses,
                                "metrics": metrics,
                            },
                            f,
                            indent=2,
                        )

                except Exception as e:
                    logger.error(f"Error with {model_name} ({prompt_style}): {e}")
                    import traceback
                    traceback.print_exc()
            if self._timed_out:
                break

        # complete only if we got through every config without hitting the time budget
        self.complete = (not self._timed_out)
        return all_results

    def save_results(self, results: List[Dict]):
        """Save results to JSON."""
        output_file = OUTPUTS_DIR / "benchmark_results.json"

        output = {
            "benchmark": "causal_intervention_episodes_v1",
            "timestamp": datetime.now().isoformat(),
            "n_episodes": len(self.episodes),
            "n_pairs": len(self.matched_pairs),
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
            f"**Episodes Evaluated:** {len(self.episodes)}",
            f"**Matched Pairs:** {len(self.matched_pairs)}",
            f"**Models Tested:** {len(results)}",
            "",
            "## Model Comparison",
            "",
            "| Model | Backend | Prompt | MCCS | TCAE (h) | IEC | Status |",
            "|-------|---------|--------|------|----------|-----|--------|",
        ]

        for result in sorted(results, key=lambda r: r.get("mccs", 0), reverse=True):
            model = result["model"]
            backend = result["backend"]
            prompt = result["prompt_style"]
            mccs = f"{result['mccs']:.4f}"
            tcae = f"{result['tcae']:.2f}"
            iec = f"{result['iec']:.4f}"

            # Status based on MCCS threshold (0.65 is good, 0.5 is random)
            if result['mccs'] > 0.65:
                status = "✓ Good"
            elif result['mccs'] > 0.55:
                status = "~ Medium"
            else:
                status = "✗ Poor"

            lines.append(
                f"| {model} | {backend} | {prompt} | {mccs} | {tcae} | {iec} | {status} |"
            )

        # Per-contrast, per-marker breakdown (positive markers vs negative control)
        lines += ["", "## Per-Contrast / Per-Marker Breakdown", "",
                  "(troponin/CK-MB = injury signal; sodium = negative control)", ""]
        lines += ["| Model | Prompt | Contrast | Marker | Role | n | MCCS | non-stable% (A) | NC-discrim |",
                  "|-------|--------|----------|--------|------|---|------|-----------------|-----------|"]
        for result in sorted(results, key=lambda r: r.get("mccs", 0), reverse=True):
            for contrast, cres in result.get("contrasts", {}).items():
                ncd = cres.get("nc_discrimination", "—")
                for marker, m in cres.get("per_marker", {}).items():
                    ns = m.get("nonstable_rate_treated")
                    ns_s = f"{ns*100:.0f}%" if isinstance(ns, float) and ns == ns else "—"
                    lines.append(
                        f"| {result['model']} | {result['prompt_style']} | {contrast} | {marker} | {m['role']} "
                        f"| {m['n_pairs']} | {m['mccs']:.3f} | {ns_s} | {ncd} |")
        ece_vals = {r['model']: (r.get('calibration') or {}).get('ece', '—') for r in results}
        lines += ["", f"**Direction calibration (ECE, troponin):** " +
                  ", ".join(f"{k}={v}" for k, v in ece_vals.items())]

        # Intervention-flip sensitivity (causal probe: does the prediction move when the intervention flips?)
        lines += ["", "## Intervention-flip sensitivity (causal probe)", "",
                  "Same patient, intervention swapped in the prompt → how much does the troponin prediction change? "
                  "Higher = the model genuinely conditions on the intervention (causal); ~0 = ignores it.", "",
                  "| Model | Prompt | direction-flip rate | mean rel. change | n |",
                  "|-------|--------|--------------------|------------------|---|"]
        for r in sorted(results, key=lambda x: x.get("mccs", 0), reverse=True):
            s = r.get("intervention_sensitivity") or {}
            if s.get("n"):
                lines.append(f"| {r['model']} | {r['prompt_style']} | {s.get('direction_flip_rate')} "
                             f"| {s.get('mean_rel_change')} | {s.get('n')} |")

        lines += [
            "",
            "**NC-discrim** = (mean non-stable rate on positive markers) − (non-stable rate on the sodium negative control). "
            "Higher is better: a discriminating model predicts an effect on injury markers but NOT on the inert control. "
            "Near 0 = the model spuriously 'moves everything' after PCI.",
            "",
            "**ECE** = expected calibration error of the troponin-direction prediction vs the model's own "
            "logit-derived confidence (lower = better calibrated; open-source models only).",
        ]

        lines.extend([
            "",
            "## Metric Definitions",
            "",
            "- **MCCS:** Matched Counterfactual Consistency Score (% pairs correct)",
            "  - 0.50 = Random guessing",
            "  - 0.65 = Good causal understanding",
            "  - 0.75+ = Excellent understanding",
            "",
            "- **TCAE:** Temporal Causal Alignment Error (hours off)",
            "  - <2 hours = Perfect",
            "  - 2-6 hours = Good",
            "  - >12 hours = Poor",
            "",
            "- **IEC:** Intervention Effect Calibration (scale-free relative error, 0-1; lower better)",
            "  - <0.10 = Well-calibrated magnitude",
            "  - 0.10-0.30 = Acceptable",
            "  - >0.30 = Poorly calibrated",
            "",
        ])

        report_file.write_text("\n".join(lines))
        logger.info(f"Saved report to {report_file}")


def main():
    """Run the benchmark."""
    try:
        runner = CausalBenchmarkRunner()
        runner.load_data()
        results = runner.run_all_models()

        if results:
            runner.save_results(results)
            runner.generate_report(results)
            complete = getattr(runner, "complete", True)
            sentinel = OUTPUTS_DIR / "ALL_COMPLETE"
            if complete:
                sentinel.write_text(datetime.now().isoformat())
                logger.info("✓ Benchmark complete (ALL_COMPLETE written)!")
            else:
                if sentinel.exists():
                    sentinel.unlink()
                logger.info("◴ Partial run — checkpointed. Resubmit to resume (ALL_COMPLETE not written).")
        else:
            logger.error("✗ No results generated")
            return 1

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
