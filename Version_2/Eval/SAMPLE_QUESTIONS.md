# Sample Questions & Ground Truth — Benchmarks A / B / C

One representative item per benchmark, drawn from the generated set (gpt-oss-20B generator, real MIMIC-IV ICU patients, age < 89). Each shows what the agent sees (the **stem** — leak-free, no values up front) and the **ground truth** used for scoring.


---

## Benchmark A — Lab-request + causal Dx/Rx

**Question ID:** `qa_00000`  
**Scoring:** ruthless-mentor judge grades *lab-request* 0/0.5/1 and *answer* 0/0.5/1.

### What the agent sees (stem)

> An 82‑year‑old woman on chronic warfarin therapy presents for routine evaluation; determine the most likely cardiovascular-related cause of her laboratory abnormalities.

The agent gets **no lab values up front** — it must call `request_all_labs_no_values()`, then `request_a_lab(name, justification)` for each lab it wants, then `answer(...)`.

### Ground truth

**Reference answer:** Over‑anticoagulation due to warfarin therapy with an INR above therapeutic range.


**Gold labs the agent should request:**

- **INR(PT)** — high INR indicates over‑anticoagulation and potential bleeding risk in a patient on warfarin *(PMID 32228188: guidelines recommend monitoring INR to maintain therapeutic range in warfarin therapy)*
- **PT** — prolonged PT corroborates elevated INR and reflects vitamin K antagonist effect *(PMID 32228188: PT is used to monitor warfarin anticoagulation)*
- **PTT** — abnormal PTT can indicate concurrent heparin or factor deficiencies affecting coagulation *(PMID 32228188: PTT is monitored when heparin therapy is considered)*
- **Sodium** — hyponatremia may reflect fluid shifts or medication effects relevant to cardiovascular status *(PMID 32228188: electrolyte monitoring is essential in patients on diuretics and anticoagulants)*
- **White Blood Cells** — leukocytosis can signal infection or inflammatory response affecting cardiovascular risk *(PMID 32228188: WBC count is part of routine monitoring for infection in hospitalized patients)*

**Causal chain:** ["High INR -> excessive vitamin K antagonist effect -> increased bleeding risk", "Prolonged PT confirms INR elevation -> indicates need for dose adjustment", "Elevated INR in a patient on warfarin -> diagnosis of over\u2011anticoagulation"]


---

## Benchmark B — Post-procedure trajectory

**Question ID:** `qb_00000`  
**Procedure (time-zero):** Dialysis - CRRT  
**Scoring:** per-lab direction 1 / 0.5 / 0, deterministic vs data-derived truth + ECE on confidence.

### What the agent sees (stem)

> A 52‑year‑old man with acute kidney injury is undergoing continuous renal replacement therapy (CRRT) at time‑zero. His pre‑procedure labs are: Bicarbonate 24.0 mEq/L, Creatinine 3.0 mg/dL, Lactate 1.2 mmol/L, Platelet Count 338 K/µL, Potassium 4.6 mEq/L, Sodium 133 mEq/L, Urea Nitrogen 30 mg/dL. Predict the post‑procedure direction (Rising, Falling, or Stable) for each of the following core labs: Creatinine and Potassium.

The agent sees each target lab's **baseline** (pre-procedure) value but **not** the post value, and predicts Rising / Falling / Stable + confidence for each.

### Ground truth (per target lab)

| Lab | Baseline | True direction | Why (causal) |
|---|---|---|---|
| Creatinine | 3.0 mg/dL (ref 0.5–1.2) | **Falling** | CRRT removes creatinine from circulation, lowering serum levels in this patient with baseline elevation. |
| Potassium | 4.6 mEq/L (ref 3.3–5.1) | **Stable** | The dialysate composition (PrismaSol B32 K0) and CRRT settings maintain potassium within normal range, preventing significant change. |

---

## Benchmark C — Counterfactual (which patient?)

**Question ID:** `qc_00000`  
**Scoring:** 0/1 (correct patient) + ECE on confidence.

### What the agent sees (stem)

> Patient A underwent continuous renal replacement therapy (CRRT) and Patient B received non‑invasive ventilation. The following post‑procedure laboratory series was recorded: Bicarbonate 17.0→17.0→17.0→17.0→16.0→15.0→18.0→18.0→16.0→17.0→17.0→17.0, Creatinine 1.3→1.3→1.3→1.5→1.5→1.4→1.3→1.2→1.2→1.2→1.3, Lactate 1.6→1.6→1.3→1.3, Platelet Count 373.0→316.0→327.0→305.0→303.0→303.0, Potassium 4.0→3.9→3.9→3.9→4.1→4.0→4.1→4.0→4.3→4.3→4.3→4.3, Sodium 135.0→135.0→137.0→137.0→138.0→139.0→136.0→135.0→138.0→137.0→137.0→136.0, Urea Nitrogen 12.0→10.0→8.0→8.0→8.0→7.0→6.0→6.0→5.0→6.0→7.0. Which patient’s procedure produced this post‑state?

- **Patient A** underwent: **Dialysis - CRRT**
- **Patient B** underwent: **Non-invasive Ventilation**

**Observed post-procedure labs (from exactly ONE of them):**
- Bicarbonate: 17.0→17.0→17.0→17.0→16.0→15.0→18.0→18.0→16.0→17.0→17.0→17.0
- Creatinine: 1.3→1.3→1.3→1.5→1.5→1.4→1.3→1.2→1.2→1.2→1.3
- Lactate: 1.6→1.6→1.3→1.3
- Platelet Count: 373.0→316.0→327.0→305.0→303.0→303.0
- Potassium: 4.0→3.9→3.9→3.9→4.1→4.0→4.1→4.0→4.3→4.3→4.3→4.3
- Sodium: 135.0→135.0→137.0→137.0→138.0→139.0→136.0→135.0→138.0→137.0→137.0→136.0
- Urea Nitrogen: 12.0→10.0→8.0→8.0→8.0→7.0→6.0→6.0→5.0→6.0→7.0

### Ground truth

**Correct answer: Patient `A`** produced the observed post-state.

**Why:** CRRT removes bicarbonate and creatinine from the blood, producing the observed gradual decline in bicarbonate and the transient rise then fall in creatinine, while non‑invasive ventilation has no such renal clearance effect.

**Distinguishing features:** [{"procedure": "Continuous renal replacement therapy", "expected_effect": "reduces serum bicarbonate and creatinine via extracorporeal clearance"}, {"procedure": "Non\u2011invasive ventilation", "expected_effect": "does not alter bicarbonate or creatinine levels"}]
