import json, sys
from pathlib import Path

BENCH = Path(__file__).parent
sys.path.insert(0, str(BENCH / "models"))

with open(BENCH / "data/episodes.json") as f:
    data = json.load(f)
episodes = {ep["episode_id"]: ep for ep in data["episodes"]}

with open(BENCH / "data/matched_pairs.json") as f:
    mp = json.load(f)

# Find a clean pci_vs_control pair where both episodes have Troponin T
pair = None
for p in mp["pairs"]:
    if p["contrast"] == "pci_vs_control" and "Troponin T" in p.get("scored_markers", []):
        ep_a = episodes.get(p["episode_a_id"])
        ep_b = episodes.get(p["episode_b_id"])
        if ep_a and ep_b:
            pair = p
            break

ep_id = pair["episode_a_id"]
episode = episodes[ep_id]

from llm_inference import HuggingFaceLLMPredictor

class FakePredictor(HuggingFaceLLMPredictor):
    def __init__(self):
        self.model_name = "microsoft/phi-4"
        self.prompt_style = "zero_shot"
    def predict(self, ep):
        pass

pred = FakePredictor()
prompt_zero = pred.build_prompt_zero_shot(episode)
prompt_cot  = pred.build_prompt_cot(episode)

print("=" * 80)
print("PAIR INFO")
print("=" * 80)
print(f"Pair ID:     {pair['pair_id']}")
print(f"Contrast:    {pair['contrast']}")
print(f"Episode A:   {pair['episode_a_id']}  (intervention: {pair['intervention_a']})")
print(f"Episode B:   {pair['episode_b_id']}  (intervention: {pair['intervention_b']})")
print(f"Scored on:   {pair['scored_markers']}")
print()

print("=" * 80)
print("FULL PROMPT SENT TO MODEL (zero_shot)")
print("=" * 80)
print(prompt_zero)

print()
print("=" * 80)
print("FULL PROMPT SENT TO MODEL (cot)")
print("=" * 80)
print(prompt_cot)

print()
print("=" * 80)
print("GROUND TRUTH LABELS")
print("=" * 80)

def get_series(vals):
    if isinstance(vals, dict):
        vals = vals.get("resampled_values", [])
    return [float(v["value"]) if isinstance(v, dict) else float(v) for v in vals]

for marker in episode["post_trajectory"]["markers"]:
    pre_vals = get_series(episode["pre_context"]["markers"].get(marker, []))
    post_vals = get_series(episode["post_trajectory"]["markers"][marker])
    if not pre_vals or not post_vals:
        continue
    a, b = pre_vals[-1], post_vals[-1]
    ch = (b - a) / abs(a) if a else (b - a)
    direction = "stable" if abs(ch) < 0.15 else ("falling" if ch < 0 else "rising")
    window_h = episode.get("pre_context", {}).get("window_hours", 48)
    n = len(post_vals)
    step = window_h / n
    timepoints = [f"{step*i:.0f}h" for i in range(1, n+1)]
    print(f"\nMarker: {marker}")
    print(f"  Pre-window final value : {a:.4f}")
    print(f"  Post-window trajectory : {[round(x, 4) for x in post_vals]}")
    print(f"  Timepoints             : {timepoints}")
    print(f"  Post-window final value: {b:.4f}")
    print(f"  % change               : {ch*100:.1f}%")
    print(f"  Ground truth direction : {direction.upper()}")

print()
print("=" * 80)
print("WHAT THE BENCHMARK CHECKS (MCCS)")
print("=" * 80)
ep_b = episodes[pair["episode_b_id"]]
for marker in pair["scored_markers"]:
    pre_a = get_series(episode["pre_context"]["markers"].get(marker, []))
    post_a = get_series(episode["post_trajectory"]["markers"].get(marker, []))
    pre_b = get_series(ep_b["pre_context"]["markers"].get(marker, []))
    post_b = get_series(ep_b["post_trajectory"]["markers"].get(marker, []))
    if not post_a or not post_b:
        continue
    actual_diff = post_a[-1] - post_b[-1]
    direction = "A improved MORE than B" if actual_diff < 0 else "B improved MORE than A"
    print(f"\nMarker: {marker}")
    print(f"  Arm A ({pair['intervention_a']}) post-final : {post_a[-1]:.4f}")
    print(f"  Arm B ({pair['intervention_b']}) post-final : {post_b[-1]:.4f}")
    print(f"  Actual diff (A - B)    : {actual_diff:.4f}")
    print(f"  Correct answer (MCCS)  : sign({'negative' if actual_diff < 0 else 'positive'}) → model must predict A_final {'<' if actual_diff < 0 else '>'} B_final")
    print(f"  Interpretation         : {direction}")
