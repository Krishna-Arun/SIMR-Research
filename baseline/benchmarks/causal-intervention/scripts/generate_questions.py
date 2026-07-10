"""
generate_questions.py

Generate clinical question stems for the causal benchmark.

For each matched pair, create:
1. Question stem (clinical scenario)
2. Ground truth trajectory
3. Evaluation rubric
"""

import json
from pathlib import Path
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Paths
DATA_DIR = Path(__file__).parent.parent / "data"
PAIRS_FILE = DATA_DIR / "matched_pairs.json"
EPISODES_FILE = DATA_DIR / "episodes.json"
OUTPUT_DIR = DATA_DIR
QUESTIONS_FILE = OUTPUT_DIR / "questions.json"

# Intervention descriptions for clinical context
INTERVENTION_DESCRIPTIONS = {
    "pci": {
        "full_name": "Percutaneous Coronary Intervention (PCI / Angioplasty)",
        "description": "Catheter-based procedure to open blocked coronary arteries",
        "expected_effect": "Troponin should fall as myocardial damage is limited",
        "expected_timing": "2-6 hours",
    },
    "observation": {
        "full_name": "Observation Only (No Intervention)",
        "description": "Patient monitored without procedural intervention",
        "expected_effect": "Depends on natural course of disease",
        "expected_timing": "Variable",
    },
    "vasopressor_norepi": {
        "full_name": "Vasopressor Support (Norepinephrine)",
        "description": "Medication to increase blood pressure in cardiogenic shock",
        "expected_effect": "May stabilize or slow troponin rise",
        "expected_timing": "Minutes to 1 hour",
    },
    "antibiotic_betalactam": {
        "full_name": "Beta-lactam Antibiotics",
        "description": "Treatment for bacterial infection (pneumonia, sepsis)",
        "expected_effect": "Slow improvement if infection-driven troponin elevation",
        "expected_timing": "24-72 hours",
    },
}


def format_labs_for_question(labs: list, max_labs: int = 15) -> str:
    """Format lab measurements for clinical question."""
    if not labs:
        return "No lab data available"

    # Take last N labs
    recent_labs = labs[-max_labs:]

    lines = []
    lines.append("| Time | Test | Value | Unit | Status |")
    lines.append("|------|------|-------|------|--------|")

    for lab in recent_labs:
        time_str = lab.get("datetime", "")[-5:]  # HH:MM
        test = lab.get("label", "?")[:12]
        value = f"{lab.get('value', 0):.2f}"
        unit = lab.get("unit", "")[:8]
        flag = lab.get("flag", "normal")
        lines.append(f"| {time_str} | {test} | {value} | {unit} | {flag} |")

    return "\n".join(lines)


