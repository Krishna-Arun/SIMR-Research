"""
build_benchmark.py

Converts translated_cases.json into the final benchmark JSON format
with human-readable question stems ready for agent evaluation.
The stem presents ALL lab values + species reference ranges upfront
(no tool calls needed — agent reads and reasons directly).

Output: species-benchmark/output/species_benchmark_v1.json
"""

import json
from pathlib import Path
from collections import defaultdict

DATA_PATH   = Path("/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/species-benchmark/data")
OUTPUT_PATH = Path("/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/species-benchmark/output")
REF_PATH    = Path("/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/species-benchmark/reference_ranges")
OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

with open(DATA_PATH / "translated_cases.json") as f:
    raw = json.load(f)


TRANSLATED = raw["cases"]

ACTION_LABELS = {
    "emergent_rrt":             "Emergent Renal Replacement Therapy",
    "acs_pathway":              "Acute Coronary Syndrome Pathway (Cardiology Consult / PCI)",
    "prbc_transfusion":         "Packed Red Blood Cell Transfusion",
    "hf_decompensation":        "Heart Failure Decompensation Protocol (IV Diuresis)",
    "potassium_repletion":      "Potassium Repletion (IV/Oral) and Diuretic Adjustment",
    "anticoagulation_reversal": "Anticoagulation Reversal (Vitamin K / PCC / FFP)",
    "nephrology_consult":       "Urgent Nephrology Consultation",
    "diabetes_intensification": "Diabetes Management Intensification",
    "dka_hhs_protocol":         "DKA / HHS Protocol (Insulin Infusion + IV Fluids)",
    "severe_hyponatremia":      "Hypertonic Saline for Severe Hyponatremia",
    "ckd_stage4_management":    "CKD Stage 4 Management Protocol",
    "thrombocytopenia_management": "Thrombocytopenia Management",
    "hypernatremia_correction": "Hypernatremia Correction (Free Water Replacement)",
    "lipid_treatment":          "Lipid-Lowering Therapy Initiation or Intensification",
    "statin_intensification":   "Statin Intensification",
    "metabolic_acidosis_workup":"Metabolic Acidosis Workup and Management",
}

WRONG_ANSWERS = {
    "emergent_rrt":             ["IV fluid bolus", "dietary potassium restriction", "oral kayexalate only", "observation and recheck"],
    "acs_pathway":              ["increase diuresis", "start anticoagulation only", "discharge with follow-up", "IV fluids"],
    "prbc_transfusion":         ["oral iron supplementation", "vitamin B12 injection", "watchful waiting", "erythropoietin only"],
    "hf_decompensation":        ["fluid bolus", "hold all diuretics", "discharge home", "increase sodium intake"],
    "potassium_repletion":      ["furosemide dose increase", "hold ACE inhibitor only", "sodium restriction", "observation"],
    "anticoagulation_reversal": ["increase anticoagulant dose", "add antiplatelet", "observation for 24h", "IV heparin switch"],
    "nephrology_consult":       ["discharge with primary care follow-up", "start NSAIDs", "IV contrast CT scan", "aggressive IV fluids only"],
    "diabetes_intensification": ["dietary counseling only", "hold all medications", "discharge", "low-sodium diet"],
    "dka_hhs_protocol":         ["oral glucose tablet", "subcutaneous insulin only", "observation", "high-carbohydrate diet"],
    "severe_hyponatremia":      ["water restriction only", "normal saline bolus", "furosemide", "discharge home"],
}


def format_lab_table(lab_panel, ref_ranges):
    """Format lab values with reference ranges but no pre-computed abnormality flags."""
    lines = []
    lines.append(f"{'Lab Test':<22} {'Value':>10}  {'Unit':<12}  {'Reference Range'}")
    lines.append("-" * 68)
    for lab, data in sorted(lab_panel.items()):
        ref = ref_ranges.get(lab, {})
        ref_str = f"{ref.get('low','?')}–{ref.get('high','?')} {ref.get('unit','')}" if ref else "see context"
        unit = data.get("unit", "")
        lines.append(f"{lab:<22} {str(data['value']):>10}  {unit:<12}  {ref_str}")
    return "\n".join(lines)


def build_stem_from_panel(age, sex, lab_panel, ref_ranges):
    lab_table = format_lab_table(lab_panel, ref_ranges)
    return f"""SPECIES: Velox noctis (fictional)
PATIENT: {age}-year-old {sex}

LABORATORY PANEL:
{lab_table}

QUESTION:
What is the complete management strategy for this patient? Include the most urgent immediate action and the definitive treatment."""


