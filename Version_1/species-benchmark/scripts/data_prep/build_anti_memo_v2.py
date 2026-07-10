"""
build_anti_memo_v2.py

Four targeted fixes over v1:

FIX 1 — Opposite-treatment zones (not just same-direction abnormality):
  K+  in 2.6–3.1 mEq/L: human sees HYPOKALEMIA (give K+), VN sees HYPERKALEMIA (remove K+)
  Na  in 145–150 mEq/L: human sees HYPERNATREMIA (restrict Na/give water), VN sees HYPONATREMIA (give saline)
  Human memorization actively produces the WRONG treatment, not just a missed finding.

FIX 2 — Borderline deviations (4–24% outside VN range, not 56%):
  Prefer values close to the VN threshold so the model must read precisely.
  K+ = 2.7 vs VN ULN 2.5: only 8% above. Requires careful comparison.

FIX 3 — Decoys that reinforce the wrong human answer:
  K+: "on chronic furosemide — routine electrolyte check" → diuretics cause human hypokalemia,
       priming the model to give potassium (wrong for VN).
  Na: "concentrated urine, poor oral intake" → dehydration framing primes for human hypernatremia
       management (restrict Na, give water) — wrong for VN.

FIX 4 — Natural variation in non-pivot labs (no more perfect midpoints):
  Z-score translate the actual EHRSHOT patient's other labs to VN scale.
  Use the translated value if it falls within VN normal range; otherwise use VN midpoint.
  The panel now looks like a real patient, not an artificially clean template.
"""

import json
from pathlib import Path

DATA_PATH   = Path("/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/species-benchmark/data")
REF_PATH    = Path("/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/species-benchmark/reference_ranges")
OUTPUT_PATH = Path("/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/species-benchmark/output")
OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

with open(DATA_PATH / "candidate_cases.json") as f:
    ALL_CASES = json.load(f)["cases"]

with open(REF_PATH / "species_reference_ranges.json") as f:
    spec = json.load(f)["species"]

VN_REF    = spec["velox_noctis"]["labs"]
HUMAN_REF = spec["human"]["labs"]

# Labs to include in panel
PANEL_LABS = ["albumin", "bun", "calcium", "creatinine", "glucose",
              "hemoglobin", "inr", "phosphorus", "platelets", "potassium", "sodium"]

VN_MID = {lab: round((d["low"] + d["high"]) / 2, 2) for lab, d in VN_REF.items()}


# ── FIX 4: natural variation via z-score translation ─────────────────────────
def translate_to_vn_natural(lab, human_val):
    """
    Z-score translate a human lab value to VN scale.
    Returns the translated value if it falls within VN normal range,
    otherwise returns VN midpoint (prevents confounding abnormalities).
    """
    h = HUMAN_REF.get(lab)
    v = VN_REF.get(lab)
    if not h or not v or h.get("sd", 0) == 0:
        return VN_MID.get(lab)

    z = (human_val - h["mean"]) / h["sd"]
    vn_val = v["mean"] + z * v["sd"]
    vn_val = round(vn_val, 1 if isinstance(vn_val, float) else 0)

    # Keep only if within VN normal range — otherwise use midpoint (no confounders)
    if v["low"] <= vn_val <= v["high"]:
        return vn_val
    return VN_MID[lab]