def create_question(pair_idx: int, pair_data: dict, episodes: dict) -> dict:
    """Create a clinical question from a matched pair."""

    # Get episodes
    ep_a_id = pair_data["episode_a_id"]
    ep_b_id = pair_data["episode_b_id"]

    ep_a = episodes.get(ep_a_id)
    ep_b = episodes.get(ep_b_id)

    if not ep_a or not ep_b:
        return None

    # Extract info
    int_a = pair_data["intervention_a"]
    int_b = pair_data["intervention_b"]
    severity = pair_data["severity_match"]["bin"]

    # Get intervention descriptions
    int_a_desc = INTERVENTION_DESCRIPTIONS.get(
        int_a, {"full_name": int_a, "description": "Unknown intervention"}
    )
    int_b_desc = INTERVENTION_DESCRIPTIONS.get(
        int_b, {"full_name": int_b, "description": "Unknown intervention"}
    )

    # Format labs
    labs_a = ep_a.get("pre_context", {}).get("labs", [])
    labs_b = ep_b.get("pre_context", {}).get("labs", [])

    # Demographics
    demo_a = ep_a.get("demographics", {})
    demo_b = ep_b.get("demographics", {})

    # Clinical context
    clinical_a = ep_a.get("clinical_context", {})
    clinical_b = ep_b.get("clinical_context", {})

    # Get ground truth (post-trajectory)
    trop_a_data = ep_a.get("post_trajectory", {}).get("Troponin I", {})
    trop_b_data = ep_b.get("post_trajectory", {}).get("Troponin I", {})

    trop_a_values = trop_a_data.get("resampled_values", [])
    trop_b_values = trop_b_data.get("resampled_values", [])

    # Get baseline troponin
    baseline_a = [l["value"] for l in labs_a if l["label"] == "Troponin I"][-1] if any(
        l["label"] == "Troponin I" for l in labs_a
    ) else 0.0
    baseline_b = [l["value"] for l in labs_b if l["label"] == "Troponin I"][-1] if any(
        l["label"] == "Troponin I" for l in labs_b
    ) else 0.0

    # Create question
    question_id = f"question_{pair_idx:04d}"

    question = {
        "question_id": question_id,
        "pair_id": pair_data["pair_id"],
        "severity": severity,
        "difficulty": "medium",  # All are medium difficulty for now
        "scenario": {
            "case_a": {
                "patient_id": ep_a.get("patient_id", "Unknown"),
                "age": demo_a.get("age", "Unknown"),
                "gender": demo_a.get("gender", "Unknown"),
                "diagnoses": clinical_a.get("diagnoses", [])[:3],
                "medications": clinical_a.get("medications", [])[:3],
                "intervention": {
                    "type": int_a,
                    "name": int_a_desc["full_name"],
                    "description": int_a_desc["description"],
                },
                "lab_summary": format_labs_for_question(labs_a),
            },
            "case_b": {
                "patient_id": ep_b.get("patient_id", "Unknown"),
                "age": demo_b.get("age", "Unknown"),
                "gender": demo_b.get("gender", "Unknown"),
                "diagnoses": clinical_b.get("diagnoses", [])[:3],
                "medications": clinical_b.get("medications", [])[:3],
                "intervention": {
                    "type": int_b,
                    "name": int_b_desc["full_name"],
                    "description": int_b_desc["description"],
                },
                "lab_summary": format_labs_for_question(labs_b),
            },
        },
        "question_stem": f"""
You are a clinical AI evaluating trajectory predictions after medical interventions.

## Case A: {int_a_desc['full_name']}
**Patient:** {demo_a.get('age')}-year-old {demo_a.get('gender')}
**Diagnoses:** {', '.join(clinical_a.get('diagnoses', [])[:3]) or 'Not listed'}
**Current Medications:** {', '.join(clinical_a.get('medications', [])[:3]) or 'Not listed'}
**Intervention:** {int_a_desc['full_name']} - {int_a_desc['description']}

**Lab Timeline (last 48 hours):**
{format_labs_for_question(labs_a)}

Baseline Troponin I: {baseline_a:.3f} ng/mL

---

## Case B: {int_b_desc['full_name']}
**Patient:** {demo_b.get('age')}-year-old {demo_b.get('gender')}
**Diagnoses:** {', '.join(clinical_b.get('diagnoses', [])[:3]) or 'Not listed'}
**Current Medications:** {', '.join(clinical_b.get('medications', [])[:3]) or 'Not listed'}
**Intervention:** {int_b_desc['full_name']} - {int_b_desc['description']}

**Lab Timeline (last 48 hours):**
{format_labs_for_question(labs_b)}

Baseline Troponin I: {baseline_b:.3f} ng/mL

---

## Question

Both patients have similar baseline conditions and lab trajectories leading up to these different interventions.

**Predict:** Will Case A's troponin trajectory differ from Case B's over the next 48 hours?

**Specifically:**
1. Which patient's troponin will change more (fall/rise/stay stable)?
2. Approximately how much change do you expect in each case?
3. When (how many hours) will you expect to see the intervention effect?

Provide your reasoning based on the intervention type and expected physiological effects.
""",
        "ground_truth": {
            "case_a": {
                "baseline": round(baseline_a, 4),
                "trajectory_48h": [round(v, 4) for v in trop_a_values[:96]]
                if trop_a_values
                else [],
                "final_value": round(trop_a_values[-1], 4) if trop_a_values else baseline_a,
                "direction": "rising" if trop_a_values and trop_a_values[-1] > baseline_a else (
                    "falling" if trop_a_values else "unknown"
                ),
                "change": round(
                    (trop_a_values[-1] - baseline_a) if trop_a_values else 0, 4
                ),
            },
            "case_b": {
                "baseline": round(baseline_b, 4),
                "trajectory_48h": [round(v, 4) for v in trop_b_values[:96]]
                if trop_b_values
                else [],
                "final_value": round(trop_b_values[-1], 4) if trop_b_values else baseline_b,
                "direction": "rising" if trop_b_values and trop_b_values[-1] > baseline_b else (
                    "falling" if trop_b_values else "unknown"
                ),
                "change": round(
                    (trop_b_values[-1] - baseline_b) if trop_b_values else 0, 4
                ),
            },
            "causal_comparison": {
                "case_a_improved_more": (trop_a_values[-1] < baseline_a if trop_a_values else False),
                "case_b_improved_more": (trop_b_values[-1] < baseline_b if trop_b_values else False),
                "magnitude_difference": round(
                    abs((trop_a_values[-1] - baseline_a) - (trop_b_values[-1] - baseline_b))
                    if trop_a_values and trop_b_values
                    else 0,
                    4,
                ),
            },
        },
        "evaluation_rubric": {
            "direction_accuracy": {
                "weight": 0.40,
                "description": "Did model predict the correct direction of change for each case?",
                "criteria": [
                    "Case A direction correct (±20%)",
                    "Case B direction correct (±20%)",
                ],
            },
            "causal_comparison": {
                "weight": 0.40,
                "description": "Did model correctly predict which case would change more?",
                "criteria": [
                    "Correctly identified which trajectory is larger",
                    "Reasoning mentions intervention effect",
                ],
            },
            "timing_estimate": {
                "weight": 0.15,
                "description": "Did model estimate reasonable timing for intervention effect?",
                "criteria": [
                    f"For {int_a}: expected within typical range",
                    f"For {int_b}: expected within typical range",
                ],
            },
            "clinical_reasoning": {
                "weight": 0.05,
                "description": "Is the reasoning clinically sound?",
                "criteria": [
                    "References intervention mechanism",
                    "Considers patient severity and comorbidities",
                ],
            },
        },
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "intervention_a_type": int_a,
            "intervention_b_type": int_b,
            "expected_effect_a": int_a_desc.get("expected_effect", "Unknown"),
            "expected_effect_b": int_b_desc.get("expected_effect", "Unknown"),
            "expected_timing_a": int_a_desc.get("expected_timing", "Unknown"),
            "expected_timing_b": int_b_desc.get("expected_timing", "Unknown"),
        },
    }

    return question