def build_counterfactual_panel(lab_panel, ref_ranges, pivot_lab):
    """Return a copy of lab_panel with the pivot lab set to the VN-normal midpoint."""
    import copy
    cf_panel = copy.deepcopy(lab_panel)
    ref = ref_ranges.get(pivot_lab, {})
    if ref and pivot_lab in cf_panel:
        cf_val = round((ref["low"] + ref["high"]) / 2, 1)
        cf_panel[pivot_lab]["value"] = cf_val
    return cf_panel


def build_question_stem(case):
    species_name = case["species_common_name"]
    patient      = case["patient"]
    age          = patient["age_years"]
    sex          = patient["sex"]
    tier         = case["tier"]

    lab_table    = format_lab_table(case["lab_panel"], case["reference_ranges_provided"])

    if tier == 3:
        stem = build_stem_from_panel(age, sex, case["lab_panel"], case["reference_ranges_provided"])
    else:
        species_note = (
            f"Apply standard veterinary clinical guidelines for {species_name}. "
            f"Reference ranges specific to this species are provided in the lab table."
        )
        stem = f"""SPECIES: {species_name}
PATIENT: {age}-year-old {sex}

CLINICAL CONTEXT:
The patient presents to a clinical care facility for evaluation. The following complete laboratory panel has been drawn. All reference ranges for this species are provided.

COMPLETE LABORATORY PANEL:
{lab_table}

{species_note}

QUESTION:
Based solely on the laboratory values and reference ranges provided above, describe the COMPLETE management strategy for this patient — including both any immediate stabilizing measures AND the definitive treatment required.

Provide:
1. The immediate action (first minutes)
2. The definitive treatment (what ultimately resolves the underlying problem)
3. Which lab value(s) drove your decision and why
4. How each key lab compares explicitly to the provided reference range for this species"""

    return stem


def build_answer_rubric(case):
    scoring = case["scoring"]
    action_label = scoring["correct_action_label"]
    action_readable = ACTION_LABELS.get(action_label, action_label)

    correct_synonyms = [action_readable]
    if action_label == "emergent_rrt":
        correct_synonyms += ["renal replacement", "hemodialysis", "continuous renal replacement",
                             "CRRT", "dialysis", "emergent dialysis"]
    elif action_label == "acs_pathway":
        correct_synonyms += ["cardiology consult", "catheterization", "PCI",
                             "angiography", "troponin protocol", "cardiac workup"]
    elif action_label == "prbc_transfusion":
        correct_synonyms += ["transfusion", "blood transfusion", "packed red cells", "PRBC",
                             "transfuse", "RBC transfusion"]
    elif action_label == "anticoagulation_reversal":
        correct_synonyms += ["vitamin K", "PCC", "FFP", "reverse anticoagulation",
                             "hold warfarin", "reversal agent"]
    elif action_label == "dka_hhs_protocol":
        correct_synonyms += ["insulin infusion", "insulin drip", "DKA protocol", "HHS protocol",
                             "IV insulin", "fluid resuscitation with insulin"]
    elif action_label == "severe_hyponatremia":
        correct_synonyms += ["hypertonic saline", "3% saline", "sodium correction",
                             "hypertonic", "sodium repletion"]

    # VN-specific: add note about what the correct action really tests
    vn_note = None
    if action_label == "emergent_rrt":
        vn_note = "VN rule: triggered by BUN > 80 + eGFR_VN < 1.5, NOT by creatinine (hepatic marker in VN)"
    elif action_label == "prbc_transfusion":
        vn_note = "VN rule: transfusion indicated ONLY at Hgb < 4.5 (not < 7.0); Hgb 4.5–7.0 → IV iron + erythropoietic support only"
    elif action_label == "dka_hhs_protocol":
        vn_note = "VN rule: DKA protocol ONLY at glucose > 700; glucose 400–700 → subcutaneous insulin adjustment only"
    elif action_label == "severe_hyponatremia":
        vn_note = "VN rule: hypertonic saline ONLY at Na < 118 (not < 120); Na 118–132 → fluid restriction + oral repletion"

    wrong = WRONG_ANSWERS.get(action_label, [])

    return {
        "correct_action_label":    action_label,
        "correct_action_readable": action_readable,
        "correct_synonyms":        correct_synonyms,
        "wrong_answers":           wrong,
        "vn_rule_note":            vn_note,
        "pivot_lab":               scoring["pivot_lab"],
        "pivot_value":             scoring["pivot_value"],
        "pivot_threshold":         scoring["pivot_threshold"],
        "pivot_direction":         scoring["pivot_direction"],
        "pivot_unit":              scoring["pivot_unit"],
        "action_detail":           scoring["correct_action_detail"],
    }


