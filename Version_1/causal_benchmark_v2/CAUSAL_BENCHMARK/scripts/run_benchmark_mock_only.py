"""Run benchmark with mock predictor only (no JSON parsing issues)"""
import json
import numpy as np
from pathlib import Path
from datetime import datetime
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "models"))
sys.path.insert(0, str(Path(__file__).parent.parent / "metrics"))

from llm_inference import create_predictor
from causal_metrics import CausalMetrics

BENCHMARK_DIR = Path(__file__).parent.parent
EPISODES_FILE = BENCHMARK_DIR / "data" / "episodes.json"
MATCHED_PAIRS_FILE = BENCHMARK_DIR / "data" / "matched_pairs.json"
OUTPUTS_DIR = BENCHMARK_DIR / "outputs"

with open(EPISODES_FILE) as f:
    episodes = {ep["episode_id"]: ep for ep in json.load(f)["episodes"]}

with open(MATCHED_PAIRS_FILE) as f:
    pairs = json.load(f).get("pairs", [])

print(f"✓ Loaded {len(episodes)} episodes, {len(pairs)} pairs")

# Mock predictor
predictor = create_predictor("mock", "zero_shot", "mock")

# Generate predictions
predictions = {}
outcomes = {}

for ep_id, ep in episodes.items():
    pred = predictor.predict(ep)
    predictions[ep_id] = np.array(pred)
    
    post_traj = ep.get("post_trajectory", {})
    for marker in ["Troponin T", "Troponin I"]:
        data = post_traj.get(marker, {})
        if isinstance(data, dict) and "resampled_values" in data:
            outcomes[ep_id] = np.array(data["resampled_values"])
            break
        elif isinstance(data, list) and data:
            outcomes[ep_id] = np.array(data)
            break

print(f"✓ Generated {len(predictions)} predictions, {len(outcomes)} outcomes")

# Compute metrics
metrics = CausalMetrics()
mccs, _ = metrics.mccs(predictions, outcomes, pairs)
tcae, _ = metrics.tcae(predictions, outcomes, pairs)
iec, _ = metrics.iec(predictions, outcomes, pairs)

print(f"\n{'='*60}")
print(f"CAUSAL BENCHMARK RESULTS (Real Data)")
print(f"{'='*60}")
print(f"Episodes Evaluated: {len(episodes)}")
print(f"Matched Pairs: {len(pairs)}")
print(f"\nBaseline (Mock) Results:")
print(f"  MCCS (Direction Accuracy): {mccs:.4f} ({mccs*100:.1f}%)")
print(f"  TCAE (Timing Error):       {tcae:.2f} hours")
print(f"  IEC (Magnitude Cal):       {iec:.4f}")

# Save results
results = {
    "benchmark": "causal_intervention_episodes_real",
    "timestamp": datetime.now().isoformat(),
    "n_episodes": len(episodes),
    "n_pairs": len(pairs),
    "results": [{
        "model": "mock",
        "backend": "mock",
        "prompt_style": "baseline",
        "mccs": float(mccs),
        "tcae": float(tcae),
        "iec": float(iec),
        "timestamp": datetime.now().isoformat()
    }]
}

with open(OUTPUTS_DIR / "benchmark_results_mock.json", "w") as f:
    json.dump(results, f, indent=2)

print(f"\n✓ Results saved to outputs/benchmark_results_mock.json")
print(f"\nInterpretation:")
print(f"  • MCCS {mccs:.1%}: Model gets direction right {mccs*100:.0f}% of time")
print(f"  • TCAE {tcae:.0f}h: Timing predictions are {tcae:.0f} hours off")
print(f"  • IEC {iec:.4f}: Magnitude calibration {'good' if iec < 0.05 else 'acceptable' if iec < 0.2 else 'poor'}")