def main():
    logger.info("Loading data...")

    # Load pairs
    with open(PAIRS_FILE) as f:
        pairs_data = json.load(f)
    pairs = pairs_data["pairs"]
    logger.info(f"Loaded {len(pairs)} matched pairs")

    # Load episodes
    with open(EPISODES_FILE) as f:
        episodes_data = json.load(f)
    episodes = {ep["episode_id"]: ep for ep in episodes_data["episodes"]}
    logger.info(f"Loaded {len(episodes)} episodes")

    # Generate questions
    logger.info("Generating questions...")
    questions = []

    for i, pair in enumerate(pairs):
        try:
            question = create_question(i + 1, pair, episodes)
            if question:
                questions.append(question)
                if (i + 1) % 10 == 0:
                    logger.info(f"  Generated {i + 1}/{len(pairs)} questions...")
        except Exception as e:
            logger.error(f"Error generating question for pair {pair.get('pair_id')}: {e}")

    logger.info(f"Successfully generated {len(questions)} questions")

    # Count by intervention type
    int_pairs = {}
    for q in questions:
        key = tuple(
            sorted(
                [q["metadata"]["intervention_a_type"], q["metadata"]["intervention_b_type"]]
            )
        )
        int_pairs[str(key)] = int_pairs.get(str(key), 0) + 1

    logger.info(f"Intervention pair distribution: {int_pairs}")

    # Save
    manifest = {
        "name": "causal_intervention_questions_v1",
        "description": "Clinical question stems for causal intervention benchmark",
        "n_questions": len(questions),
        "intervention_pairs": int_pairs,
        "generated_at": datetime.now().isoformat(),
        "questions": questions,
    }

    with open(QUESTIONS_FILE, "w") as f:
        json.dump(manifest, f, indent=2)

    logger.info(f"Saved {len(questions)} questions to {QUESTIONS_FILE}")

    # Print sample
    if questions:
        logger.info("\n" + "=" * 60)
        logger.info("SAMPLE QUESTION:")
        logger.info("=" * 60)
        q = questions[0]
        print(q["question_stem"])
        print("\n[GROUND TRUTH - NOT SHOWN TO MODEL]")
        print(f"Case A: {q['ground_truth']['case_a']['direction']} by {q['ground_truth']['case_a']['change']:.4f}")
        print(f"Case B: {q['ground_truth']['case_b']['direction']} by {q['ground_truth']['case_b']['change']:.4f}")


if __name__ == "__main__":
    main()