def main():
    benchmark_cases = []

    for case in TRANSLATED:
        stem   = build_question_stem(case)
        rubric = build_answer_rubric(case)

        # Counterfactual: pivot lab set to VN-normal midpoint, everything else unchanged
        pivot_lab = rubric["pivot_lab"]
        patient   = case["patient"]
        cf_panel  = build_counterfactual_panel(
            case["lab_panel"], case["reference_ranges_provided"], pivot_lab
        )
        cf_pivot_val = cf_panel[pivot_lab]["value"] if pivot_lab in cf_panel else None
        cf_stem = build_stem_from_panel(
            patient["age_years"], patient["sex"], cf_panel, case["reference_ranges_provided"]
        )

        benchmark_cases.append({
            "case_id":        case["case_id"],
            "species":        case["species"],
            "tier":           case["tier"],
            "n_labs":         case["n_labs"],
            "action_label":   case["scoring"]["correct_action_label"],
            "question_stem":  stem,
            "counterfactual": {
                "question_stem":    cf_stem,
                "pivot_lab":        pivot_lab,
                "pivot_val_real":   rubric["pivot_value"],
                "pivot_val_cf":     cf_pivot_val,
                "pivot_range":      f"{case['reference_ranges_provided'].get(pivot_lab, {}).get('low','?')}–{case['reference_ranges_provided'].get(pivot_lab, {}).get('high','?')}",
                "expected_answer_change": True,
            },
            "rubric":         rubric,
            "lab_panel":      case["lab_panel"],
            "reference_ranges": case["reference_ranges_provided"],
            "metadata": {
                "human_subject_id": case["human_subject_id"],
                "window_date":      case["window_date"],
                "patient":          case["patient"],
            }
        })

    # Sort: tier 1 → 2 → 3 within each action group
    benchmark_cases.sort(key=lambda c: (c["action_label"], c["tier"]))

    # Re-assign sequential IDs
    for i, c in enumerate(benchmark_cases, start=1):
        c["case_id"] = i

    by_species = defaultdict(int)
    by_action  = defaultdict(int)
    by_tier    = defaultdict(int)
    for c in benchmark_cases:
        by_species[c["species"]] += 1
        by_action[c["action_label"]] += 1
        by_tier[c["tier"]] += 1

    print(f"Built {len(benchmark_cases)} benchmark cases")
    print(f"By species: {dict(by_species)}")
    print(f"By tier: {dict(by_tier)}")
    print(f"By action: {dict(sorted(by_action.items(), key=lambda x: -x[1]))}")

    output = {
        "benchmark_name":    "Species-Invariant Clinical Lab Reasoning Benchmark v1",
        "description":       (
            "Tests whether AI agents reason from provided lab values and reference ranges "
            "vs. memorizing human clinical patterns. Cases are translated to real and fictional "
            "animal species using z-score preservation. Tier 3 (Velox noctis) provides the "
            "strongest anti-memorization guarantee — no training data exists for this species."
        ),
        "n_cases":           len(benchmark_cases),
        "tiers": {
            "1": "Dog (Canis lupus familiaris) — real species, some veterinary training data",
            "2": "Horse (Equus caballus) — real species, minimal CVD training data",
            "3": "Velox noctis (fictional) — zero training data; reference ranges in-context only",
        },
        "scoring_rubric": {
            "correct_action":    "1.0 if answer matches correct_synonyms (case-insensitive substring); 0.0 otherwise",
            "pivot_lab_cited":   "1.0 if reasoning mentions pivot_lab by name",
            "threshold_compared":"1.0 if reasoning compares pivot_value to provided reference range (not a memorized human range)",
            "total":             "mean of 3 components; max 1.0",
        },
        "cases": benchmark_cases,
    }

    outfile = OUTPUT_PATH / "species_benchmark_v1.json"
    with open(outfile, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved benchmark to {outfile}")

    # Print a sample question stem
    sample = next((c for c in benchmark_cases if c["tier"] == 3), benchmark_cases[0])
    print(f"\n{'='*70}")
    print(f"SAMPLE CASE (tier={sample['tier']}, action={sample['action_label']})")
    print("="*70)
    print(sample["question_stem"])


if __name__ == "__main__":
    main()
