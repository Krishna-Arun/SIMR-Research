"""
build_anti_memo_cases.py

Builds the hardest version of the VN species benchmark.

Design principle:
  The pivot lab value is WITHIN human normal range — a human clinician
  would call it normal. But by VN species standards it is clearly abnormal.
  The model MUST read the provided reference ranges to detect the problem.
  Human memorization produces the wrong answer ("looks normal to me").

  All non-pivot labs are set to VN midpoints → zero gestalt fallback.
  The only signal is: pivot_value vs VN reference range in the table.

Anti-memorization pairs (human-normal → VN-abnormal):
  K+:  human 3.5–5.0  → all above VN ULN 2.5   (VN critical_high = 4.0)
  Na:  human 136–145  → all below VN lower 153   (VN critical_low  = 130)
  Cr:  human 0.6–1.2  → all above VN ULN 0.5    (VN critical_high = 1.5)
"""

import json
from pathlib import Path

DATA_PATH   = Path("/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/species-benchmark/data")
REF_PATH    = Path("/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/species-benchmark/reference_ranges")
OUTPUT_PATH = Path("/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/species-benchmark/output")
OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

with open(DATA_PATH / "candidate_cases.json") as f:
    CASES = json.load(f)["cases"]

with open(REF_PATH / "species_reference_ranges.json") as f:
    VN_REF = json.load(f)["species"]["velox_noctis"]["labs"]

# VN midpoints for every lab — used to zero out non-pivot labs
VN_MID = {
    lab: round((d["low"] + d["high"]) / 2, 2)
    for lab, d in VN_REF.items()
}

# Labs to include in every panel (subset of VN_REF that are clinically meaningful)
PANEL_LABS = ["albumin", "bun", "calcium", "creatinine", "glucose",
              "hemoglobin", "inr", "phosphorus", "platelets", "potassium", "sodium"]

ANTI_MEMO_CONFIGS = [
    {
        "pivot_lab":             "potassium",
        "human_normal":          (3.5, 5.0),
        "select_range":          (3.8, 4.9),   # solidly human-normal, clearly VN-abnormal
        "vn_lo":                 1.0,
        "vn_hi":                 2.5,
        "vn_critical":           4.0,          # above this → emergent
        "action_label":          "vn_hyperkalemia",
        "correct_action_readable": "Emergent VN Hyperkalemia Management (IV Calcium + Insulin-Dextrose)",
        "correct_synonyms": [
            "calcium gluconate", "IV calcium", "insulin dextrose", "kayexalate",
            "hyperkalemia", "potassium management", "potassium lowering",
            "cardiac stabilization", "emergent potassium"
        ],
        "wrong_answers": [
            "potassium is normal", "no intervention", "routine follow-up",
            "discharge without treatment", "no acute concern"
        ],
        "decoy_context": "presenting for a routine pre-operative medical clearance. No acute symptoms reported.",
    },
    {
        "pivot_lab":             "sodium",
        "human_normal":          (136, 145),
        "select_range":          (136, 143),   # solidly human-normal, clearly VN-low (VN lo=153)
        "vn_lo":                 153,
        "vn_hi":                 177,
        "vn_critical":           130,          # below this → emergent; above (but below 153) → moderate
        "action_label":          "vn_hyponatremia",
        "correct_action_readable": "Isotonic Saline Infusion for VN Hyponatremia",
        "correct_synonyms": [
            "isotonic saline", "normal saline", "sodium supplementation",
            "IV saline", "sodium infusion", "sodium repletion",
            "hyponatremia", "sodium correction", "sodium replacement"
        ],
        "wrong_answers": [
            "sodium is normal", "no intervention", "routine follow-up",
            "discharge without treatment", "no sodium concern"
        ],
        "decoy_context": "presenting for annual wellness evaluation. Vital signs stable, no acute complaints.",
    },
    {
        "pivot_lab":             "creatinine",
        "human_normal":          (0.5, 1.2),
        "select_range":          (0.6, 1.05),  # solidly human-normal, clearly above VN ULN 0.5
        "vn_lo":                 0.1,
        "vn_hi":                 0.5,
        "vn_critical":           1.5,
        "action_label":          "vn_renal_elevation",
        "correct_action_readable": "Nephrology Consultation for VN Creatinine Elevation",
        "correct_synonyms": [
            "nephrology", "nephrology consult", "renal evaluation", "renal workup",
            "kidney evaluation", "renal function", "creatinine elevated",
            "further renal testing", "renal consult"
        ],
        "wrong_answers": [
            "creatinine is normal", "no intervention", "routine follow-up",
            "discharge without treatment", "no renal concern"
        ],
        "decoy_context": "presenting for management of well-controlled hypertension. No urinary symptoms.",
    },
]

