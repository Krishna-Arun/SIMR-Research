"""
translate_cases.py

Takes candidate_cases.json and produces species-translated versions.
For each case, generates 3 translated variants:
  - dog         (real species, some veterinary training data exists)
  - horse       (real species, minimal training data for CVD)
  - velox_noctis (fictional, zero training data — pure reasoning test)

Translation method: z-score preservation
  z = (human_value - human_mean) / human_sd
  animal_value = animal_mean + z * animal_sd

Output: species-benchmark/data/translated_cases.json
         species-benchmark/data/benchmark_cases_sampled.json  (top 50 curated cases)
"""

import json
import math
from pathlib import Path
from collections import defaultdict

DATA_PATH = Path("/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/species-benchmark/data")
REF_PATH  = Path("/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/species-benchmark/reference_ranges")

# ── Load species reference ranges ──────────────────────────────────────────────
with open(REF_PATH / "species_reference_ranges.json") as f:
    SPECIES_REF = json.load(f)["species"]

# ── Load candidate cases ────────────────────────────────────────────────────────
with open(DATA_PATH / "candidate_cases.json") as f:
    raw = json.load(f)

CASES = raw["cases"]
print(f"Loaded {len(CASES)} candidate cases")


def translate_value(lab_name, human_value, target_species):
    """
    Translate a human lab value to the target species using z-score preservation.
    Returns None if lab not found in either species reference.
    """
    human_ref  = SPECIES_REF["human"]["labs"].get(lab_name)
    target_ref = SPECIES_REF[target_species]["labs"].get(lab_name)

    if not human_ref or not target_ref:
        return None

    z = (human_value - human_ref["mean"]) / human_ref["sd"]
    translated = target_ref["mean"] + z * target_ref["sd"]

    # Round to same precision as the original
    if human_value == int(human_value):
        translated = round(translated, 0)
    else:
        translated = round(translated, 1)

    return {
        "value":         translated,
        "z_score":       round(z, 2),
        "unit":          target_ref["unit"],
        "ref_low":       target_ref["low"],
        "ref_high":      target_ref["high"],
        "is_abnormal":   translated < target_ref["low"] or translated > target_ref["high"],
        "direction":     "HIGH" if translated > target_ref["high"]
                         else ("LOW" if translated < target_ref["low"] else "NORMAL"),
        "human_value":   human_value,
        "human_unit":    SPECIES_REF["human"]["labs"][lab_name]["unit"],
    }


def translate_threshold_hit(hit, target_species):
    """Translate a threshold-crossing event to a species-specific equivalent."""
    lab_name  = hit["lab"]
    human_val = hit["value"]

    target_ref = SPECIES_REF[target_species]["labs"].get(lab_name)
    human_ref  = SPECIES_REF["human"]["labs"].get(lab_name)

    if not target_ref or not human_ref:
        return None

    z = (human_val - human_ref["mean"]) / human_ref["sd"]
    translated_val = target_ref["mean"] + z * target_ref["sd"]

    # Translate the threshold too
    human_thresh = hit["threshold"]
    z_thresh = (human_thresh - human_ref["mean"]) / human_ref["sd"]
    translated_thresh = target_ref["mean"] + z_thresh * target_ref["sd"]

    return {
        "lab":                   lab_name,
        "species_value":         round(translated_val, 1),
        "species_threshold":     round(translated_thresh, 1),
        "species_ref_low":       target_ref["low"],
        "species_ref_high":      target_ref["high"],
        "species_unit":          target_ref["unit"],
        "direction":             hit["direction"],
        "action_label":          hit["action_label"],
        "action_detail":         hit["action_detail"],
        "z_score":               round(z, 2),
    }


def make_species_case(human_case, target_species, case_id):
    """Produce a complete species-translated case object."""
    species_info = SPECIES_REF[target_species]

    # Translate all labs in the panel
    translated_panel = {}
    for lab_name, lab_data in human_case["lab_panel"].items():
        result = translate_value(lab_name, lab_data["value"], target_species)
        if result:
            translated_panel[lab_name] = result

    if len(translated_panel) < 3:
        return None

    # Translate the primary threshold hit
    primary_translated = translate_threshold_hit(human_case["primary_action"], target_species)
    if not primary_translated:
        return None

    # Translate all threshold hits
    all_hits_translated = [
        h for h in [translate_threshold_hit(h, target_species) for h in human_case["all_threshold_hits"]]
        if h is not None
    ]

    # Compute patient approximate age
    demographics = human_case.get("demographics", {})
    birth_year   = demographics.get("birth_year", 1960)
    window_year  = int(human_case["window_date"][:4])
    human_age    = window_year - birth_year
    gender       = demographics.get("gender", "Unknown")

    # Scale age to species lifespan
    species_ages = {
        "dog":          max(1, round(human_age / 7)),     # ~7 dog years per human year
        "horse":        max(1, round(human_age / 3.5)),   # horses live ~30yr, humans ~80yr
        "velox_noctis": max(1, round(human_age * 0.4)),   # fictional: shorter lifespan
    }
    species_age = species_ages.get(target_species, human_age)

    # Map human gender to species-appropriate term
    gender_map = {
        "dog":   {"M": "intact male", "F": "intact female", "Unknown": "adult"},
        "horse": {"M": "gelding",     "F": "mare",          "Unknown": "adult"},
        "velox_noctis": {"M": "male", "F": "female",        "Unknown": "adult"},
    }
    species_gender = gender_map.get(target_species, {}).get(gender, "adult")

    # Get medication equivalents if available
    med_equiv = species_info.get("medication_equivalents", {})

    return {
        "case_id":             case_id,
        "species":             target_species,
        "species_common_name": species_info["common_name"],
        "tier":                1 if target_species == "dog" else (2 if target_species == "horse" else 3),
        "human_subject_id":    human_case["subject_id"],
        "window_date":         human_case["window_date"],

        "patient": {
            "species":         species_info["common_name"],
            "age_years":       species_age,
            "sex":             species_gender,
            "human_diagnoses": human_case["diagnoses"],
        },

        "lab_panel":           translated_panel,
        "n_labs":              len(translated_panel),

        "reference_ranges_provided": {
            lab: {
                "unit":  SPECIES_REF[target_species]["labs"][lab]["unit"],
                "low":   SPECIES_REF[target_species]["labs"][lab]["low"],
                "high":  SPECIES_REF[target_species]["labs"][lab]["high"],
            }
            for lab in translated_panel
            if lab in SPECIES_REF[target_species]["labs"]
        },

        "primary_action":      primary_translated,
        "all_threshold_hits":  all_hits_translated,
        "n_threshold_hits":    len(all_hits_translated),

        "medication_equivalents": med_equiv,

        "scoring": {
            "correct_action_label":  primary_translated["action_label"],
            "correct_action_detail": primary_translated["action_detail"],
            "pivot_lab":             primary_translated["lab"],
            "pivot_value":           primary_translated["species_value"],
            "pivot_threshold":       primary_translated["species_threshold"],
            "pivot_direction":       primary_translated["direction"],
            "pivot_unit":            primary_translated["species_unit"],
        }
    }