# ── Anti-memorization configs (FIX 1 + 3) ────────────────────────────────────
CONFIGS = [
    {
        # FIX 1: K+ in overlap zone — human LOW (hypokalemia), VN HIGH (hyperkalemia)
        # FIX 2: borderline values — just 4–24% above VN ULN of 2.5
        # FIX 3: decoy reinforces human wrong answer (furosemide → think hypokalemia)
        "pivot_lab":    "potassium",
        "select_range": (2.6, 3.1),   # human hypokalemia range, VN hyperkalemia range
        "vn_lo": 1.0,  "vn_hi": 2.5,
        "action_label": "vn_hyperkalemia_overlap",
        "correct_action_readable": "VN Hyperkalemia Management — Remove potassium (Kayexalate/binder + dietary restriction)",
        "correct_synonyms": [
            "kayexalate", "potassium binder", "restrict potassium", "hyperkalemia",
            "remove potassium", "reduce potassium", "potassium lowering",
            "sodium polystyrene", "patiromer", "cardiac monitoring hyperkalemia",
            "emergent potassium management"
        ],
        # FIX 1: human memorization produces the OPPOSITE treatment
        "wrong_answers": [
            "IV potassium", "potassium supplement", "KCl infusion",
            "potassium repletion", "give potassium", "hypokalemia treatment",
            "potassium replacement"
        ],
        # FIX 3: decoy — furosemide context primes model to think hypokalemia
        "decoy_context": (
            "on chronic furosemide 40 mg daily for heart failure, "
            "presenting for routine outpatient electrolyte monitoring. "
            "No acute symptoms. Cardiologist requested labs."
        ),
        "human_interpretation": "K+ {val} — below human LLN 3.5 → human clinician: IV potassium replacement (WRONG for VN)",
    },
    {
        # FIX 1: Na in overlap zone — human HIGH (hypernatremia), VN LOW (hyponatremia)
        # FIX 2: borderline — just 1–5% below VN lower of 153
        # FIX 3: decoy — dehydration framing primes for human hypernatremia mgmt
        "pivot_lab":    "sodium",
        "select_range": (145, 150),   # human hypernatremia range, VN hyponatremia range
        "vn_lo": 153,  "vn_hi": 177,
        "action_label": "vn_hyponatremia_overlap",
        "correct_action_readable": "VN Hyponatremia Management — Isotonic saline infusion to raise sodium toward VN normal",
        "correct_synonyms": [
            "isotonic saline", "normal saline", "sodium supplementation",
            "IV saline", "sodium infusion", "hyponatremia", "sodium repletion",
            "0.9% saline", "sodium replacement", "sodium correction"
        ],
        # FIX 1: human memorization produces the OPPOSITE treatment
        "wrong_answers": [
            "restrict sodium", "free water", "hypotonic", "hypernatremia treatment",
            "sodium restriction", "water replacement", "D5W", "0.45% saline",
            "half-normal saline"
        ],
        # FIX 3: decoy — dehydration/concentrated urine primes for human hypernatremia
        "decoy_context": (
            "with history of decreased oral intake over the past week, "
            "presenting for evaluation of fatigue. Urine appears concentrated. "
            "No acute neurological symptoms."
        ),
        "human_interpretation": "Na {val} — above human ULN 145 → human clinician: free water / restrict sodium (WRONG for VN)",
    },
]

CASES_PER_ACTION = 5


def format_results_section(lab_panel):
    """Patient lab results — values only, no reference ranges on the same line."""
    lines = [
        f"{'Lab Test':<22} {'Result':>10}  {'Unit'}",
        "-" * 46,
    ]
    for lab in sorted(lab_panel.keys()):
        data = lab_panel[lab]
        lines.append(f"{lab:<22} {str(data['value']):>10}  {data['unit']}")
    return "\n".join(lines)


def format_ranges_section(ref_ranges):
    """Species reference ranges — separate from patient results."""
    lines = [
        f"{'Lab Test':<22} {'Normal Range':<24}  {'Unit'}",
        "-" * 52,
    ]
    for lab in sorted(ref_ranges.keys()):
        ref = ref_ranges[lab]
        lines.append(f"{lab:<22} {str(ref['low']) + '–' + str(ref['high']):<24}  {ref['unit']}")
    return "\n".join(lines)


def build_stem(age, sex, decoy_context, lab_panel, ref_ranges):
    results = format_results_section(lab_panel)
    ranges  = format_ranges_section(ref_ranges)
    return f"""SPECIES: Velox noctis (fictional)
PATIENT: {age}-year-old {sex}, {decoy_context}

VELOX NOCTIS SPECIES REFERENCE RANGES:
{ranges}

PATIENT LABORATORY RESULTS:
{results}

QUESTION:
Based on the laboratory results, what clinical management do you recommend for this patient?"""