CASES_PER_ACTION = 5


def format_lab_table(lab_panel, ref_ranges):
    lines = [
        f"{'Lab Test':<22} {'Value':>10}  {'Unit':<12}  {'Reference Range'}",
        "-" * 68,
    ]
    for lab in sorted(lab_panel.keys()):
        data = lab_panel[lab]
        ref = ref_ranges.get(lab, {})
        ref_str = f"{ref['low']}–{ref['high']} {ref['unit']}" if ref else "see context"
        lines.append(f"{lab:<22} {str(data['value']):>10}  {data['unit']:<12}  {ref_str}")
    return "\n".join(lines)


def build_stem(age, sex, decoy_context, lab_panel, ref_ranges):
    lab_table = format_lab_table(lab_panel, ref_ranges)
    return f"""SPECIES: Velox noctis (fictional)
PATIENT: {age}-year-old {sex}, {decoy_context}

LABORATORY PANEL:
{lab_table}

QUESTION:
What is the complete management strategy for this patient? Include the most urgent immediate action and the definitive treatment."""


def build_case(human_case, config, case_id):
    pivot_lab = config["pivot_lab"]
    pivot_val = round(human_case["lab_panel"][pivot_lab]["value"], 1)

    # Lab panel: pivot = actual EHRSHOT human value, all others = VN midpoints
    lab_panel = {}
    ref_ranges = {}
    for lab in PANEL_LABS:
        vn = VN_REF[lab]
        val = pivot_val if lab == pivot_lab else VN_MID[lab]
        lab_panel[lab] = {"value": val, "unit": vn["unit"]}
        ref_ranges[lab] = {"low": vn["low"], "high": vn["high"], "unit": vn["unit"]}

    # Demographics
    demo  = human_case.get("demographics", {})
    h_age = int(human_case["window_date"][:4]) - demo.get("birth_year", 1970)
    vn_age = max(1, round(h_age * 0.4))
    vn_sex = {"M": "male", "F": "female"}.get(demo.get("gender", "U"), "adult")

    real_stem = build_stem(vn_age, vn_sex, config["decoy_context"], lab_panel, ref_ranges)

    # Counterfactual: pivot set to VN midpoint → everything VN-normal
    cf_val = VN_MID[pivot_lab]
    cf_panel = {**lab_panel, pivot_lab: {"value": cf_val, "unit": VN_REF[pivot_lab]["unit"]}}
    cf_stem  = build_stem(vn_age, vn_sex, config["decoy_context"], cf_panel, ref_ranges)

    pivot_direction = "HIGH" if pivot_val > config["vn_hi"] else "LOW"

    return {
        "case_id":              case_id,
        "species":              "velox_noctis",
        "tier":                 3,
        "action_label":         config["action_label"],
        "anti_memorization":    True,
        "question_stem":        real_stem,
        "counterfactual": {
            "question_stem":  cf_stem,
            "pivot_val_cf":   cf_val,
            "pivot_range":    f"{config['vn_lo']}–{config['vn_hi']}",
            "note": (
                f"pivot set to VN-normal midpoint ({cf_val}). "
                f"A human-memorizing model says 'normal' for BOTH conditions "
                f"because {pivot_val} and {cf_val} both look unremarkable by human standards."
            ),
        },
        "rubric": {
            "correct_action_label":    config["action_label"],
            "correct_action_readable": config["correct_action_readable"],
            "correct_synonyms":        config["correct_synonyms"],
            "wrong_answers":           config["wrong_answers"],
            "pivot_lab":               pivot_lab,
            "pivot_value":             pivot_val,
            "pivot_direction":         pivot_direction,
            "pivot_vn_range":          f"{config['vn_lo']}–{config['vn_hi']} {VN_REF[pivot_lab]['unit']}",
            "pivot_human_range":       f"{config['human_normal'][0]}–{config['human_normal'][1]} {VN_REF[pivot_lab]['unit']}",
            "anti_memo_note": (
                f"{pivot_lab}={pivot_val} is WITHIN human normal range "
                f"({config['human_normal'][0]}–{config['human_normal'][1]}) "
                f"but {pivot_direction} for VN (range {config['vn_lo']}–{config['vn_hi']}). "
                f"A model relying on human memorization will call this normal and miss the intervention."
            ),
        },
        "lab_panel":      lab_panel,
        "reference_ranges": ref_ranges,
        "metadata": {
            "human_subject_id": human_case["subject_id"],
            "window_date":      human_case["window_date"],
            "patient":          {"age_years": vn_age, "sex": vn_sex},
        },
    }