def main():
    TARGET_SPECIES = ["velox_noctis"]

    # Action diversity: select top N cases from each action category
    CASES_PER_ACTION = 5
    by_action = defaultdict(list)
    for case in CASES:
        action = case["primary_action"]["action_label"]
        by_action[action].append(case)

    # Priority actions for the benchmark
    PRIORITY_ACTIONS = [
        "emergent_rrt",
        "acs_pathway",
        "prbc_transfusion",
        "hf_decompensation",
        "potassium_repletion",
        "anticoagulation_reversal",
        "nephrology_consult",
        "diabetes_intensification",
        "dka_hhs_protocol",
        "severe_hyponatremia",
    ]

    selected_human_cases = []
    for action in PRIORITY_ACTIONS:
        pool = by_action.get(action, [])
        # Sort by richness (most labs + most threshold hits)
        pool.sort(key=lambda c: (c["n_threshold_hits"], c["n_labs"]), reverse=True)
        selected_human_cases.extend(pool[:CASES_PER_ACTION])

    print(f"Selected {len(selected_human_cases)} human cases across {len(PRIORITY_ACTIONS)} action types")

    # Translate each to all target species
    translated = []
    case_id = 1

    for human_case in selected_human_cases:
        for species in TARGET_SPECIES:
            result = make_species_case(human_case, species, case_id)
            if result:
                translated.append(result)
                case_id += 1

    print(f"Produced {len(translated)} translated cases "
          f"({len(translated)//len(TARGET_SPECIES)} human cases × {len(TARGET_SPECIES)} species)")

    # Stats
    by_species = defaultdict(int)
    by_action  = defaultdict(int)
    for c in translated:
        by_species[c["species"]] += 1
        by_action[c["scoring"]["correct_action_label"]] += 1

    print("\nBy species:", dict(by_species))
    print("By action:")
    for action, count in sorted(by_action.items(), key=lambda x: -x[1]):
        print(f"  {action:35s}: {count}")

    # Save full translated set
    with open(DATA_PATH / "translated_cases.json", "w") as f:
        json.dump({"n_cases": len(translated), "cases": translated}, f, indent=2)

    # Save a clean benchmark sample (top 30 cases: 10 human × 3 species)
    benchmark_sample = []
    seen_human = defaultdict(int)
    for c in translated:
        action = c["scoring"]["correct_action_label"]
        if seen_human[action] < 3:
            benchmark_sample.append(c)
            seen_human[action] += 1

    with open(DATA_PATH / "benchmark_cases_sampled.json", "w") as f:
        json.dump({"n_cases": len(benchmark_sample), "cases": benchmark_sample}, f, indent=2)

    print(f"\nSaved {len(translated)} translated cases to translated_cases.json")
    print(f"Saved {len(benchmark_sample)} benchmark sample cases to benchmark_cases_sampled.json")

    # Print one example case
    example = next((c for c in translated if c["species"] == "velox_noctis"), translated[0])
    print(f"\n── Example case (species={example['species']}, action={example['scoring']['correct_action_label']}) ──")
    print(f"  Patient: {example['patient']['age_years']}yr {example['patient']['sex']} {example['patient']['species']}")
    print(f"  Labs ({example['n_labs']}):")
    for lab, data in list(example["lab_panel"].items())[:6]:
        flag = f"[{data['direction']}]" if data["is_abnormal"] else ""
        ref = f"ref {data['ref_low']}–{data['ref_high']} {data['unit']}"
        print(f"    {lab:20s}: {data['value']} {data['unit']:10s} {flag:6s}  ({ref})")
    print(f"  Correct action: {example['scoring']['correct_action_label']}")
    print(f"  Pivot lab: {example['scoring']['pivot_lab']} = {example['scoring']['pivot_value']} "
          f"(threshold: {example['scoring']['pivot_direction']} {example['scoring']['pivot_threshold']} "
          f"{example['scoring']['pivot_unit']})")


if __name__ == "__main__":
    main()