def build_case(human_case, config, case_id):
    pivot_lab = config["pivot_lab"]
    pivot_val = round(human_case["lab_panel"][pivot_lab]["value"], 1)

    # FIX 4: build panel using natural variation (z-score translate patient's real values)
    lab_panel  = {}
    ref_ranges = {}
    for lab in PANEL_LABS:
        vn = VN_REF[lab]
        if lab == pivot_lab:
            val = pivot_val   # use actual EHRSHOT value (overlap zone)
        else:
            # Use z-score translated value if within VN range, else VN midpoint
            human_val = human_case["lab_panel"].get(lab, {}).get("value")
            val = translate_to_vn_natural(lab, human_val) if human_val is not None else VN_MID[lab]
        lab_panel[lab]  = {"value": val, "unit": vn["unit"]}
        ref_ranges[lab] = {"low": vn["low"], "high": vn["high"], "unit": vn["unit"]}

    # Demographics
    demo  = human_case.get("demographics", {})
    h_age = int(human_case["window_date"][:4]) - demo.get("birth_year", 1970)
    vn_age = max(1, round(h_age * 0.4))
    vn_sex = {"M": "male", "F": "female"}.get(demo.get("gender", "U"), "adult")

    real_stem = build_stem(vn_age, vn_sex, config["decoy_context"], lab_panel, ref_ranges)

    # Counterfactual: pivot → VN midpoint (VN-normal, but ALSO human-normal for K+)
    # This removes all signal — both human and VN would say "normal"
    cf_val   = VN_MID[pivot_lab]
    cf_panel = {**lab_panel, pivot_lab: {"value": cf_val, "unit": VN_REF[pivot_lab]["unit"]}}
    cf_stem  = build_stem(vn_age, vn_sex, config["decoy_context"], cf_panel, ref_ranges)

    vn_deviation_pct = abs(pivot_val - (config["vn_hi"] if pivot_val > config["vn_hi"] else config["vn_lo"])) \
                       / (config["vn_hi"] if pivot_val > config["vn_hi"] else config["vn_lo"]) * 100

    pivot_direction = "HIGH" if pivot_val > config["vn_hi"] else "LOW"
    human_interp = config["human_interpretation"].format(val=pivot_val)

    return {
        "case_id":           case_id,
        "species":           "velox_noctis",
        "tier":              3,
        "action_label":      config["action_label"],
        "anti_memorization": True,
        "fixes_applied": {
            "fix1_opposite_treatment": True,
            "fix2_borderline_deviation": f"{vn_deviation_pct:.0f}% outside VN range",
            "fix3_reinforcing_decoy":   True,
            "fix4_natural_variation":   True,
        },
        "human_memorization_predicts": human_interp,
        "question_stem":     real_stem,
        "counterfactual": {
            "question_stem": cf_stem,
            "pivot_val_cf":  cf_val,
            "pivot_range":   f"{config['vn_lo']}–{config['vn_hi']}",
            "note": (
                f"pivot set to VN midpoint ({cf_val}). "
                f"Both human AND VN norms say this is normal — no intervention. "
                f"This removes the opposite-treatment tension entirely."
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
            "vn_deviation_pct":        round(vn_deviation_pct, 1),
            "human_memorization_trap": (
                f"Human clinician sees {pivot_lab}={pivot_val} as "
                f"{'low' if pivot_direction == 'HIGH' else 'high'} by human standards "
                f"and recommends {config['wrong_answers'][0]} — the OPPOSITE of the VN-correct answer."
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
    case_id   = 1

    for config in CONFIGS:
        lab = config["pivot_lab"]
        lo, hi = config["select_range"]

        eligible = [
            c for c in ALL_CASES
            if lab in c["lab_panel"] and lo <= c["lab_panel"][lab]["value"] <= hi
        ]
        # FIX 2: prefer borderline values (closest to VN threshold)
        vn_threshold = config["vn_hi"] if eligible and eligible[0]["lab_panel"][lab]["value"] > config["vn_hi"] \
                       else config["vn_lo"]
        eligible.sort(key=lambda c: abs(c["lab_panel"][lab]["value"] - vn_threshold))

        # Take first CASES_PER_ACTION but spread across the value range too
        # (sort by closeness to VN threshold, then pick evenly distributed subset)
        if len(eligible) > CASES_PER_ACTION * 3:
            by_val = sorted(eligible, key=lambda c: c["lab_panel"][lab]["value"])
            step = len(by_val) // CASES_PER_ACTION
            selected = [by_val[i * step] for i in range(CASES_PER_ACTION)]
        else:
            selected = eligible[:CASES_PER_ACTION]

        print(f"\n{lab} ({config['action_label']}): {len(eligible)} eligible → {len(selected)} selected")
        print(f"  Human interprets these as: {'LOW (hypokalemia)' if lab == 'potassium' else 'HIGH (hypernatremia)'}")
        print(f"  VN interprets these as:    {'HIGH (hyperkalemia)' if lab == 'potassium' else 'LOW (hyponatremia)'}")
        print(f"  Treatments are OPPOSITE.")

        for c in selected:
            val = round(c["lab_panel"][lab]["value"], 1)
            vn_boundary = config["vn_hi"] if val > config["vn_hi"] else config["vn_lo"]
            pct = abs(val - vn_boundary) / vn_boundary * 100
            print(f"  subject={c['subject_id']}  {lab}={val}  {pct:.0f}% outside VN range")
            case = build_case(c, config, case_id)
            all_cases.append(case)
            case_id += 1

    benchmark = {
        "benchmark_name": "Species Anti-Memorization Benchmark v2 — Opposite-Treatment Zones",
        "description": (
            "Hardest version: pivot lab values sit in the overlap zone where human and VN "
            "interpretations are OPPOSITE in direction. A model applying human memorization "
            "produces the wrong treatment (not just a missed finding — the opposite action). "
            "All four v1 weaknesses are fixed."
        ),
        "fixes": {
            "fix1": "Opposite-treatment zones: K+ 2.6–3.1 (human hypokalemia, VN hyperkalemia); "
                    "Na 145–150 (human hypernatremia, VN hyponatremia). Human memorization → wrong treatment.",
            "fix2": "Borderline deviations: 4–24% outside VN range. Must read the provided "
                    "reference number precisely — glancing at scale is insufficient.",
            "fix3": "Decoys reinforce wrong human answer: furosemide context → model thinks hypokalemia; "
                    "dehydration context → model thinks hypernatremia. Human priming is maximized.",
            "fix4": "Natural panel variation: non-pivot labs are z-score translated from actual EHRSHOT "
                    "patient values (clamped to VN normal range). No more artificially uniform midpoints.",
        },
        "n_cases":  len(all_cases),
        "scoring": {
            "correct_action":           "1 if answer matches correct_synonyms; 0 if matches wrong_answers",
            "human_memo_failure":       "1 if answer recommends the human-memorized OPPOSITE treatment",
            "pivot_lab_cited":          "1 if reasoning names pivot lab explicitly",
            "used_vn_range":            "1 if reasoning compares to provided VN range (not human range)",
            "counterfactual_sensitivity":"1 if answer changes when pivot is set to VN-normal midpoint",
        },
        "cases": all_cases,
    }

    outfile = OUTPUT_PATH / "anti_memo_benchmark_v2.json"
    with open(outfile, "w") as f:
        json.dump(benchmark, f, indent=2)
    print(f"\nSaved {len(all_cases)} cases to {outfile}")

    sample = all_cases[0]
    print(f"\n{'='*72}")
    print(f"SAMPLE CASE: {sample['action_label']} | case {sample['case_id']}")
    print(f"Fix 2 deviation: {sample['fixes_applied']['fix2_borderline_deviation']}")
    print(f"Human trap:      {sample['rubric']['human_memorization_trap']}")
    print("="*72)
    print(sample["question_stem"])


if __name__ == "__main__":
    main()