def main():
    all_cases = []
    case_id = 1

    for config in ANTI_MEMO_CONFIGS:
        lab   = config["pivot_lab"]
        lo, hi = config["select_range"]

        eligible = [
            c for c in CASES
            if lab in c["lab_panel"] and lo <= c["lab_panel"][lab]["value"] <= hi
        ]
        # Spread across the value range for diversity
        eligible.sort(key=lambda c: c["lab_panel"][lab]["value"])
        if len(eligible) <= CASES_PER_ACTION:
            selected = eligible
        else:
            indices = [round(i * (len(eligible) - 1) / (CASES_PER_ACTION - 1))
                       for i in range(CASES_PER_ACTION)]
            selected = [eligible[i] for i in indices]

        print(f"\n{lab} ({config['action_label']}): {len(eligible)} eligible → selecting {len(selected)}")
        for c in selected:
            val = round(c["lab_panel"][lab]["value"], 1)
            print(f"  subject={c['subject_id']}  {lab}={val}  "
                  f"[human-normal {config['human_normal'][0]}–{config['human_normal'][1]}] "
                  f"[VN range {config['vn_lo']}–{config['vn_hi']}] → VN-{'HIGH' if val > config['vn_hi'] else 'LOW'}")
            case = build_case(c, config, case_id)
            all_cases.append(case)
            case_id += 1

    benchmark = {
        "benchmark_name": "Species Anti-Memorization Benchmark v1",
        "description": (
            "Tests whether AI agents read and apply provided species-specific reference ranges "
            "vs. applying memorized human clinical norms. Every pivot lab value is within human "
            "normal range — a model using human memorization calls it normal and fails. "
            "A model that reads the VN reference range in the table detects the abnormality and "
            "recommends the correct intervention."
        ),
        "design": {
            "pivot_selection":  "Human-normal lab values that are VN-abnormal",
            "panel_design":     "All non-pivot labs set to VN midpoints — zero gestalt fallback",
            "decoy_context":    "Clinical stem implies routine/normal visit to maximize memorization pressure",
            "counterfactual":   "Pivot set to VN-normal midpoint; correct answer changes to 'no acute intervention'",
        },
        "anti_memo_pairs": {
            "potassium": "Human normal 3.5–5.0 mEq/L → all above VN ULN 2.5",
            "sodium":    "Human normal 136–145 mEq/L → all below VN lower 153",
            "creatinine":"Human normal 0.6–1.2 mg/dL → all above VN ULN 0.5",
        },
        "n_cases": len(all_cases),
        "scoring_rubric": {
            "correct_action":   "1 if answer matches correct_synonyms (case-insensitive substring match)",
            "pivot_lab_cited":  "1 if reasoning names the pivot lab by name",
            "used_vn_ranges":   "1 if reasoning explicitly compares pivot value to the VN reference range (not a human range)",
            "counterfactual_sensitivity": "1 if answer changes when pivot is set to VN-normal midpoint",
            "total":            "mean of 4 metrics; max 1.0",
        },
        "cases": all_cases,
    }

    outfile = OUTPUT_PATH / "anti_memo_benchmark_v1.json"
    with open(outfile, "w") as f:
        json.dump(benchmark, f, indent=2)
    print(f"\nSaved {len(all_cases)} cases to {outfile}")

    # Print a sample stem
    sample = all_cases[0]
    print(f"\n{'='*70}")
    print(f"SAMPLE CASE: {sample['action_label']} | case {sample['case_id']}")
    print(f"Anti-memo note: {sample['rubric']['anti_memo_note']}")
    print("="*70)
    print(sample["question_stem"])


if __name__ == "__main__":
    main()
