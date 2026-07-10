# Benchmark C — 100 questions


---

## qc_00000  ·  subject None / hadm c001560

**Question:** Patient A underwent continuous renal replacement therapy (CRRT) and Patient B received non‑invasive ventilation. The following post‑procedure laboratory series was recorded: Bicarbonate 17.0→17.0→17.0→17.0→16.0→15.0→18.0→18.0→16.0→17.0→17.0→17.0, Creatinine 1.3→1.3→1.3→1.5→1.5→1.4→1.3→1.2→1.2→1.2→1.3, Lactate 1.6→1.6→1.3→1.3, Platelet Count 373.0→316.0→327.0→305.0→303.0→303.0, Potassium 4.0→3.9→3.9→3.9→4.1→4.0→4.1→4.0→4.3→4.3→4.3→4.3, Sodium 135.0→135.0→137.0→137.0→138.0→139.0→136.0→135.0→138.0→137.0→137.0→136.0, Urea Nitrogen 12.0→10.0→8.0→8.0→8.0→7.0→6.0→6.0→5.0→6.0→7.0. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Non-invasive Ventilation
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** CRRT removes bicarbonate and creatinine from the blood, producing the observed gradual decline in bicarbonate and the transient rise then fall in creatinine, while non‑invasive ventilation has no such renal clearance effect.
- Continuous renal replacement therapy: reduces serum bicarbonate and creatinine via extracorporeal clearance
- Non‑invasive ventilation: does not alter bicarbonate or creatinine levels

**PubMed:** PMID 42161388 (Optimizing CO(2) clearance in combined extracorporeal carbon); PMID 41877111 (Clearance of small and middle molecules during continuous re)

---

## qc_00001  ·  subject None / hadm c000383

**Question:** Two patients underwent different procedures: Patient A had extubation after invasive ventilation, and Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory values were recorded for one of them: Bicarbonate rose from 16.0 to 25.0, Creatinine fell from 11.4 to 7.8, Lactate decreased from 4.3 to 3.2, Platelet count fluctuated from 109.0 to 86.0, Potassium spiked to 6.4 then returned to 5.5, Sodium remained around 140, and Urea Nitrogen dropped from 53.0 to 36.0. Which patient’s procedure produced this laboratory trajectory?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** Extubation removes the metabolic stress of mechanical ventilation, rapidly lowering lactate and improving acid–base status, while CRRT primarily clears solutes like creatinine and urea but does not markedly reduce lactate; the observed lactate fall and bicarbonate rise are consistent with extubation.
- Extubation: Rapid decrease in lactate and correction of metabolic acidosis, with modest changes in creatinine and urea.
- CRRT: Clearance of creatinine and urea, but lactate levels often remain unchanged or rise due to ongoing critical illness.

**PubMed:** PMID 41689327 (Comparison of Classical Blood Cardioplegia and Modified Del ); PMID 41854309 (Regional citrate anticoagulation prolongs filter lifespan an)

---

## qc_00002  ·  subject None / hadm c000589

**Question:** Patient A underwent extubation and Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory values were observed: Bicarbonate 24.0→23.0, Creatinine 1.8→2.0, Platelet Count 103.0→107.0, Potassium 5.3→4.1, Sodium 135.0→138.0, Urea Nitrogen 39.0→45.0. Which patient’s procedure produced this laboratory profile?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** CRRT typically lowers serum potassium and urea nitrogen while raising creatinine due to filtration and fluid shifts, but it does not cause the observed drop in potassium from 5.3 to 4.1; extubation alone can lead to a modest decrease in potassium and a slight rise in bicarbonate, matching the pattern seen.
- CRRT: reduces potassium and urea nitrogen, may increase creatinine, and corrects acidosis
- Extubation: minimal impact on electrolytes; may slightly lower potassium and raise bicarbonate

**PubMed:** PMID 36694734 (Effects of continuous renal replacement therapy on Apache-II); PMID 41689327 (Comparison of Classical Blood Cardioplegia and Modified Del )

---

## qc_00003  ·  subject None / hadm c001477

**Question:** Patient A underwent continuous renal replacement therapy (CRRT) and Patient B was intubated. After the procedures, the following laboratory values were observed: Bicarbonate 24.0, Creatinine 5.7, Hemoglobin 7.4, Lactate 1.0, Platelet Count 186.0, Potassium 4.2, Sodium 140.0, Urea Nitrogen 80.0. Which patient’s procedure produced this post‑procedure laboratory profile?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Intubation
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** The rise in bicarbonate and fall in creatinine are characteristic of CRRT, but the observed values are more consistent with the modest changes seen after intubation alone, while CRRT would have produced a larger bicarbonate increase and a more pronounced creatinine decline; the platelet count and potassium trend also align better with the intubation profile.
- CRRT: increases serum bicarbonate, reduces creatinine, may lower potassium, and can modestly raise platelets
- Intubation: minimal impact on bicarbonate, creatinine, potassium, and platelets; lactate may transiently rise or fall depending on ventilation

**PubMed:** PMID 42130369 (High Bicarbonate Dialysis With or Without Extracorporeal Car); PMID 41877111 (Clearance of small and middle molecules during continuous re)

---

## qc_00004  ·  subject None / hadm c000360

**Question:** Patient A underwent extubation and Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory values were recorded: Bicarbonate increased from 20.0 to 29.0 mmol/L, Creatinine decreased from 4.8 to 2.2 mg/dL, Lactate fell from 2.0 to 1.6 mmol/L, Platelet Count dropped from 298 to 164 ×10^9/L, Potassium fell from 6.8 to 3.5 mmol/L, Sodium rose from 136 to 139 mmol/L, and Urea Nitrogen fell from 32 to 19 mg/dL. Which patient’s procedure produced this laboratory trajectory?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT removes excess potassium, urea, and creatinine while providing bicarbonate, explaining the rapid declines in K⁺, BUN, Cr and the rise in bicarbonate; extubation alone would not produce such marked electrolyte shifts.
- Extubation: minimal impact on serum electrolytes or acid–base status; platelet count may transiently fall due to stress but no large K⁺ or Cr changes
- CRRT: continuous removal of potassium, urea, creatinine and lactate with bicarbonate supplementation, leading to progressive normalization of these labs

**PubMed:** PMID 28856008 (When CRRT on ECMO Is Not Enough for Potassium Clearance: A C); PMID 41877111 (Clearance of small and middle molecules during continuous re)

---

## qc_00005  ·  subject None / hadm c001191

**Question:** Patient A underwent continuous renal replacement therapy (CRRT) and Patient B was intubated. The following post‑procedure laboratory trajectory was observed: bicarbonate 22.0→19.0→19.0→23.0→20.0, creatinine 0.9→1.6→1.7→1.4→1.3, lactate 4.9→1.9→1.3→2.5→2.3→2.0→1.6→2.1→1.8→1.5→2.1, platelet count 241.0→257.0→245.0→214.0→226.0, potassium 4.2→4.9→5.6→4.8→5.4, sodium 144.0→142.0→142.0→144.0→144.0, urea nitrogen 26.0→34.0→37.0→39.0→43.0. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Intubation
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** Intubation in a septic, CKD patient causes transient hypoxia and catecholamine surge, raising lactate and urea nitrogen while modestly increasing creatinine; CRRT would lower creatinine and lactate, not raise them.
- CRRT: reduces creatinine, urea nitrogen, and lactate; stabilizes potassium and bicarbonate
- Intubation: can transiently elevate lactate and urea nitrogen due to hypoxia and stress; may raise creatinine in CKD patients

**PubMed:** PMID 41854309 (Regional citrate anticoagulation prolongs filter lifespan an); PMID 41598217 (Peak Lactate Within 24 h and Mortality in Septic Shock Patie); PMID 42017096 (Early Plasma Exchange for Multiple Organ Failure Following M)

---

## qc_00006  ·  subject None / hadm c000724

**Question:** Two patients underwent different procedures: Patient A had extubation, while Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory trend was observed: Bicarbonate rose from 25.0 to 29.0, Creatinine fell from 1.3 to 0.9, Lactate increased to 2.1, Platelet count rose from 141 to 163, Potassium fluctuated around 4.0, Sodium remained ~137–138, and Urea Nitrogen decreased from 19.0 to 9.0. Which patient’s procedure produced this laboratory pattern?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT removes urea and creatinine, raising bicarbonate via bicarbonate‑laden dialysate and improves platelet counts by reducing inflammatory mediators; extubation does not alter these labs.
- Extubation: minimal impact on renal clearance, bicarbonate, or platelet count
- CRRT: reduces creatinine and urea, increases bicarbonate, and can raise platelet count

**PubMed:** PMID 42028141 (Cast nephropathy in the ICU: Early recognition and extracorp); PMID 42130369 (High Bicarbonate Dialysis With or Without Extracorporeal Car); PMID 42346488 (Hyperbilirubinemia After Redo Valve Surgery: Incidence, Peri)

---

## qc_00007  ·  subject None / hadm c000479

**Question:** Patient A underwent extubation and Patient B underwent continuous renal replacement therapy (CRRT). The following post-procedure laboratory values were recorded: Bicarbonate rose from 23.0 to 34.0 mmol/L, Creatinine fell from 5.7 to 2.3 mg/dL, Lactate fluctuated between 1.2 and 1.6 mmol/L, Platelet Count decreased from 151 to 80 ×10^9/L, Potassium dropped from 4.5 to 3.8 mmol/L, Sodium increased from 137 to 141 mmol/L, and Urea Nitrogen fell from 33.0 to 13.0 mg/dL. Which patient’s procedure produced this post-state?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT removes creatinine, urea, and potassium while adding bicarbonate, explaining the observed declines and rises; extubation alone would not produce such marked changes.
- Extubation: minimal impact on renal solutes or bicarbonate; lab changes are usually due to underlying disease, not extubation.
- CRRT: continuous removal of creatinine, urea, and potassium and infusion of bicarbonate solution, raising bicarbonate and sodium while lowering creatinine, urea, and potassium.

**PubMed:** PMID 37558740 (Kinetics of small and middle molecule clearance during conti); PMID 42130369 (High Bicarbonate Dialysis With or Without Extracorporeal Car); PMID 41615333 (Continuous Renal Replacement Therapy During Liver Transplant)

---

## qc_00008  ·  subject None / hadm c000361

**Question:** Patient A underwent extubation and Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory values were observed: Bicarbonate 32.0 mmol/L, Creatinine 1.3 mg/dL, Platelet Count 311 ×10^9/L, Potassium 3.7 mmol/L, Sodium 131 mmol/L, Urea Nitrogen 38.0 mg/dL. Which patient’s procedure produced this laboratory profile?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** Extubation removes CO₂ retention, causing a shift toward metabolic alkalosis and raising bicarbonate, while creatinine remains unchanged; CRRT would lower creatinine and often reduce bicarbonate due to dialysate composition. The platelet rise is consistent with removal of platelet‑consuming inflammatory mediators during extubation, not with CRRT‑associated platelet consumption.
- Extubation: Increases arterial bicarbonate via CO₂ loss, modest rise in platelets, unchanged creatinine
- CRRT: Lowers creatinine, may lower or stabilize bicarbonate, can decrease platelets due to filter adsorption

**PubMed:** PMID 27885969 (36th International Symposium on Intensive Care and Emergency); PMID 42130369 (High Bicarbonate Dialysis With or Without Extracorporeal Car); PMID 41023114 (Change in platelet and leukocyte counts and hospital mortali)

---

## qc_00009  ·  subject None / hadm c000610

**Question:** Patient A underwent extubation and Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory values were observed: Bicarbonate 24.0→26.0→25.0 mmol/L, Creatinine 1.4→1.3→1.3 mg/dL, Platelet Count 302.0→375.0 ×10⁹/L, Potassium 4.4→4.6→4.4 mmol/L, Sodium 133.0→135.0→133.0 mmol/L, Urea Nitrogen 15.0→15.0→20.0 mg/dL. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** Extubation improves ventilation, reducing CO₂ retention and raising serum bicarbonate, while CRRT removes solutes and would lower bicarbonate; the observed rise in bicarbonate aligns with extubation. CRRT would lower creatinine and urea nitrogen, but the creatinine remained stable and urea nitrogen increased, inconsistent with CRRT.
- Extubation: Improved CO₂ elimination increases serum bicarbonate and may modestly raise potassium; creatinine and urea nitrogen remain unchanged.
- CRRT: Continuous removal of solutes lowers creatinine, urea nitrogen, and potassium, while bicarbonate may decrease due to dialysate composition.

**PubMed:** PMID 37861571 (Effects of a forced‑air warming system and warmed intravenou); PMID 36694734 (Effects of continuous renal replacement therapy on Apache‑II)

---

## qc_00010  ·  subject None / hadm c001665

**Question:** Two patients underwent different procedures: Patient A received continuous renal replacement therapy (CRRT) and Patient B received non‑invasive ventilation. After the procedures, the following laboratory values were recorded: Bicarbonate 26.0→27.0→27.0→24.0→25.0→24.0→23.0→23.0→20.0, Creatinine 1.0→0.8→0.7→0.7→0.6→0.6, Lactate 1.3→1.6→1.2→1.1→1.4→1.2→1.1→1.9→1.8→1.7, Platelet Count 199.0→157.0→175.0→164.0→178.0→200.0, Potassium 4.4→4.5→4.7→5.3→5.0→4.8→4.9→4.9→5.3→4.7, Sodium 141.0→140.0→139.0→141.0→141.0→140.0→139.0→139.0→140.0, Urea Nitrogen 46.0→33.0→28.0→27.0→24.0→23.0. Which patient’s procedure produced this post‑procedure laboratory profile?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Non-invasive Ventilation
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** CRRT removes creatinine and urea, lowering their levels, and can correct metabolic acidosis, raising bicarbonate; it also removes potassium, lowering serum potassium, whereas non‑invasive ventilation has no such renal effects.
- CRRT: decreases creatinine, urea nitrogen, potassium; increases bicarbonate
- Non‑invasive ventilation: no significant change in renal or acid‑base labs

**PubMed:** PMID 41877111 (Clearance of small and middle molecules during continuous re); PMID 41878413 (Outcomes of Extracorporeal Removal in Acute Barium Poisoning)

---

## qc_00011  ·  subject None / hadm c000859

**Question:** Two patients underwent different procedures: Patient A was extubated after invasive ventilation, while Patient B received continuous renal replacement therapy (CRRT). The following post‑procedure laboratory values were recorded (in the order shown): Bicarbonate 23.0→24.0→21.0→24.0→25.0→24.0→24.0→23.0, Creatinine 0.9→0.9→0.6→0.9→0.8→1.0→1.0→1.3, Hemoglobin 11.3, Lactate 5.5→3.8, Platelet Count 193.0→127.0→194.0, Potassium 4.3→4.4→3.5→4.1→4.4→4.2→4.3→5.2, Sodium 141.0→144.0→144.0→143.0→142.0→145.0→143.0→143.0, Urea Nitrogen 17.0→21.0→22.0→25.0→28.0→29.0→31.0→36.0. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** Extubation improves ventilation, lowering lactate and modestly raising bicarbonate, while CRRT would lower creatinine and urea; the observed creatinine drop to 0.6 and lactate reduction are consistent with extubation, not with CRRT.
- Extubation: reduces lactate and improves bicarbonate by restoring adequate ventilation
- CRRT: lowers creatinine and urea nitrogen by extracorporeal clearance

**PubMed:** PMID 42007097 (Early initiation of continuous renal replacement therapy imp); PMID 42116820 (Use of near-infrared spectroscopy to guide care in the cardi)

---

## qc_00012  ·  subject None / hadm c000633

**Question:** Two patients underwent different procedures: Patient A had extubation after invasive ventilation, while Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory trajectory was recorded: Bicarbonate fluctuated between 19.0 and 21.0 mmol/L, Creatinine rose from 2.2 to 3.2 mg/dL and then declined to 2.2 mg/dL, Platelet Count varied from 86 to 125 ×10⁹/L, Potassium ranged from 4.1 to 5.0 mmol/L, Sodium decreased from 137 to 133 mmol/L, and Urea Nitrogen increased from 33 to 55 mg/dL before falling to 48 mg/dL. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** Extubation alone does not markedly alter renal markers; the observed sustained rise and subsequent fall in creatinine, urea nitrogen, and potassium are characteristic of CRRT’s clearance and fluid balance effects, which are absent in a simple extubation scenario.
- Extubation: Minimal impact on renal labs; bicarbonate and electrolytes remain largely unchanged
- CRRT: Gradual reduction of creatinine, urea nitrogen, and potassium with transient shifts in bicarbonate and sodium due to dialysate composition

**PubMed:** PMID 36694734 (Effects of continuous renal replacement therapy on Apache-II)

---

## qc_00013  ·  subject None / hadm c001800

**Question:** Patient A underwent continuous renal replacement therapy (CRRT) and Patient B received non‑invasive ventilation. The following post‑procedure laboratory trajectory was observed: Bicarbonate rose from 22.0 to 24.0 and then fell to 23.0; Creatinine decreased from 3.9 to 2.0; Hemoglobin increased from 9.2 to 9.1; Lactate fluctuated but peaked at 3.8; Platelet count dropped to 132.0; Potassium remained stable; Sodium decreased to 132.0; Urea nitrogen fell to 42.0. Which patient’s procedure produced this laboratory pattern?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Non-invasive Ventilation
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** CRRT removes uremic toxins and corrects acid–base disturbances, explaining the rapid creatinine and urea decline and bicarbonate rise; the transient lactate spike reflects CRRT‑related metabolic shifts, whereas non‑invasive ventilation does not alter these labs.
- CRRT: decreases creatinine, urea, and lactate while increasing bicarbonate and stabilizing potassium
- Non‑invasive ventilation: minimal impact on renal clearance or acid–base status, so creatinine, urea, and bicarbonate remain largely unchanged

**PubMed:** PMID 42130369 (High Bicarbonate Dialysis With or Without Extracorporeal Car); PMID 42028141 (Cast nephropathy in the ICU: Early recognition and extracorp); PMID 41765054 (A novel serum phosphorus to chloride and bicarbonate ratio p)

---

## qc_00014  ·  subject None / hadm c000228

**Question:** Two patients underwent different procedures: Patient A had extubation after prolonged mechanical ventilation, while Patient B underwent continuous renal replacement therapy (CRRT). After the procedures, the following laboratory values were observed: Bicarbonate rose from 24.0 to 30.0 mmol/L, Creatinine fell from 3.1 to 2.6 mg/dL, Platelet Count increased from 130.0 to 159.0 ×10^9/L, Potassium rose from 3.4 to 4.2 mmol/L, Sodium increased from 137.0 to 143.0 mmol/L, and Urea Nitrogen decreased from 67.0 to 58.0 mg/dL. Which patient’s procedure produced this post‑procedure laboratory profile?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** Extubation improves pulmonary perfusion and reduces lactate, leading to a rise in bicarbonate and a modest creatinine decline; it also removes the need for continuous renal support, allowing gradual normalization of electrolytes and urea. CRRT, by contrast, actively removes potassium and urea, would lower potassium and urea rather than raise them, and typically causes a drop in bicarbonate due to bicarbonate‑free dialysate.
- Extubation: ↑ serum bicarbonate, ↓ creatinine, ↑ potassium, ↑ sodium, ↓ urea nitrogen, ↑ platelet count due to reduced inflammation
- CRRT: ↓ potassium, ↓ urea nitrogen, ↓ creatinine, ↓ bicarbonate (if bicarbonate‑free dialysate), possible thrombocytopenia

**PubMed:** PMID 41877111 (Clearance of small and middle molecules during continuous re); PMID 39601911 (Chloride removal and bicarbonate replacement by isotonic sod)

---

## qc_00015  ·  subject None / hadm c001367

**Question:** Patient A underwent continuous renal replacement therapy (CRRT) while Patient B was intubated. The following post‑procedure laboratory values were recorded: Bicarbonate 23.0 mmol/L, Creatinine 2.0 mg/dL, Hemoglobin 8.1 g/dL, Lactate 1.9 mmol/L, Platelet Count 36.0 ×10^9/L, Potassium 4.6 mmol/L, Sodium 141.0 mmol/L, Urea Nitrogen 72.0 mg/dL. Which patient’s procedure produced this laboratory profile?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Intubation
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** CRRT removes creatinine, urea, and lactate while correcting acidosis, producing the observed decreases in creatinine, urea, and lactate and the rise in bicarbonate; intubation alone does not alter these metabolites.
- CRRT: dialytic clearance of creatinine, urea, and lactate; correction of metabolic acidosis (↑bicarbonate) and modest potassium shifts
- Intubation: minimal direct effect on renal clearance or acid–base status; labs remain largely unchanged

**PubMed:** PMID 41877111 (Clearance of small and middle molecules during continuous re); PMID 41854309 (Regional citrate anticoagulation prolongs filter lifespan an)

---

## qc_00016  ·  subject None / hadm c000263

**Question:** Two patients underwent different procedures: Patient A had extubation after invasive ventilation, while Patient B underwent continuous renal replacement therapy (CRRT) for acute kidney injury. The following post‑procedure laboratory trajectory was observed: Bicarbonate fluctuated around 25–26 mmol/L, Creatinine steadily decreased from 1.8 to 1.1 mg/dL, Hemoglobin dropped to 8.2 g/dL, Lactate varied between 1.0–1.7 mmol/L, Platelet count rose to 383–423 ×10⁹/L, Potassium increased to 4.2–4.5 mmol/L, Sodium rose to 135–141 mmol/L, and Urea Nitrogen fell from 45 to 30 mg/dL. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT removes creatinine, urea, and excess bicarbonate, explaining the steady decline in creatinine, urea, and the stabilization of bicarbonate; it also clears lactate and can modestly raise potassium and sodium, matching the observed trends, whereas extubation alone would not produce such systematic metabolic changes.
- CRRT: continuous removal of creatinine, urea, and lactate, with modest shifts in bicarbonate, potassium, and sodium
- Extubation: minimal direct effect on renal clearance or electrolyte balance, primarily relieving ventilatory support

**PubMed:** PMID 35242474 (Comparison of the Treatment Efficacy of Continuous Renal Rep); PMID 41877111 (Clearance of small and middle molecules during continuous re)

---

## qc_00017  ·  subject None / hadm c000785

**Question:** Patient A underwent extubation and Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory values were recorded: Bicarbonate 20.0→28.0→27.0→23.0, Creatinine 4.3→2.7→3.8→4.9, Platelet Count 93.0→121.0→116.0, Potassium 4.3→4.5→3.7→4.2→4.1, Sodium 137.0→138.0→134.0→131.0, Urea Nitrogen 21.0→9.0→18.0→32.0. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** Extubation in a patient with chronic kidney disease can cause transient metabolic alkalosis and a rise in bicarbonate, while CRRT typically lowers creatinine and urea nitrogen; the observed creatinine rise and urea nitrogen oscillation match the extubation pattern, not the CRRT clearance effect.
- Extubation: may transiently increase bicarbonate and cause variable creatinine due to hemodynamic shifts
- CRRT: reduces creatinine and urea nitrogen by continuous filtration

**PubMed:** PMID 41877111 (Clearance of small and middle molecules during continuous re); PMID 42245947 (Impacts of hemoperfusion combined with continuous renal repl)

---

## qc_00018  ·  subject None / hadm c001017

**Question:** Patient A underwent continuous renal replacement therapy (CRRT) and Patient B underwent intubation. The following post‑procedure laboratory values were observed: Bicarbonate decreased from 30.0 to 27.0 to 23.0 mmol/L, Creatinine rose from 0.7 to 0.6 to 0.6 to 0.9 to 0.9 to 1.0 mg/dL, Hemoglobin 8.3 g/dL, Lactate fluctuated from 1.4 to 1.0 to 1.1 to 1.0 mmol/L, Platelet Count increased from 178 to 173 to 229 ×10^9/L, Potassium rose from 4.2 to 4.2 to 4.3 to 4.8 to 4.4 mmol/L, Sodium varied from 139 to 142 to 142 to 139 mmol/L, and Urea Nitrogen increased from 15.0 to 12.0 to 12.0 to 18.0 to 18.0 to 23.0 mg/dL. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Intubation
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** Intubation alone does not alter renal clearance, so creatinine and urea rise are inconsistent; CRRT removes creatinine and urea, but the observed rise reflects pre‑existing AKI and fluid shifts, while the gradual bicarbonate drop and lactate changes are typical of CRRT’s metabolic effects, matching Patient B’s procedure.
- CRRT: removes creatinine and urea, can lower bicarbonate and lactate, and may transiently alter platelet counts due to extracorporeal contact
- Intubation: no direct effect on renal labs; may modestly affect lactate via ventilation changes but not cause creatinine or urea shifts

**PubMed:** PMID 41877111 (Clearance of small and middle molecules during continuous re); PMID 42130369 (High Bicarbonate Dialysis With or Without Extracorporeal Car)

---

## qc_00019  ·  subject None / hadm c000795

**Question:** Two patients underwent different procedures: Patient A had extubation after invasive ventilation, and Patient B underwent continuous renal replacement therapy (CRRT). The following post-procedure laboratory trajectory was observed: Bicarbonate fluctuated from 19.0 to 21.0, Creatinine rose from 0.8 to 1.8, Platelet Count increased from 192 to 232, Potassium varied between 4.6 and 5.0, Sodium decreased from 134 to 131, and Urea Nitrogen spiked from 8.0 to 28.0. Which patient’s procedure produced this laboratory pattern?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT removes urea and creatinine, causing a transient rise in creatinine and a dramatic increase in urea nitrogen, while the bicarbonate‑rich replacement fluid lowers serum bicarbonate; extubation does not produce these marked changes.
- Extubation: minimal impact on renal labs; bicarbonate and electrolytes remain stable
- CRRT: removal of urea and creatinine, bicarbonate‑rich fluid lowers bicarbonate, transient potassium shifts

**PubMed:** PMID 41247497 (Comparison of two different bicarbonate replacement fluids d); PMID 41615333 (Continuous Renal Replacement Therapy During Liver Transplant)

---

## qc_00020  ·  subject None / hadm c000032

**Question:** Two patients underwent different procedures: Patient A had an extubation, while Patient B underwent continuous renal replacement therapy (CRRT). After the procedures, the following laboratory values were recorded: Bicarbonate 16.0→16.0→19.0→16.0→14.0, Creatinine 2.0→2.0→2.0→1.9→2.0, Lactate 3.2→2.7→2.9→2.7→2.5→2.5→2.8→3.2→2.6→2.6→2.9→3.4→3.9→4.1→4.3→5.7→7.3→8.5, Platelet Count 56.0→45.0→49.0→58.0→44.0→60.0→49.0→59.0→48.0→41.0→36.0→35.0→35.0, Potassium 4.4→4.6→4.2→4.2→4.7, Sodium 135.0→135.0→135.0→133.0→133.0, Urea Nitrogen 15.0→14.0→13.0→14.0→16.0. Which patient’s procedure produced this post‑procedure laboratory pattern?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT removes creatinine and urea, causing transient decreases, while platelet consumption and lactate accumulation are typical of extracorporeal circuits; extubation alone would not produce these changes.
- Extubation: minimal impact on creatinine, lactate, or platelet count
- CRRT: reduces creatinine and urea, increases lactate and platelet consumption

**PubMed:** PMID 36472056 (Treatment Efficacy of Continuous Renal Replacement on Sympto); PMID 41877111 (Clearance of small and middle molecules during continuous re); PMID 41909343 (Where Is the Lactate Coming From? An Unusual Presentation of)

---

## qc_00021  ·  subject None / hadm c001669

**Question:** Two patients underwent different procedures: Patient A received continuous renal replacement therapy (CRRT) and Patient B received non‑invasive ventilation. Their pre‑procedure labs are shown. After the procedures, the following serial lab values were recorded: Bicarbonate 23.0→27.0→26.0→26.0→27.0→28.0, Creatinine 3.3→2.3→1.5→1.2→1.2→1.6, Platelet Count 213.0→264.0→372.0, Potassium 3.8→4.4→4.1→4.7→4.7→4.8, Sodium 135.0→138.0→137.0→141.0→141.0→144.0, Urea Nitrogen 46.0→31.0→21.0→17.0→17.0→24.0. Which patient’s procedure produced this post‑procedure laboratory trajectory?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Non-invasive Ventilation
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** CRRT removes creatinine, urea, and potassium while adding bicarbonate, producing the observed decreases in creatinine, urea nitrogen, and potassium and the rise in bicarbonate; non‑invasive ventilation does not alter these electrolytes or acid–base status.
- CRRT: dialysis‑like removal of creatinine, urea nitrogen, and potassium and infusion of bicarbonate, raising serum bicarbonate.
- Non‑invasive ventilation: no significant effect on renal clearance or serum bicarbonate, potassium, or urea nitrogen.

**PubMed:** PMID 42130369 (High Bicarbonate Dialysis With or Without Extracorporeal Car); PMID 41877111 (Clearance of small and middle molecules during continuous re)

---

## qc_00022  ·  subject None / hadm c000287

**Question:** Patient A underwent extubation after a prolonged intubation, while Patient B received continuous renal replacement therapy (CRRT) for acute kidney injury. The following post‑procedure laboratory trajectory was observed: bicarbonate 29.0→24.0→25.0→25.0→24.0, creatinine 5.5→9.2→9.7→9.5→10.9, lactate 1.1, platelet count 194.0→227.0→250.0→248.0, potassium 3.8→4.2→3.9→4.4→4.0, sodium 137.0→131.0→136.0→135.0→136.0, urea nitrogen 19.0→52.0→55.0→57.0→59.0. Which patient’s procedure produced this laboratory pattern?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** Extubation can precipitate hemodynamic instability and inflammatory stress that worsen renal perfusion, leading to a rise in creatinine and urea nitrogen, whereas CRRT typically removes creatinine and urea, lowering them; the observed increases are therefore consistent with extubation.
- Extubation: may cause transient hypotension and inflammatory response that can elevate creatinine and urea nitrogen
- CRRT: removes creatinine and urea nitrogen, typically decreasing their serum levels

**PubMed:** PMID 42007097 (Early initiation of continuous renal replacement therapy imp); PMID 42336097 (Inhaled nitric oxide for reducing major adverse events requi)

---

## qc_00023  ·  subject None / hadm c000657

**Question:** Patient A underwent extubation and Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory values were observed (in the order of appearance): Bicarbonate 25.0 → 23.0 → 24.0, Creatinine 1.6 → 1.8 → 1.8, Platelet Count 140.0 → 101.0 → 110.0, Potassium 4.9 → 4.9 → 4.3 → 4.3, Sodium 139.0 → 133.0 → 134.0, Urea Nitrogen 22.0 → 24.0 → 25.0. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** Extubation typically causes a transient rise in serum potassium due to catecholamine‑mediated shift and mild metabolic acidosis, matching the observed potassium peak and subsequent decline; CRRT would have steadily lowered potassium and creatinine, contrary to the pattern seen.
- Extubation: Transient hyperkalemia and mild acidosis with a brief rise in creatinine and urea nitrogen.
- CRRT: Gradual reduction of potassium, creatinine, and urea nitrogen with stable bicarbonate and sodium.

**PubMed:** PMID 41877111 (Clearance of small and middle molecules during continuous re); PMID 39601911 (Chloride removal and bicarbonate replacement by isotonic sod)

---

## qc_00024  ·  subject None / hadm c001067

**Question:** Two patients underwent different procedures: Patient A received continuous renal replacement therapy (CRRT) for acute kidney injury, while Patient B was intubated for respiratory failure. After the procedures, the following laboratory values were observed: bicarbonate fluctuated from 21.0 to 24.0 to 27.0 and back to 24.0, creatinine rose from 3.5 to 2.4 to 2.8 to 3.3, hemoglobin dropped to 7.6, lactate decreased to 1.0, platelet count varied from 199 to 160 to 176, potassium decreased from 5.2 to 3.9 to 4.1, sodium decreased from 133 to 130, and urea nitrogen fell from 82 to 52 to 63 to 85. Which patient’s procedure most plausibly produced this post‑procedure laboratory pattern?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Intubation
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** Intubation can trigger a transient metabolic alkalosis and modest hemolysis, explaining the rise in bicarbonate and drop in hemoglobin, while the patient’s pre‑existing mild renal dysfunction explains the modest creatinine changes; CRRT would have produced a more pronounced potassium decline and sustained bicarbonate correction, inconsistent with the observed pattern.
- CRRT: Rapid potassium removal and sustained bicarbonate correction, with gradual creatinine decline.
- Intubation: Transient metabolic alkalosis, modest hemolysis, and minimal impact on potassium and creatinine.

**PubMed:** PMID 17883675 (Potassium additive algorithm for use in continuous renal rep); PMID 39601911 (Chloride removal and bicarbonate replacement by isotonic sod); PMID 41877111 (Clearance of small and middle molecules during continuous re)

---

## qc_00025  ·  subject None / hadm c000737

**Question:** Patient A underwent extubation and Patient B underwent continuous renal replacement therapy (CRRT). The following post-procedure laboratory values were recorded (in mmol/L or appropriate units): Bicarbonate: 23.0 → 25.0 → 31.0, Creatinine: 1.0 → 1.2 → 1.1, Platelet Count: 117.0 → 81.0 → 110.0, Potassium: 4.8 → 4.1 → 4.6 → 4.2, Sodium: 137.0 → 137.0 → 140.0 → 137.0, Urea Nitrogen: 23.0 → 24.0 → 25.0. Which patient’s procedure produced this post-state?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** CRRT removes potassium and small solutes, lowering potassium and creatinine, and can transiently raise bicarbonate; extubation does not alter these labs, so the observed pattern matches the dialysis patient’s expected changes, not the extubation patient’s.
- CRRT: reduces serum potassium and creatinine, can increase bicarbonate, and may cause transient platelet fluctuations due to anticoagulation
- Extubation: minimal impact on electrolytes, renal function, or platelet count

**PubMed:** PMID 41877111 (Clearance of small and middle molecules during continuous re); PMID 39601911 (Chloride removal and bicarbonate replacement by isotonic sod)

---

## qc_00026  ·  subject None / hadm c001305

**Question:** Patient A underwent continuous renal replacement therapy (CRRT) and Patient B underwent intubation. The following post‑procedure laboratory trajectory was observed: Bicarbonate fluctuated from 23.0 to 24.0 to 23.0 to 21.0 to 21.0 to 22.0 to 20.0 to 22.0, Creatinine decreased from 1.5 to 1.4 to 1.7 to 1.5 to 1.4 to 1.3 to 1.4, Lactate rose from 1.4 to 1.8 to 1.6 to 2.0 to 2.2 to 2.5 to 2.2 to 1.8 to 1.7 to 2.5 to 2.1 to 2.4 to 2.7 to 2.4 to 2.3 to 1.6 to 1.2 to 1.7 to 1.7, Platelet Count increased from 77.0 to 105.0 to 107.0 to 86.0 to 77.0, Potassium rose from 4.3 to 4.5 to 4.1 to 4.3 to 4.3 to 4.6 to 4.4 to 3.9 to 3.7, Sodium varied from 132.0 to 134.0 to 133.0 to 131.0 to 134.0 to 133.0 to 135.0 to 133.0 to 135.0, and Urea Nitrogen decreased from 37.0 to 36.0 to 41.0 to 38.0 to 37.0 to 33.0 to 33.0. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Intubation
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** CRRT efficiently clears creatinine, urea, and lactate while modestly lowering bicarbonate; it also can cause transient platelet activation and potassium shifts, matching the observed trends, whereas intubation alone would not produce these metabolic changes.
- CRRT: reduces creatinine and urea, clears lactate, may lower bicarbonate, transiently alters platelets and potassium
- Intubation: minimal direct effect on renal clearance or metabolic panels; changes would be due to underlying illness, not the procedure itself

**PubMed:** PMID 37558740 (Kinetics of small and middle molecule clearance during conti); PMID 41854309 (Regional citrate anticoagulation prolongs filter lifespan an)

---

## qc_00027  ·  subject None / hadm c000398

**Question:** Two patients underwent different procedures: Patient A had extubation after invasive ventilation, and Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory values were observed: Bicarbonate increased from 27.0 to 30.0, Creatinine rose from 0.8 to 0.9, Platelet Count fell from 125.0 to 110.0, Potassium remained at 4.6, Sodium rose from 132.0 to 134.0, and Urea Nitrogen increased from 23.0 to 35.0. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** Extubation removes the ventilatory acid load and improves ventilation, raising serum bicarbonate and modestly increasing creatinine due to transient hemoconcentration; it does not clear urea, so urea nitrogen rises. CRRT, by contrast, would lower urea nitrogen and creatinine, not raise them.
- Extubation: Increases serum bicarbonate and may transiently raise creatinine; urea nitrogen is not removed.
- CRRT: Decreases serum urea nitrogen and creatinine; bicarbonate may remain unchanged or decrease.

**PubMed:** PMID 41261569 (Comparative evaluation of continuous renal replacement thera); PMID 37861571 (Effects of a forced‑air warming system and warmed intravenou)

---

## qc_00028  ·  subject None / hadm c000684

**Question:** Patient A underwent extubation and Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory trajectory was observed: Bicarbonate 24.0→21.0→23.0, Creatinine 1.0→1.1→1.3→1.3→1.3→1.2, Hemoglobin 8.0→7.4, Lactate 1.0, Platelet Count 96.0→101.0→76.0→81.0→87.0→83.0, Potassium 4.8→4.5→4.6→4.4→4.9→4.3, Sodium 133.0→130.0→129.0→126.0→125.0, Urea Nitrogen 19.0→20.0→21.0→23.0→27.0→30.0. Which patient’s procedure produced this laboratory pattern?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** Extubation improves oxygenation, lowering lactate and modestly raising bicarbonate, while CRRT primarily clears nitrogenous waste, markedly reducing urea nitrogen and creatinine; the observed rise in urea nitrogen and stable creatinine fits extubation rather than CRRT.
- Extubation: reduces lactate, modestly increases bicarbonate, minimal impact on urea nitrogen
- CRRT: drastically lowers urea nitrogen and creatinine, may lower bicarbonate

**PubMed:** PMID 34719982 (Treatment Effect of Regional Sodium Citrate Anticoagulation ); PMID 41158371 (Survival prediction model for hypoxemic patients receiving p)

---

## qc_00029  ·  subject None / hadm c000876

**Question:** Two patients underwent different procedures: Patient A had extubation after invasive ventilation, while Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory values were observed: Bicarbonate 25.0→25.0→22.0, Creatinine 1.9→1.7→1.7→1.5→1.4, Lactate 1.1, Platelet Count 230.0→290.0→321.0, Potassium 4.7→5.0→4.8→4.2→4.1→4.8, Sodium 133.0→136.0→135.0→135.0→135.0→135.0, Urea Nitrogen 26.0→27.0→27.0→25.0→27.0. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** Extubation removes the need for ventilator‑associated fluid overload and catecholamine support, leading to a modest drop in creatinine and a transient rise in bicarbonate, whereas CRRT directly clears creatinine and urea, producing a more pronounced decline; the observed creatinine trajectory and bicarbonate pattern align with extubation rather than CRRT.
- Extubation: Reduces fluid overload and catecholamine use, causing a modest creatinine decrease and transient bicarbonate rise.
- CRRT: Directly removes creatinine and urea, producing a rapid and larger decline in these labs.

**PubMed:** PMID 41877111 (Clearance of small and middle molecules during continuous re)

---

## qc_00030  ·  subject None / hadm c000151

**Question:** Two patients underwent different procedures: one was extubated after prolonged mechanical ventilation, the other received continuous renal replacement therapy (CRRT) for acute kidney injury. Following the procedures, the following laboratory trajectory was observed: bicarbonate rose from 25.0 to 28.0 mmol/L, creatinine fell from 1.4 to 0.8 mg/dL, lactate fluctuated but overall decreased, platelet count varied, potassium fluctuated but remained around 3.5–4.3 mmol/L, sodium stayed near 137–140 mmol/L, and urea nitrogen declined from 36.0 to 26.0 mg/dL. Which patient’s procedure produced this post‑procedure laboratory pattern?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** Extubation after prolonged ventilation typically improves ventilation‑perfusion matching, leading to a rise in serum bicarbonate and a modest decline in lactate, while CRRT directly clears creatinine and urea nitrogen; the observed creatinine drop to 0.8 mg/dL and urea nitrogen decline are consistent with CRRT, but the pattern of bicarbonate rise and lactate decrease without a dramatic creatinine reduction matches the expected metabolic recovery after extubation rather than the dialysis‑driven clearance seen in patient B.
- Extubation: Improves CO₂ elimination, raising bicarbonate and lowering lactate; minimal direct effect on creatinine or urea nitrogen
- CRRT: Actively removes creatinine and urea nitrogen, producing a rapid decline in these labs while bicarbonate and lactate changes are secondary to fluid shifts

**PubMed:** PMID 41877111 (Clearance of small and middle molecules during continuous re); PMID 39923771 (Effects of immediate extubation in the operating room on lon)

---

## qc_00031  ·  subject None / hadm c000654

**Question:** Patient A underwent extubation and Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory values were observed: Bicarbonate 19.0→23.0→20.0 mmol/L, Creatinine 0.5→0.5→0.7 mg/dL, Platelet Count 301→364→429 ×10^3/µL, Potassium 3.9→4.4→4.4 mmol/L, Sodium 133→135→136 mmol/L, Urea Nitrogen 14→14→17 mg/dL. Which patient’s procedure produced this laboratory trajectory?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** Extubation removes positive pressure ventilation, causing a transient respiratory alkalosis that lowers bicarbonate, then compensatory metabolic acidosis raises it; creatinine rises modestly from pre‑extubation levels, and platelets increase due to mobilization of marrow reserves, matching the observed pattern. CRRT would have removed bicarbonate, lowering it, and would not produce the initial rise seen.
- Extubation: Initial drop in bicarbonate due to respiratory alkalosis, followed by a compensatory rise; modest creatinine increase; platelet count rises from mobilization.
- CRRT: Continuous removal of bicarbonate leading to sustained low levels; creatinine remains high or decreases; platelet count may be unchanged or slightly decreased.

**PubMed:** PMID 20217045 (Effectiveness of acetazolamide for reversal of metabolic alk); PMID 42130369 (High Bicarbonate Dialysis With or Without Extracorporeal Car)

---

## qc_00032  ·  subject None / hadm c000184

**Question:** Patient A underwent extubation, while Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory trend was observed: Bicarbonate rose from 20.0 to 29.0 mmol/L and then fell to 26.0 mmol/L; Creatinine decreased from 1.6 to 1.3 mg/dL; Lactate fluctuated around 1.6–1.8 mmol/L; Platelet count dropped from 49 to 47 ×10^9/L; Potassium varied between 3.7 and 4.8 mmol/L; Sodium increased from 130 to 137 mmol/L; Urea nitrogen fell from 37 to 21 mg/dL. Which patient’s procedure produced this laboratory pattern?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT removes waste and excess electrolytes, raising bicarbonate, lowering creatinine, urea, and potassium, while modestly increasing sodium; it also can cause transient platelet consumption, matching the observed shifts, whereas extubation alone would not produce such systematic changes.
- Extubation: Minimal impact on metabolic or renal labs; no systematic rise in bicarbonate or fall in creatinine.
- CRRT: Rapid correction of acidosis (↑bicarbonate), clearance of creatinine and urea (↓levels), removal of potassium (↓K+), modest sodium gain, and filter‑related platelet consumption (↓platelets).

**PubMed:** PMID 42130369 (High Bicarbonate Dialysis With or Without Extracorporeal Car); PMID 41877111 (Clearance of small and middle molecules during continuous re)

---

## qc_00033  ·  subject None / hadm c000292

**Question:** Two patients underwent different procedures: Patient A had extubation and Patient B had continuous renal replacement therapy (CRRT). The following post‑procedure laboratory values were recorded: Bicarbonate 22.0→26.0→24.0→27.0→26.0→28.0→27.0→27.0→26.0, Creatinine 2.0→2.1→1.9→2.1→1.9→2.1→2.0→2.2→2.2, Lactate 4.9→2.2→1.7→1.6→1.8→1.5→1.3→1.4→1.6→1.8→1.6→1.5→1.7, Platelet Count 73.0→90.0→86.0→82.0→83.0→93.0→94.0, Potassium 3.2→3.5→3.3→4.1→3.9→4.1→4.2→4.5→4.3, Sodium 134.0→131.0→132.0→132.0→132.0→132.0→132.0→131.0→128.0, Urea Nitrogen 15.0→13.0→11.0→10.0→9.0→10.0→11.0→13.0→13.0. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** Extubation improves oxygenation and reduces anaerobic metabolism, causing a rapid fall in lactate and a modest rise in bicarbonate, while CRRT primarily clears creatinine and urea but does not markedly lower lactate; the observed lactate trajectory and bicarbonate pattern match extubation.
- Extubation: Rapid lactate decrease and modest bicarbonate increase due to improved ventilation and oxygen delivery.
- CRRT: Significant creatinine and urea nitrogen reduction with minimal impact on lactate or bicarbonate.

**PubMed:** PMID 41877111 (Clearance of small and middle molecules during continuous re); PMID 40070308 (A dynamic elastance‑based protocol to guide intra‑operative )

---

## qc_00034  ·  subject None / hadm c000183

**Question:** Two patients underwent different procedures: Patient A had extubation, and Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory trajectory was observed in one of them: Bicarbonate rose from 20.0 to 29.0 mmol/L and then fell to 26.0 mmol/L; Creatinine decreased from 1.6 to 1.3 mg/dL; Lactate fluctuated around 1.6–1.8 mmol/L; Platelet count dropped to 49 ×10⁹/L then rose to 60 ×10⁹/L; Potassium fell to 3.7 mmol/L then rose to 4.8 mmol/L; Sodium increased from 130 to 137 mmol/L; Urea nitrogen fell from 37 to 21 mg/dL. Which patient’s procedure produced this laboratory pattern?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT removes urea and creatinine, raising bicarbonate and sodium while lowering potassium, matching the observed trend; extubation alone would not cause such marked changes in renal clearance markers.
- Extubation: minimal impact on renal clearance markers; may transiently alter lactate due to stress
- CRRT: reduces creatinine and urea nitrogen, corrects metabolic acidosis (↑bicarbonate), and shifts electrolytes (↓K⁺, ↑Na⁺)

**PubMed:** PMID 41877111 (Clearance of small and middle molecules during continuous re); PMID 42130369 (High Bicarbonate Dialysis With or Without Extracorporeal Car)

---

## qc_00035  ·  subject None / hadm c000413

**Question:** Two patients underwent different procedures: Patient A was extubated after prolonged invasive ventilation, while Patient B received continuous renal replacement therapy (CRRT). Both patients had distinct pre‑procedure laboratory values. After the procedures, the following laboratory trajectory was observed: bicarbonate fluctuated between 26 and 31 mmol/L, creatinine rose from 1.9 to 2.3 mg/dL, hemoglobin fell from 6.4 to 5.4 g/dL, lactate spiked to 4.5 mmol/L, platelet count dropped to 11×10^9/L, potassium peaked at 5.9 mmol/L, sodium rose to 153 mmol/L, and urea nitrogen increased to 95 mg/dL. Which patient’s procedure is most consistent with this post‑procedure laboratory pattern?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** Extubation after prolonged ventilation often precipitates transient metabolic acidosis, a rise in lactate due to hypoperfusion, and a surge in potassium from intracellular shift; CRRT would typically lower creatinine and urea, not raise them, and would not cause the marked lactate spike seen here.
- Extubation: post‑extubation metabolic acidosis, transient lactate rise, and potassium surge
- CRRT: dialytic clearance of creatinine and urea, stabilization of lactate, and no significant potassium spike

**PubMed:** PMID 41689327 (Comparison of Classical Blood Cardioplegia and Modified Del ); PMID 41877111 (Clearance of small and middle molecules during continuous re)

---

## qc_00036  ·  subject None / hadm c000874

**Question:** Two patients underwent different procedures: Patient A had extubation after invasive ventilation, while Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory trajectory was observed: Bicarbonate rose from 28.0 to 32.0, Creatinine fell from 1.2 to 1.1, Platelet Count increased from 247 to 334, Potassium fluctuated between 3.6 and 3.9, Sodium rose from 134 to 139, and Urea Nitrogen remained around 33. Which patient’s procedure produced this laboratory pattern?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** The rise in bicarbonate and modest creatinine decline are typical of CRRT, but the observed pattern shows a gradual bicarbonate increase without a significant creatinine drop, matching the modest metabolic alkalosis expected after extubation rather than the pronounced bicarbonate rise and creatinine clearance seen with CRRT.
- Extubation: Gradual increase in serum bicarbonate and mild rise in sodium due to fluid shifts, with little change in creatinine
- CRRT: Marked increase in serum bicarbonate and significant reduction in creatinine and urea nitrogen due to solute clearance

**PubMed:** PMID 41615333 (Continuous Renal Replacement Therapy During Liver Transplant)

---

## qc_00037  ·  subject None / hadm c000723

**Question:** Patient A underwent extubation and Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory trajectory was observed: Bicarbonate 23.0→25.0→25.0→27.0→26.0, Creatinine 0.7→0.9→0.9→1.0→0.9, Lactate 1.6→1.6, Platelet Count 82.0→88.0→96.0, Potassium 3.6→4.1→3.5→3.5→3.4, Sodium 139.0→137.0→138.0→139.0→137.0, Urea Nitrogen 13.0→14.0→17.0→18.0→17.0. Which patient’s procedure produced this laboratory pattern?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT removes creatinine and urea, raising bicarbonate and normalizing potassium, matching the observed rise in bicarbonate, fall in creatinine, and potassium oscillation; extubation alone would not alter these renal and acid–base parameters.
- Extubation: minimal impact on renal clearance, bicarbonate, or potassium; primarily improves oxygenation.
- CRRT: enhances creatinine and urea clearance, raises bicarbonate via replacement fluid, and removes potassium, leading to the observed lab changes.

**PubMed:** PMID 41877111 (Clearance of small and middle molecules during continuous re); PMID 39601911 (Chloride removal and bicarbonate replacement by isotonic sod)

---

## qc_00038  ·  subject None / hadm c000671

**Question:** Patient A underwent extubation and Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory values were observed: Bicarbonate 20.0→21.0→20.0→23.0→26.0→25.0→25.0→24.0, Creatinine 4.2→2.6→2.3→2.2→2.3→2.4→4.0→4.7, Lactate 1.3→2.5, Platelet Count 243.0→302.0→254.0→258.0, Potassium 4.6→5.1→4.3→4.4→4.8→4.7→4.8→5.1→5.6, Sodium 139.0→138.0→140.0→139.0→138.0→140.0→139.0→133.0→133.0, Urea Nitrogen 41.0→31.0→28.0→27.0→28.0→29.0→47.0→54.0. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT removes creatinine, urea nitrogen, and potassium while adding bicarbonate, matching the observed trends; extubation alone would not cause these shifts.
- Extubation: minimal impact on renal or electrolyte labs; no significant change in creatinine, bicarbonate, or potassium.
- CRRT: rapid decline in creatinine, urea nitrogen, and potassium; rise in bicarbonate; modest platelet changes.

**PubMed:** PMID 41877111 (Clearance of small and middle molecules during continuous re); PMID 42308152 (Creatinine Paradox in CRRT: Higher Levels, Lower Mortality -)

---

## qc_00039  ·  subject None / hadm c001473

**Question:** Patient A underwent continuous renal replacement therapy (CRRT) and Patient B underwent intubation. The following post‑procedure laboratory values were observed: Bicarbonate 12.0→13.0→13.0→14.0, Creatinine 3.0→2.3→2.1→1.7, Lactate 13.9→16.0→17.0→15.0→14.8→16.0→16.0→16.0→16.0→18.0, Platelet Count 80.0→61.0→59.0→48.0, Potassium 7.2→6.2→5.7→5.8, Sodium 132.0→135.0→136.0→134.0, Urea Nitrogen 69.0→48.0→40.0→29.0. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Intubation
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT rapidly corrects acidosis and removes potassium, lowering bicarbonate and potassium while improving creatinine; intubation in a septic patient can worsen lactate due to hypoxia, explaining the persistent high lactate trend.
- CRRT: increases bicarbonate, lowers potassium, improves creatinine and urea nitrogen
- Intubation: may elevate lactate due to hypoxia and sepsis, with minimal effect on bicarbonate or potassium

**PubMed:** PMID 42130369 (High Bicarbonate Dialysis With or Without Extracorporeal Car); PMID 41877111 (Clearance of small and middle molecules during continuous re); PMID 42017096 (Early Plasma Exchange for Multiple Organ Failure Following M)

---

## qc_00040  ·  subject None / hadm c001787

**Question:** Patient A underwent continuous renal replacement therapy (CRRT) while Patient B received non‑invasive ventilation. After the procedure, the following laboratory values were observed: Bicarbonate fluctuated from 25.0 to 27.0 to 26.0 to 26.0 to 27.0 to 24.0 to 27.0 to 26.0, Creatinine decreased from 1.9 to 1.7 to 1.7 to 1.7 to 1.7 to 1.6 to 1.7, Lactate dropped from 1.1 to 0.9 to 0.9 to 1.0 to 1.0 to 1.2, Platelet Count rose from 275.0 to 272.0 to 325.0 to 384.0, Potassium fell from 4.6 to 4.4 to 4.5 to 4.4 to 4.2 to 4.1 to 4.1 to 4.2 to 4.3 to 4.6, Sodium moved from 134.0 to 136.0 to 136.0 to 134.0 to 135.0 to 137.0 to 136.0 to 133.0, and Urea Nitrogen changed from 12.0 to 11.0 to 11.0 to 13.0 to 15.0 to 12.0 to 12.0. Which patient’s procedure produced this post‑procedure laboratory pattern?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Non-invasive Ventilation
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** CRRT removes creatinine, urea, and potassium while replacing bicarbonate, producing the observed decreases in creatinine, potassium, and urea and the transient bicarbonate shifts; non‑invasive ventilation does not alter these electrolytes or creatinine.
- CRRT: dialytic clearance of creatinine, urea, and potassium with bicarbonate replacement, leading to lowered creatinine, urea, potassium and variable bicarbonate
- Non‑invasive ventilation: no significant effect on renal clearance or electrolyte levels; bicarbonate and creatinine remain stable

**PubMed:** PMID 37558740 (Kinetics of small and middle molecule clearance during conti); PMID 41877111 (Clearance of small and middle molecules during continuous re); PMID 39601911 (Chloride removal and bicarbonate replacement by isotonic sod)

---

## qc_00041  ·  subject None / hadm c001352

**Question:** Patient A underwent continuous renal replacement therapy (CRRT) and Patient B underwent intubation. The following post‑procedure laboratory trajectory was observed: Bicarbonate rose from 18.0 to 28.0, then fluctuated, ending at 18.0; Creatinine fell from 3.7 to 0.8; Lactate decreased from 5.5 to 10.9; Platelet count dropped from 108 to 44; Potassium decreased from 5.1 to 4.9; Sodium decreased from 140 to 130; Urea nitrogen fell from 45 to 10. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Intubation
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** CRRT removes uremic toxins and corrects acid–base disturbances, explaining the rapid rise in bicarbonate, decline in creatinine, urea nitrogen, and potassium, and the transient drop in platelets due to filter contact; intubation alone would not produce such pronounced metabolic changes.
- CRRT: increases serum bicarbonate, lowers creatinine, urea nitrogen, and potassium, and can transiently reduce platelet count
- Intubation: minimal direct effect on bicarbonate, creatinine, or electrolytes; may modestly affect lactate via ventilation changes

**PubMed:** PMID 42130369 (High Bicarbonate Dialysis With or Without Extracorporeal Car); PMID 41765054 (A novel serum phosphorus to chloride and bicarbonate ratio p); PMID 41263458 (Continuous Renal Replacement Therapy in Pediatric Sepsis and)

---

## qc_00042  ·  subject None / hadm c001609

**Question:** Patient A underwent continuous renal replacement therapy (CRRT) while Patient B received non‑invasive ventilation. The following post‑procedure laboratory values were recorded: Bicarbonate 24.0→25.0→25.0→25.0, Creatinine 0.6→0.7→0.5, Hemoglobin 10.6, Lactate 0.8→0.9→0.8→0.9→0.9→0.8, Platelet Count 187.0→183.0→159.0, Potassium 3.8→4.0→4.0→3.9, Sodium 132.0→135.0→137.0→135.0, Urea Nitrogen 14.0→19.0. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Non-invasive Ventilation
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** The modest rise in creatinine, urea nitrogen and potassium, together with a slight increase in bicarbonate, is characteristic of the solute clearance and fluid shifts seen after CRRT, whereas non‑invasive ventilation alone would not alter these values.
- CRRT: Gradual reduction of creatinine, urea nitrogen, and potassium with a modest rise in bicarbonate due to dialysate composition.
- Non‑invasive ventilation: No significant change in renal solutes or electrolytes; laboratory values remain stable.

**PubMed:** PMID 41877111 (Clearance of small and middle molecules during continuous re); PMID 41877111 (Clearance of small and middle molecules during continuous re)

---

## qc_00043  ·  subject None / hadm c000139

**Question:** Two patients underwent different procedures: Patient A was extubated after prolonged mechanical ventilation, while Patient B received continuous renal replacement therapy (CRRT). Both had similar baseline labs. After the procedures, the following lab trajectory was observed: Bicarbonate 20.0→17.0→16.0, Creatinine 2.7→2.6, Lactate 4.0→4.6→4.9, Platelet Count 70.0→75.0, Potassium 4.6→5.9→5.9, Sodium 137.0→137.0→132.0, Urea Nitrogen 37.0→36.0. Which patient’s procedure produced this post‑procedure lab pattern?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT removes bicarbonate and can cause metabolic acidosis, explaining the progressive drop in bicarbonate; it also clears creatinine, matching the slight decrease, and can lead to hyperkalemia when the dialysate potassium is low, consistent with the rise to 5.9 mmol/L. Extubation alone would not produce such a marked acidosis or hyperkalemia.
- Extubation: Minimal impact on bicarbonate, creatinine, or potassium; may transiently raise lactate if hypoventilation occurs.
- CRRT: Bicarbonate loss and metabolic acidosis; creatinine clearance; potential hyperkalemia if dialysate potassium is low; modest lactate changes.

**PubMed:** PMID 39601911 (Chloride removal and bicarbonate replacement by isotonic sod); PMID 41877111 (Clearance of small and middle molecules during continuous re); PMID 40435983 (Chloride Mass Transfers during Continuous Veno-Venous Hemodi)

---

## qc_00044  ·  subject None / hadm c000656

**Question:** Patient A underwent extubation and Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory values were observed: Bicarbonate 24.0→26.0→25.0→26.0→25.0→24.0 mmol/L, Creatinine 2.0→1.9→2.6→2.9→3.2→3.1 mg/dL, Platelet Count 182→192→228 ×10⁹/L, Potassium 4.3→4.2→4.8→4.9→5.3→4.4 mmol/L, Sodium 134→134→132→130→130→130 mmol/L, Urea Nitrogen 34→32→45→52→62→68 mg/dL. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT removes solutes such as creatinine, urea nitrogen, and potassium, causing the observed rise in urea nitrogen and potassium despite initial decreases, whereas extubation has no such effect on renal clearance.
- Extubation: No significant change in renal solute clearance; labs remain largely unchanged.
- CRRT: Continuous removal of creatinine, urea nitrogen, and potassium, leading to fluctuating levels as the filter clears and re‑accumulates solutes.

**PubMed:** PMID 36382094 (Optimal stage of initiating continuous renal replacement the); PMID 41332109 ([Performance evaluation of different filtration fractions du)

---

## qc_00045  ·  subject None / hadm c000681

**Question:** Patient A underwent extubation and Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory values were observed: Bicarbonate 24.0→24.0→23.0→28.0, Creatinine 1.3→1.4→1.5→1.6→1.5→1.3, Platelet Count 82.0→77.0→74.0→58.0, Potassium 5.1→4.9→5.1→4.9→4.0→3.5, Sodium 141.0→137.0→137.0→143.0, Urea Nitrogen 18.0→22.0→26.0→31.0→35.0→34.0. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** Extubation in a patient with pre‑existing AKI and sepsis typically causes a transient rise in creatinine and urea due to fluid shifts and catabolism, while CRRT would lower these values; the observed creatinine peak and subsequent decline match extubation physiology, not CRRT.
- Extubation: Transient increase in creatinine and urea nitrogen from fluid shifts and catabolism, with modest bicarbonate change.
- CRRT: Gradual reduction of creatinine and urea nitrogen with stable bicarbonate, not a peak followed by decline.

**PubMed:** PMID 41261569 (Comparative evaluation of continuous renal replacement thera); PMID 41948244 (Diabetic Ketoacidosis Complicated by Cerebral and Pulmonary )

---

## qc_00046  ·  subject None / hadm c001346

**Question:** Patient A underwent continuous renal replacement therapy (CRRT) and Patient B underwent intubation. The following post‑procedure laboratory values were observed: Bicarbonate 18.0, Creatinine 4.2, Lactate 1.3, Platelet Count 53.0, Potassium 4.5, Sodium 137.0, Urea Nitrogen 90.0. Which patient’s procedure produced this laboratory profile?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Intubation
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** The marked rise in creatinine and urea nitrogen is typical of acute kidney injury that can be precipitated by the hemodynamic instability of intubation, whereas CRRT would normally lower these values; the drop in bicarbonate and potassium is consistent with the metabolic derangements seen after intubation and ventilation, not with the bicarbonate‑replacement effect of CRRT.
- CRRT: CRRT typically reduces creatinine, urea nitrogen, and corrects metabolic acidosis by adding bicarbonate to the replacement fluid.
- Intubation: Intubation can transiently worsen renal perfusion, raising creatinine and urea nitrogen, and may cause a drop in bicarbonate and potassium due to ventilation‑induced alkalosis and fluid shifts.

**PubMed:** PMID 41247497 (Comparison of two different bicarbonate replacement fluids d); PMID 41615333 (Continuous Renal Replacement Therapy During Liver Transplant)

---

## qc_00047  ·  subject None / hadm c001261

**Question:** Patient A underwent continuous renal replacement therapy (CRRT) and Patient B underwent intubation. The following post‑procedure laboratory values were observed: Bicarbonate 28.0→26.0→25.0→28.0→26.0→27.0, Creatinine 0.9→0.9→0.9→0.8→0.7→0.9, Lactate 1.5→2.0→2.5→1.9→1.8→2.4→2.6→1.7→2.1, Platelet Count 77.0→70.0→79.0→67.0→60.0, Potassium 3.8→4.3→5.1→4.6→4.9→4.6→4.6, Sodium 139.0→138.0→140.0→139.0→141.0→142.0, Urea Nitrogen 16.0→12.0→16.0→16.0→19.0. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Intubation
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT (Patient A) typically lowers creatinine and urea nitrogen and can clear lactate, but the observed creatinine drop to 0.7 and sustained lactate rise are inconsistent with CRRT; intubation (Patient B) does not alter these labs, matching the pattern.
- CRRT: reduces creatinine and urea nitrogen, clears lactate, and may lower potassium
- Intubation: minimal direct effect on creatinine, urea nitrogen, lactate, or potassium

**PubMed:** PMID 41854309 (Regional citrate anticoagulation prolongs filter lifespan an); PMID 41598217 (Peak Lactate Within 24 h and Mortality in Septic Shock Patie); PMID 42130369 (High Bicarbonate Dialysis With or Without Extracorporeal Car)

---

## qc_00048  ·  subject None / hadm c001521

**Question:** Patient A underwent continuous renal replacement therapy (CRRT) while Patient B received non‑invasive ventilation. After the procedure, the following laboratory values were observed: Bicarbonate 31.0 mEq/L, Creatinine 2.1 mg/dL, Platelet Count 278.0 ×10^9/L, Potassium 3.6 mEq/L, Sodium 149.0 mEq/L, Urea Nitrogen 50.0 mg/dL. Which patient’s procedure produced this post‑procedure laboratory profile?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Non-invasive Ventilation
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT in Patient A would have markedly increased bicarbonate and lowered potassium, but would not raise creatinine to 2.1 mg/dL; the observed creatinine and potassium trajectory matches the expected improvement from diuretic and renal recovery in Patient B, not the dialysis‑induced metabolic changes of CRRT.
- CRRT: raises serum bicarbonate, lowers serum potassium, and can transiently elevate creatinine due to fluid shifts
- Non‑invasive ventilation: improves ventilation without altering bicarbonate or potassium, allowing renal recovery to lower creatinine and stabilize potassium

**PubMed:** PMID 42130369 (High Bicarbonate Dialysis With or Without Extracorporeal Car); PMID 41877111 (Clearance of small and middle molecules during continuous re)

---

## qc_00049  ·  subject None / hadm c000359

**Question:** Patient A underwent extubation and Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory values were recorded: Bicarbonate rose from 20.0 to 29.0 mmol/L, Creatinine fell from 4.8 to 2.2 mg/dL, Lactate decreased from 2.0 to 1.3 mmol/L, Platelet count fluctuated from 298 to 164, Potassium dropped from 6.8 to 3.5 mmol/L, Sodium increased from 136 to 139 mmol/L, and Urea Nitrogen fell from 32 to 19 mg/dL. Which patient’s procedure produced this laboratory trajectory?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT removes uremic toxins and electrolytes, lowering creatinine, potassium, and urea while correcting acidosis (bicarbonate rise) and improving lactate clearance; extubation has no such metabolic effect.
- Extubation: minimal impact on renal or electrolyte labs; no significant change in creatinine, bicarbonate, or potassium
- CRRT: reduces serum creatinine, potassium, and urea; increases bicarbonate; improves lactate clearance

**PubMed:** PMID 41050122 (Optimizing a Dose Prescription as the First Step of Green Co); PMID 42362664 (Serum magnesium and adverse prognosis in acute pancreatitis ); PMID 41877111 (Clearance of small and middle molecules during continuous re)

---

## qc_00050  ·  subject None / hadm c000133

**Question:** Patient A underwent extubation and Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory trend was observed: Bicarbonate 24.0→27.0→25.0→23.0→24.0→20.0→25.0, Creatinine 2.5→2.3→2.3→3.5→3.9, Lactate 2.0→2.1→1.9→2.1→2.7→2.1→9.8, Platelet Count 194.0→141.0→118.0→107.0→95.0, Potassium 4.0→3.6→3.7→4.3→5.4→4.5→4.1→4.9→5.4, Sodium 132.0→131.0→130.0→130.0→126.0→134.0, Urea Nitrogen 29.0→24.0→24.0→41.0→47.0. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT removes creatinine and urea nitrogen, explaining the initial drop and subsequent rise as renal function improves, while the therapy’s dialysate composition and citrate anticoagulation cause transient shifts in potassium and bicarbonate, matching the observed oscillations; extubation alone would not produce such marked changes in renal clearance or electrolyte dynamics.
- Extubation: minimal impact on creatinine, urea nitrogen, or electrolyte levels; primarily improves ventilation status.
- CRRT: reduces creatinine and urea nitrogen, alters potassium and bicarbonate via dialysate and citrate anticoagulation, and can transiently affect platelet count.

**PubMed:** PMID 42129846 (Metabolic complications of citrate anticoagulation in contin); PMID 41553965 (Intraoperative Continuous Renal Replacement Therapy in Non-C)

---

## qc_00051  ·  subject None / hadm c001342

**Question:** Two patients underwent different procedures: one received continuous renal replacement therapy (CRRT) and the other was intubated. Their pre‑procedure laboratory values are shown below. After the procedures, the following laboratory trajectory was observed: bicarbonate decreased from 22.0 to 18.0, creatinine rose from 1.1 to 0.9, lactate increased from 0.9 to 1.3, platelet count fluctuated around 95–105, potassium rose from 4.3 to 4.9, sodium remained near 140, and urea nitrogen increased from 17.0 to 30.0. Which patient’s procedure produced this post‑procedure laboratory pattern?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Intubation
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** CRRT removes nitrogenous waste and bicarbonate, explaining the rise in urea nitrogen and drop in bicarbonate; it also clears creatinine, matching the observed creatinine trend, whereas intubation alone does not produce these changes.
- CRRT: reduces bicarbonate, clears creatinine and urea nitrogen, modestly lowers potassium
- Intubation: minimal direct effect on bicarbonate, creatinine, urea nitrogen, potassium; primarily affects oxygenation

**PubMed:** PMID 42130369 (High Bicarbonate Dialysis With or Without Extracorporeal Car); PMID 41615333 (Continuous Renal Replacement Therapy During Liver Transplant)

---

## qc_00052  ·  subject None / hadm c001134

**Question:** Two patients underwent different procedures: Patient A received continuous renal replacement therapy (CRRT) and Patient B was intubated. After the procedures, the following laboratory values were observed: Bicarbonate increased from 27.0 to 30.0 mmol/L, Creatinine rose from 1.9 to 2.9 mg/dL, Hemoglobin 8.5 g/dL, Lactate fluctuated around 2.2–2.7 mmol/L, Platelet Count dropped to 58–116 ×10^9/L, Potassium decreased from 5.4 to 4.0 mmol/L, Sodium remained ~144 mmol/L, and Urea Nitrogen varied between 57–65 mg/dL. Which patient’s procedure produced this post‑procedure laboratory profile?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Intubation
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** CRRT removes acid and bicarbonate, correcting metabolic acidosis and raising serum bicarbonate, while also clearing creatinine and urea, explaining the rise in bicarbonate and creatinine; it also removes potassium, accounting for the drop in potassium, and can cause platelet activation leading to a transient drop in platelet count. Intubation alone does not produce these electrolyte and renal changes.
- CRRT: increases serum bicarbonate, removes creatinine/urea, lowers potassium, may transiently lower platelets
- Intubation: minimal direct effect on bicarbonate, creatinine, potassium, or platelets; changes are usually secondary to ventilation status

**PubMed:** PMID 42130369 (High Bicarbonate Dialysis With or Without Extracorporeal Car); PMID 41090683 (Impact of enteral nutrition guidance on immune function in C); PMID 42078230 (Profound Asymptomatic Hyponatremia Associated With Anuric Ac)

---

## qc_00053  ·  subject None / hadm c000498

**Question:** Patient A underwent extubation and Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory values were observed: Bicarbonate 19.0→24.0→21.0→22.0 mmol/L, Creatinine 1.7→2.8→3.1→3.0→3.4 mg/dL, Platelet Count 170.0→172.0→181.0→192.0 ×10⁹/L, Potassium 5.2→5.4→5.1→5.4→5.1 mmol/L, Sodium 137.0→133.0→134.0→132.0 mmol/L, Urea Nitrogen 38.0→54.0→59.0→77.0→83.0 mg/dL. Which patient’s procedure produced this laboratory trajectory?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** The rise in creatinine and urea nitrogen with only modest bicarbonate changes is characteristic of impaired renal clearance, which is expected after extubation in a patient with pre‑existing CKD and AKI; CRRT would have lowered creatinine and urea, not increased them.
- Extubation: Minimal impact on creatinine/urea; may worsen acidosis if ventilation is reduced, leading to stable or slightly lower bicarbonate.
- CRRT: Significant removal of creatinine and urea, correction of acidosis with increased bicarbonate, and potential potassium shifts toward lower levels.

**PubMed:** PMID 41877111 (Clearance of small and middle molecules during continuous re); PMID 42194945 (PaCO2 as a Possible Treatable Trait in Acute Respiratory Fai)

---

## qc_00054  ·  subject None / hadm c000162

**Question:** Patient A underwent extubation and Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory trajectory was observed: Bicarbonate 21.0→20.0→25.0→24.0, Creatinine 2.2→2.1→2.5→2.9, Lactate 4.6, Platelet Count 167.0→223.0, Potassium 5.2→4.7→4.9→5.2→5.4, Sodium 131.0→128.0→131.0→129.0→125.0, Urea Nitrogen 43.0→39.0→46.0→56.0. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT removes creatinine and urea, explaining the initial drop then rise as fluid shifts occur; it also causes transient potassium and sodium shifts and can raise platelet counts by reducing inflammatory mediators, matching the observed pattern, whereas extubation has no such metabolic effects.
- Extubation: minimal impact on creatinine, urea, electrolytes, or platelets; no systematic trend in these labs
- CRRT: initial decrease in creatinine and urea, transient potassium and sodium shifts, and platelet count rise due to removal of inflammatory mediators

**PubMed:** PMID 36472056 (Treatment Efficacy of Continuous Renal Replacement on Sympto); PMID 27885969 (36th International Symposium on Intensive Care and Emergency)

---

## qc_00055  ·  subject None / hadm c000356

**Question:** Two patients underwent different procedures: Patient A had extubation, and Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory trajectory was observed: bicarbonate fluctuated from 21.0 to 26.0 mEq/L, creatinine rose to 2.1 mg/dL then fell to 1.3 mg/dL, lactate peaked at 4.1 mmol/L and then declined, platelet count dropped from 81 to 19 ×10⁹/L, potassium varied between 3.9 and 5.0 mmol/L, sodium rose to 138 mmol/L, and urea nitrogen increased to 29 mg/dL before decreasing. Which patient’s procedure produced this laboratory pattern?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT removes creatinine and urea, explaining the initial rise then fall of creatinine and urea nitrogen; it also causes platelet consumption and potassium shifts, matching the observed platelet drop and potassium oscillation, whereas extubation has no such renal or hematologic effects.
- Extubation: minimal impact on renal clearance, platelets, or electrolytes
- CRRT: reduces creatinine/urea, consumes platelets, and alters potassium and lactate levels

**PubMed:** PMID 39134011 (Coagulation Risk Predicting in Anticoagulant-Free Continuous); PMID 42088147 (Regional citrate anticoagulation for renal replacement thera); PMID 41999944 (Nafamostat mesilate improves sepsis outcomes by modulating c)

---

## qc_00056  ·  subject None / hadm c000460

**Question:** Patient A underwent extubation and Patient B underwent continuous renal replacement therapy (CRRT). Following the procedures, the following laboratory values were recorded: Bicarbonate 22.0→21.0→23.0→24.0→24.0→22.0→24.0→24.0→25.0→23.0→24.0, Creatinine 2.1→1.8→1.8→1.6→1.8→3.0→2.5→2.1→1.8→1.8→1.7, Lactate 1.7→2.6→1.6→1.3→1.4→1.3→1.2→1.0→1.0→1.2→0.9→0.9, Platelet Count 353.0→308.0→291.0→300.0→238.0→247.0→240.0→279.0→270.0→275.0→257.0, Potassium 4.8→4.9→4.6→4.2→4.2→4.4→4.5→4.3→4.2→4.4→4.3, Sodium 141.0→142.0→140.0→140.0→137.0→140.0→142.0→140.0→140.0→140.0→138.0, Urea Nitrogen 27.0→25.0→23.0→22.0→21.0→31.0→26.0→20.0→17.0→17.0→15.0. Which patient’s procedure produced this post‑procedure laboratory trajectory?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT removes potassium and urea, raises bicarbonate, and lowers creatinine, matching the observed trends; extubation alone would not alter these metabolic parameters.
- Extubation: minimal impact on serum electrolytes, bicarbonate, or creatinine
- CRRT: reduces potassium and urea, increases bicarbonate, and lowers creatinine

**PubMed:** PMID 41877111 (Clearance of small and middle molecules during continuous re); PMID 42130369 (High Bicarbonate Dialysis With or Without Extracorporeal Car); PMID 41090683 (Impact of enteral nutrition guidance on immune function in C)

---

## qc_00057  ·  subject None / hadm c001122

**Question:** Patient A underwent continuous renal replacement therapy (CRRT) and Patient B underwent intubation. The following post‑procedure laboratory values were recorded: Bicarbonate: 25.0→26.0→29.0→29.0→31.0, Creatinine: 1.5→1.5→1.5→1.5→1.6, Lactate: 1.2→1.0→0.9→0.9, Platelet Count: 239.0→239.0→191.0→180.0, Potassium: 5.0→4.9→4.5→3.7→3.9→3.9→3.9→3.5, Sodium: 131.0→137.0→135.0→136.0→135.0, Urea Nitrogen: 78.0→75.0→71.0→68.0→69.0. Which patient’s procedure produced this laboratory trajectory?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Intubation
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** Intubation (Patient B) is associated with a transient rise in bicarbonate and a modest drop in potassium due to catecholamine‑mediated shifts, whereas CRRT (Patient A) would have caused a more pronounced potassium removal and a gradual rise in bicarbonate from dialysate buffering; the observed mild bicarbonate increase and modest potassium fall are more consistent with the intubation‑related metabolic changes seen in Patient B.
- CRRT: Continuous removal of potassium and urea, bicarbonate replacement in dialysate, and platelet activation leading to a drop in platelet count.
- Intubation: Catecholamine surge can raise bicarbonate transiently and shift potassium intracellularly, with minimal impact on urea nitrogen or platelet count.

**PubMed:** PMID 41877111 (Clearance of small and middle molecules during continuous re); PMID 39601911 (Chloride removal and bicarbonate replacement by isotonic sod)

---

## qc_00058  ·  subject None / hadm c001003

**Question:** Patient A underwent continuous renal replacement therapy (CRRT) and Patient B underwent intubation. The following post‑procedure laboratory values were recorded: Bicarbonate 15.0, Creatinine 2.0, Lactate 5.7, Platelet Count 144, Potassium 4.4, Sodium 126, Urea Nitrogen 41. Which patient’s procedure produced this laboratory profile?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Intubation
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** Intubation with mechanical ventilation increases lactate and reduces bicarbonate due to hypoventilation and tissue hypoxia, while CRRT typically corrects acidosis and improves renal clearance, lowering creatinine and urea; the observed low bicarbonate, high lactate, and unchanged creatinine are consistent with intubation alone.
- CRRT: improves acid–base status (↑bicarbonate), reduces creatinine and urea, and may modestly lower potassium
- Intubation: can worsen acidosis (↓bicarbonate) and raise lactate due to hypoxia, with minimal effect on creatinine

**PubMed:** PMID 42130369 (High Bicarbonate Dialysis With or Without Extracorporeal Car); PMID 42017096 (Early Plasma Exchange for Multiple Organ Failure Following M)

---

## qc_00059  ·  subject None / hadm c000645

**Question:** Patient A underwent extubation and Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory trend was observed: Bicarbonate decreased from 22.0 to 16.0, Creatinine rose from 2.9 to 4.8, Lactate fell from 1.0 to 0.7, Platelet count fluctuated, Potassium increased from 4.7 to 4.8, Sodium remained around 142, and Urea Nitrogen rose from 111 to 148. Which patient’s procedure produced this laboratory pattern?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** Extubation in a patient with chronic kidney disease and metabolic acidosis typically worsens acid–base status and raises serum creatinine due to reduced perfusion, matching the observed decline in bicarbonate and rise in creatinine; CRRT would instead lower creatinine and raise bicarbonate, which is inconsistent with the trend.
- Extubation: Can precipitate metabolic acidosis and increase creatinine in CKD patients due to hypoventilation and reduced renal perfusion.
- CRRT: Reduces serum creatinine and improves bicarbonate by removing waste and correcting acid–base disturbances.

**PubMed:** PMID 41261569 (Comparative evaluation of continuous renal replacement thera); PMID 42326233 (Delayed Emergence Due to Severe Respiratory Acidosis Followi)

---

## qc_00060  ·  subject None / hadm c000983

**Question:** Patient A underwent continuous renal replacement therapy (CRRT) and Patient B underwent intubation. After the procedures, the following laboratory values were recorded: bicarbonate remained 24.0, creatinine fluctuated around 2.4–2.5, lactate was 0.8, platelet count rose to 251, potassium oscillated between 3.3 and 4.6, sodium stayed 144–145, and urea nitrogen decreased from 38 to 36. Which patient’s procedure produced this post‑procedure laboratory profile?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Intubation
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** The observed lactate of 0.8 and stable bicarbonate are consistent with the metabolic effects of intubation, which does not alter acid–base status, whereas CRRT would typically lower lactate and raise bicarbonate; the modest potassium shifts and urea nitrogen decline are also more compatible with the small fluid shifts of intubation than the significant solute removal of CRRT.
- CRRT: reduces lactate, increases bicarbonate, removes potassium and urea, often lowering creatinine
- Intubation: minimal impact on lactate, bicarbonate, potassium, urea or creatinine; may cause slight fluid shifts

**PubMed:** PMID 42178010 (Metformin-associated lactic acidosis: Bridging pharmacokinet); PMID 41854309 (Regional citrate anticoagulation prolongs filter lifespan an); PMID 41878413 (Outcomes of Extracorporeal Removal in Acute Barium Poisoning)

---

## qc_00061  ·  subject None / hadm c000300

**Question:** Two patients underwent different procedures: Patient A had extubation after invasive ventilation, while Patient B received continuous renal replacement therapy (CRRT) for acute kidney injury. Their pre‑procedure labs are shown below. After the procedures, one patient’s labs evolved as follows: bicarbonate rose from 23 to 32 mmol/L, creatinine fell from 2.3 to 1.0 mg/dL, hemoglobin increased from 9.0 to 10.4 g/dL, lactate rose from 1.0 to 2.2 mmol/L, platelet count rose from 126 to 199 ×10^9/L, potassium fell from 4.3 to 3.6 mmol/L, sodium fluctuated around 136 mmol/L, and urea nitrogen fell from 47 to 13 mg/dL. Which patient’s procedure produced this post‑procedure laboratory trajectory?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT removes creatinine, urea, and potassium while adding bicarbonate, explaining the marked declines in creatinine, urea nitrogen, and potassium and the rise in bicarbonate; the modest lactate increase reflects CRRT‑related metabolic shifts, whereas extubation alone would not produce such pronounced renal clearance or bicarbonate changes.
- Extubation: Minimal impact on renal clearance or bicarbonate; hemoglobin may rise slightly from fluid shifts, but creatinine, urea, potassium, and lactate remain largely unchanged.
- CRRT: Rapid decline in creatinine, urea nitrogen, and potassium; increase in bicarbonate; modest lactate rise; platelet count may rise due to removal of inflammatory mediators.

**PubMed:** PMID 16750454 (Metformin-associated lactic acidosis treated with continuous); PMID 32699722 (Metformin Associated Lactic Acidosis in the Intensive Care U); PMID 37558740 (Kinetics of small and middle molecule clearance during conti)

---

## qc_00062  ·  subject None / hadm c001817

**Question:** Two patients underwent different procedures: Patient A received continuous renal replacement therapy (CRRT) and Patient B received non‑invasive ventilation. After the procedures, the following laboratory values were observed: Bicarbonate 24.0→21.0→21.0→20.0→20.0→20.0→20.0→19.0→20.0→21.0, Creatinine 3.9→3.3→3.9→2.7→2.4→2.1→1.9→1.8→1.7→2.0, Lactate 1.2→1.1→1.1, Platelet Count 117.0→119.0→65.0→108.0, Potassium 4.4→4.7→5.1→5.1→5.1→5.0→4.8→4.6→4.4→4.4, Sodium 133.0→132.0→131.0→133.0→134.0→134.0→134.0→134.0→134.0→133.0, Urea Nitrogen 103.0→79.0→79.0→38.0→27.0→24.0→20.0→20.0→24.0. Which patient’s procedure produced this post‑procedure laboratory trajectory?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Non-invasive Ventilation
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** CRRT rapidly clears creatinine, urea nitrogen, and potassium while replacing bicarbonate, producing the observed declines and fluctuations; non‑invasive ventilation has no such metabolic effect.
- CRRT: continuous removal of creatinine, urea nitrogen, and potassium; bicarbonate replacement raises serum bicarbonate.
- Non‑invasive ventilation: minimal direct impact on renal clearance or electrolyte balance.

**PubMed:** PMID 41877111 (Clearance of small and middle molecules during continuous re); PMID 39601911 (Chloride removal and bicarbonate replacement by isotonic sod); PMID 33523772 (ISPD guidelines for peritoneal dialysis in acute kidney inju)

---

## qc_00063  ·  subject None / hadm c000968

**Question:** Patient A underwent continuous renal replacement therapy (CRRT) and Patient B underwent intubation. The following post-procedure laboratory values were observed: Bicarbonate: 24.0→18.0→17.0→18.0→16.0→17.0→17.0, Creatinine: 1.9→2.2→2.6→2.9→3.2→3.4→3.5, Hemoglobin: 9.0→11.5, Lactate: 1.4→1.2→1.5→1.5, Platelet Count: 260.0→255.0→271.0→256.0→248.0, Potassium: 5.0→4.6→4.3→3.9→4.3→4.2→4.2→4.7, Sodium: 144.0→132.0→133.0→129.0→132.0→132.0→131.0→129.0, Urea Nitrogen: 41.0→46.0→58.0→69.0→84.0→99.0→109.0. Which patient’s procedure produced this post-state?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Intubation
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** The progressive metabolic acidosis, rising creatinine and urea nitrogen, and transient potassium shift are classic for CRRT, matching Patient B’s intubation‑associated CRRT, whereas Patient A’s CRRT would not produce the same pattern of rising renal markers.
- CRRT: causes metabolic acidosis, increases creatinine and urea nitrogen, and can transiently lower potassium due to dialysate composition
- Intubation: does not markedly alter bicarbonate, creatinine, or urea nitrogen; may modestly affect potassium via ventilation changes

**PubMed:** PMID 42130369 (High Bicarbonate Dialysis With or Without Extracorporeal Car); PMID 41263458 (Continuous Renal Replacement Therapy in Pediatric Sepsis and)

---

## qc_00064  ·  subject None / hadm c001554

**Question:** Patient A underwent continuous renal replacement therapy (CRRT) and Patient B received non‑invasive ventilation. The following post‑procedure laboratory values were observed: Bicarbonate 23.0→26.0→27.0, Creatinine 0.4→0.5→0.5→0.5→0.6, Lactate 1.3→1.2→1.5→1.4→0.9, Platelet Count 99.0→105.0→110.0, Potassium 6.5→4.0→4.0→4.1→3.7→5.6→3.7→4.0, Sodium 138.0→139.0→136.0→138.0→137.0→136.0→137.0→137.0, Urea Nitrogen 12.0→11.0→13.0→13.0→11.0. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Non-invasive Ventilation
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** The gradual rise in bicarbonate and the transient potassium spikes are characteristic of CRRT’s bicarbonate replacement and potassium removal, whereas non‑invasive ventilation does not alter these electrolytes in the same pattern.
- CRRT: Bicarbonate increases due to bicarbonate‑based replacement fluid; potassium is removed, causing transient drops and later rebounds.
- Non‑invasive ventilation: Minimal direct effect on bicarbonate or potassium; changes are usually due to ventilation status rather than dialysis.

**PubMed:** PMID 39601911 (Chloride removal and bicarbonate replacement by isotonic sod); PMID 41877111 (Clearance of small and middle molecules during continuous re)

---

## qc_00065  ·  subject None / hadm c001777

**Question:** Two patients underwent different procedures: Patient A received continuous renal replacement therapy (CRRT) while Patient B received non‑invasive ventilation. The following post‑procedure laboratory values were observed: Bicarbonate rose from 21.0 to 28.0 mmol/L, Creatinine fell from 3.2 to 2.4 mg/dL, Lactate fluctuated but ended at 1.2 mmol/L, Platelet count dropped to 97×10⁹/L, Potassium decreased from 5.9 to 3.4 mmol/L, Sodium increased to 143 mmol/L, and Urea Nitrogen fell to 15 mg/dL. Which patient’s procedure produced this laboratory trajectory?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Non-invasive Ventilation
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** CRRT removes potassium and corrects acidosis, producing the observed potassium decline and bicarbonate rise; it also clears urea and creatinine, matching the reductions seen, whereas non‑invasive ventilation has no such renal effects.
- CRRT: continuous removal of potassium and urea, correction of metabolic acidosis (↑bicarbonate), and reduction of creatinine
- Non‑invasive ventilation: no significant impact on renal solute clearance or acid–base status

**PubMed:** PMID 39601911 (Chloride removal and bicarbonate replacement by isotonic sod); PMID 24929959 (Continuous renal replacement therapy (CRRT) for rhabdomyolys)

---

## qc_00066  ·  subject None / hadm c001771

**Question:** Two patients underwent different procedures: Patient A received continuous renal replacement therapy (CRRT) for acute kidney injury, while Patient B underwent non‑invasive ventilation for respiratory support. After the procedures, the following laboratory values were recorded in sequence: Bicarbonate 24.0→22.0→23.0 mmol/L, Creatinine 2.9→4.3→2.6 mg/dL, Platelet Count 200.0→189.0→207.0 ×10⁹/L, Potassium 4.5→4.3→4.3 mmol/L, Sodium 139.0→141.0→142.0 mmol/L, Urea Nitrogen 46.0→77.0→33.0 mg/dL. Which patient’s procedure produced this post‑procedure laboratory trajectory?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Non-invasive Ventilation
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT removes urea and creatinine, producing the observed rise and subsequent fall in these values, whereas non‑invasive ventilation has no direct effect on renal solute clearance; the pattern of creatinine and urea nitrogen is therefore consistent only with Patient B’s CRRT procedure.
- CRRT: Rapid removal of urea and creatinine, leading to transient increases followed by normalization; modest correction of metabolic acidosis and potassium shifts
- Non‑invasive ventilation: Primarily improves oxygenation and ventilation; minimal direct impact on renal solute levels

**PubMed:** PMID 30905252 (Solutes removal characteristics at various effluent rates du); PMID 34839601 (Effects of regional citrate anticoagulation in continuous ve)

---

## qc_00067  ·  subject None / hadm c001026

**Question:** Patient A underwent continuous renal replacement therapy (CRRT) and Patient B underwent intubation. After the procedures, the following laboratory values were observed: Bicarbonate 32.0→30.0→30.0→27.0→24.0→26.0→26.0→28.0→27.0→26.0, Creatinine 1.5→1.5→1.3→1.4→1.4→1.5→1.6→3.1→3.5, Lactate 1.3→1.5→1.3→1.2→0.9→0.9→1.0, Platelet Count 160.0→158.0→209.0→182.0→168.0, Potassium 4.5→4.6→4.6→4.5→5.3→5.1→4.5→4.1→3.9→4.4, Sodium 138.0→137.0→136.0→137.0→136.0→137.0→138.0→140.0→137.0→135.0, Urea Nitrogen 17.0→16.0→15.0→14.0→15.0→15.0→15.0→33.0→41.0. Which patient’s procedure produced this post‑procedure laboratory profile?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Intubation
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** CRRT removes urea and creatinine, raises bicarbonate, and can transiently lower potassium, matching the observed trends; intubation alone does not produce such marked changes in these labs.
- CRRT: increases bicarbonate, decreases creatinine and urea nitrogen, and removes potassium
- Intubation: minimal direct effect on bicarbonate, creatinine, urea nitrogen, or potassium; may cause mild metabolic changes

**PubMed:** PMID 22812253 (Continuous blood purification therapy on 16 patients with di)

---

## qc_00068  ·  subject None / hadm c001478

**Question:** Two patients underwent different procedures: Patient A received continuous renal replacement therapy (CRRT) and Patient B underwent intubation. After the procedures, the following laboratory values were observed: Bicarbonate 22.0 mEq/L, Creatinine 2.7 mg/dL, Lactate 1.8 mmol/L, Platelet Count 40.0 ×10⁹/L, Potassium 5.9 mmol/L, Sodium 136.0 mmol/L, Urea Nitrogen 29.0 mg/dL. Which patient’s procedure produced this post‑procedure laboratory profile?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Intubation
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** CRRT removes creatinine and urea, corrects metabolic acidosis (raising bicarbonate), and can cause modest platelet activation leading to a transient drop; intubation alone does not alter these renal or acid–base parameters.
- CRRT: decreases creatinine and urea, raises bicarbonate, may transiently lower platelets
- Intubation: no significant change in renal clearance or acid–base status

**PubMed:** PMID 42130369 (High Bicarbonate Dialysis With or Without Extracorporeal Car); PMID 41615333 (Continuous Renal Replacement Therapy During Liver Transplant)

---

## qc_00069  ·  subject None / hadm c001404

**Question:** Patient A underwent continuous renal replacement therapy (CRRT) and Patient B underwent intubation. The following post‑procedure laboratory trajectory was observed: Bicarbonate rose from 18.0 to 22.0, Creatinine fell from 5.2 to 3.9, Hemoglobin fluctuated but remained around 8–9, Lactate decreased from 1.2 to 0.7, Platelet Count stayed near 135, Potassium decreased slightly, Sodium increased from 139 to 141, and Urea Nitrogen decreased from 56 to 52. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Intubation
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT in Patient A would markedly improve renal clearance, lowering creatinine and urea, and can raise bicarbonate via dialysate; however, the observed creatinine decline and bicarbonate rise are more pronounced and gradual, matching the typical CRRT effect, while intubation alone does not alter these labs significantly.
- CRRT: rapid reduction in creatinine and urea, gradual increase in bicarbonate, modest hemoglobin changes due to fluid shifts
- Intubation: minimal direct impact on renal labs; may transiently affect lactate if hypoxia occurs

**PubMed:** PMID 42130369 (High Bicarbonate Dialysis With or Without Extracorporeal Car); PMID 41615333 (Continuous Renal Replacement Therapy During Liver Transplant)

---

## qc_00070  ·  subject None / hadm c001549

**Question:** Two patients underwent different procedures: Patient A received continuous renal replacement therapy (CRRT) and Patient B received non‑invasive ventilation. The following post‑procedure laboratory trajectory was observed: Bicarbonate 27.0→28.0→30.0→29.0→29.0→29.0, Creatinine 0.9→0.9→1.0→1.3→1.5→1.5, Lactate 1.3→1.5→1.3→1.2→1.3, Platelet Count 186.0→221.0→272.0, Potassium 4.1→4.4→4.0→4.2→4.2→4.2, Sodium 139.0→135.0→134.0→135.0→136.0→134.0, Urea Nitrogen 11.0→11.0→15.0→22.0→31.0→38.0. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Non-invasive Ventilation
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** CRRT removes nitrogenous waste, causing a progressive rise in serum creatinine and urea nitrogen, while non‑invasive ventilation has no such effect on renal clearance.
- CRRT: increases serum creatinine and urea nitrogen due to extracorporeal clearance and fluid shifts
- Non‑invasive ventilation: minimal impact on renal labs; creatinine and urea nitrogen remain stable

**PubMed:** PMID 41844479 (Trajectory pattern of serum urea nitrogen to creatinine rati)

---

## qc_00071  ·  subject None / hadm c000233

**Question:** Patient A underwent extubation and Patient B underwent continuous renal replacement therapy (CRRT). After the procedure, the following laboratory values were observed: Bicarbonate 28.0, Creatinine 2.4, Hemoglobin 6.5, Lactate 1.4, Platelet Count 19.0, Potassium 3.8, Sodium 133.0, Urea Nitrogen 30.0. Which patient’s procedure produced this post‑procedure laboratory profile?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT removes creatinine and urea, raising bicarbonate and lowering lactate, while extubation has no such renal clearance effect; the observed rise in bicarbonate, fall in lactate, and drop in creatinine are characteristic of CRRT.
- CRRT: increases serum bicarbonate, decreases creatinine and urea, lowers lactate, and can lower potassium
- Extubation: minimal impact on renal labs; no significant change in bicarbonate, creatinine, or lactate

**PubMed:** PMID 41201895 (A Conservative Dialysis Strategy and Kidney Function Recover); PMID 41765054 (A novel serum phosphorus to chloride and bicarbonate ratio p); PMID 41615333 (Continuous Renal Replacement Therapy During Liver Transplant)

---

## qc_00072  ·  subject None / hadm c000887

**Question:** Two patients underwent different procedures: Patient A was extubated after invasive ventilation, and Patient B received continuous renal replacement therapy (CRRT). The following post‑procedure laboratory trajectory was observed: Bicarbonate 15.0→18.0→18.0→16.0→17.0→17.0→17.0→16.0, Creatinine 1.5→1.4→1.3→1.2→1.2→1.2→1.3→2.0, Lactate 1.6→1.3→1.3, Platelet Count 305.0→303.0→303.0→357.0, Potassium 4.0→4.1→4.0→4.3→4.3→4.3→4.3→5.0, Sodium 139.0→136.0→135.0→138.0→137.0→137.0→136.0→133.0, Urea Nitrogen 8.0→7.0→6.0→6.0→5.0→6.0→7.0→11.0. Which patient’s procedure produced this laboratory pattern?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT removes creatinine, urea, and potassium while adding bicarbonate, explaining the rise in bicarbonate, fall in creatinine and urea, and gradual potassium increase; extubation alone would not produce these shifts.
- Extubation: minimal impact on bicarbonate, creatinine, potassium, or urea; labs remain largely unchanged
- CRRT: increases bicarbonate, decreases creatinine and urea, and removes potassium, leading to the observed lab trajectory

**PubMed:** PMID 41877111 (Clearance of small and middle molecules during continuous re); PMID 39601911 (Chloride removal and bicarbonate replacement by isotonic sod); PMID 41878413 (Outcomes of Extracorporeal Removal in Acute Barium Poisoning)

---

## qc_00073  ·  subject None / hadm c000716

**Question:** Patient A underwent extubation and Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory trajectory was observed: Bicarbonate decreased from 25.0 to 20.0 mmol/L, Creatinine rose from 1.1 to 2.3 mg/dL, Hemoglobin remained at 7.9 g/dL, Lactate fluctuated around 1.0–1.6 mmol/L, Platelet count increased from 241 to 360 ×10^9/L, Potassium rose from 3.7 to 5.0 mmol/L, Sodium stayed near 138 mmol/L, and Urea Nitrogen increased from 22 to 23 mg/dL. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT removes bicarbonate and potassium, causing their decline and rise respectively, and clears urea and creatinine; the observed rise in creatinine and potassium and decline in bicarbonate are characteristic of CRRT, whereas extubation would not produce these electrolyte shifts.
- Extubation: minimal impact on bicarbonate, potassium, creatinine, or platelet count
- CRRT: decreases bicarbonate, increases potassium, and clears urea and creatinine, often raising platelet count due to filter interaction

**PubMed:** PMID 42130369 (High Bicarbonate Dialysis With or Without Extracorporeal Car); PMID 41090683 (Impact of enteral nutrition guidance on immune function in C); PMID 39308137 (Sterile water and regional citrate anticoagulation: A simple)

---

## qc_00074  ·  subject None / hadm c000938

**Question:** Two patients underwent different procedures: Patient A received continuous renal replacement therapy (CRRT) and Patient B was intubated for airway management. After the procedures, the following laboratory values were recorded (in the order shown): Bicarbonate: 26.0→24.0→25.0→23.0, Creatinine: 2.0→2.0→2.4→2.7, Lactate: 0.9, Platelet Count: 287.0→312.0→303.0, Potassium: 4.4→4.2→4.0→3.7, Sodium: 143.0→146.0→146.0→145.0, Urea Nitrogen: 62.0→60.0→67.0→85.0. Which patient’s procedure produced this post‑procedure laboratory profile?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Intubation
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT removes solutes and fluid, leading to a gradual rise in creatinine and urea nitrogen as the patient’s renal function improves, whereas intubation and mechanical ventilation can precipitate acute kidney injury, causing a progressive increase in creatinine and urea nitrogen over time. The observed rise in creatinine and urea nitrogen is therefore consistent with the intubation‑associated AKI seen in Patient B, not the dialysis‑related clearance seen in Patient A.
- CRRT: Gradual decrease in serum creatinine and urea nitrogen as solutes are cleared, with modest shifts in electrolytes
- Intubation (mechanical ventilation): Potential for acute kidney injury, causing progressive increases in serum creatinine and urea nitrogen due to hypoxia and hemodynamic instability

**PubMed:** PMID 41261569 (Comparative evaluation of continuous renal replacement thera); PMID 42355915 (Hemodynamic and Vascular Stressor Exposure and Outcomes Amon)

---

## qc_00075  ·  subject None / hadm c001698

**Question:** Two patients underwent different procedures: Patient A received continuous renal replacement therapy (CRRT) and Patient B received non‑invasive ventilation. After the procedure, the following laboratory values were recorded (in the order shown): Bicarbonate: 24.0→22.0→23.0→22.0→19.0→22.0, Creatinine: 2.4→2.4→2.2→2.7→3.8→4.0, Platelet Count: 165.0→162.0→153.0→161.0→170.0, Potassium: 5.0→5.0→4.9→4.9→4.9→4.4→4.6, Sodium: 133.0→131.0→131.0→133.0→135.0→119.0→130.0, Urea Nitrogen: 16.0→16.0→14.0→18.0→27.0→28.0. Which patient’s procedure produced this post‑procedure laboratory profile?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Non-invasive Ventilation
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** CRRT removes solutes and fluid, leading to a transient rise in creatinine and urea nitrogen as the filter clears accumulated waste, while it also corrects acidosis, raising bicarbonate; non‑invasive ventilation does not produce the observed creatinine surge or the pattern of bicarbonate changes seen here.
- Continuous renal replacement therapy (CRRT): Increases serum creatinine and urea nitrogen transiently due to filter clearance, raises bicarbonate by correcting acidosis, and modestly lowers potassium.
- Non‑invasive ventilation: Can lower bicarbonate by causing hypercapnia, but does not markedly raise creatinine or urea nitrogen.

**PubMed:** PMID 41050122 (Optimizing a Dose Prescription as the First Step of Green Co); PMID 22812253 (Continuous blood purification therapy on 16 patients with di)

---

## qc_00076  ·  subject None / hadm c000733

**Question:** Patient A underwent extubation and Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory trajectory was observed: Bicarbonate rose from 29.0 to 36.0 mmol/L, Creatinine fell from 1.7 to 1.3 mg/dL, Hemoglobin remained 10.5 g/dL, Lactate fluctuated between 1.2 and 1.9 mmol/L, Platelet count varied around 90×10^9/L, Potassium stayed near 3.5–4.2 mmol/L, Sodium increased from 144 to 152 mmol/L, and Urea Nitrogen climbed from 40 to 60 mg/dL. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** Extubation improves ventilation, reducing lactate and increasing bicarbonate, while CRRT would lower urea nitrogen; the observed rise in urea and bicarbonate aligns with extubation rather than dialysis.
- Extubation: Improved ventilation lowers lactate and raises bicarbonate, with modest creatinine decline and urea rise due to fluid shifts.
- CRRT: Continuous dialysis removes urea and creatinine, lowering both, and typically does not raise bicarbonate or urea nitrogen.

**PubMed:** PMID 20217045 (Effectiveness of acetazolamide for reversal of metabolic alk); PMID 41347379 (Effect of extracorporeal anticoagulation with nafamostat mes)

---

## qc_00077  ·  subject None / hadm c000663

**Question:** Patient A underwent extubation after prolonged invasive ventilation, while Patient B received continuous renal replacement therapy (CRRT). The following laboratory values were observed after the procedure: Bicarbonate 27.0 mmol/L, Creatinine 1.0 mg/dL, Lactate 3.1 mmol/L, Platelet Count 103 ×10⁹/L, Potassium 4.1 mmol/L, Sodium 137 mmol/L, Urea Nitrogen 24 mg/dL. Which patient’s procedure produced this post‑procedure laboratory profile?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** Extubation improves ventilation, reducing lactic acidosis and raising bicarbonate, while CRRT would lower creatinine and potassium but not markedly affect lactate or bicarbonate; the observed rise in bicarbonate and fall in lactate align with extubation effects.
- Extubation: Improved ventilation decreases lactate and increases bicarbonate; minimal impact on creatinine or potassium.
- CRRT: Removal of solutes lowers creatinine, potassium, and urea nitrogen; lactate and bicarbonate remain largely unchanged.

**PubMed:** PMID 36694734 (Effects of continuous renal replacement therapy on Apache-II); PMID 42116820 (Use of near-infrared spectroscopy to guide care in the cardi)

---

## qc_00078  ·  subject None / hadm c000040

**Question:** Two patients underwent different procedures: one was extubated, the other received continuous renal replacement therapy (CRRT). Their pre‑procedure labs and post‑procedure lab trajectories are shown below. Which patient’s procedure produced the observed post‑procedure lab pattern?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** Extubation removes the metabolic burden of mechanical ventilation, leading to a rapid rise in bicarbonate and a modest drop in lactate, while CRRT primarily clears solutes and does not acutely raise bicarbonate; the observed bicarbonate surge and lactate decrease are therefore consistent with extubation rather than CRRT.
- Extubation: Increases serum bicarbonate and reduces lactate due to improved ventilation and reduced metabolic acidosis
- CRRT: Reduces creatinine and urea nitrogen but has minimal immediate impact on bicarbonate or lactate

**PubMed:** PMID 41689327 (Comparison of Classical Blood Cardioplegia and Modified Del ); PMID 41462317 (Efficacy and organ protective effects of continuous renal re)

---

## qc_00079  ·  subject None / hadm c000384

**Question:** Two patients underwent different procedures: Patient A was extubated after prolonged mechanical ventilation, while Patient B received continuous renal replacement therapy (CRRT) for acute kidney injury. The following laboratory values were recorded after the procedures: Bicarbonate 18.0, Creatinine 2.5, Hemoglobin 8.7, Lactate 0.6, Platelet Count 136, Potassium 4.4, Sodium 135, Urea Nitrogen 68. Which patient’s procedure produced this post‑procedure laboratory profile?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** Extubation removes the metabolic burden of ventilation and improves ventilation‑perfusion, leading to a rise in bicarbonate and a fall in lactate, while CRRT typically lowers creatinine and urea nitrogen but does not markedly correct metabolic acidosis; the observed rise in bicarbonate and drop in lactate are therefore consistent with extubation rather than CRRT.
- Extubation: Increases bicarbonate and decreases lactate by restoring normal ventilation and reducing metabolic acidosis.
- CRRT: Reduces creatinine and urea nitrogen but has minimal effect on bicarbonate and lactate, often leaving metabolic acidosis unchanged.

**PubMed:** PMID 36694734 (Effects of continuous renal replacement therapy on Apache-II); PMID 41909343 (Where Is the Lactate Coming From? An Unusual Presentation of)

---

## qc_00080  ·  subject None / hadm c001674

**Question:** Patient A underwent continuous renal replacement therapy (CRRT) and Patient B received non‑invasive ventilation. The following post‑procedure laboratory trajectory was observed: Bicarbonate rose from 22.0 to 27.0 mmol/L, Creatinine fell from 1.0 to 0.9 mg/dL, Hemoglobin fluctuated around 8.6–9.3 g/dL, Lactate varied between 0.6 and 1.6 mmol/L, Platelet count increased from 71 to 131 ×10⁹/L, Potassium decreased from 4.5 to 3.5 mmol/L, Sodium rose from 134 to 141 mmol/L, and Urea nitrogen decreased from 23 to 21 mg/dL. Which patient’s procedure produced this laboratory pattern?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Non-invasive Ventilation
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT removes excess solutes and corrects acidosis, raising bicarbonate, lowering creatinine, potassium, and urea, while non‑invasive ventilation has no such metabolic effect; the observed lab shifts match CRRT’s expected profile.
- Continuous renal replacement therapy: increases serum bicarbonate, decreases creatinine, potassium, and urea nitrogen, and can modestly raise sodium.
- Non‑invasive ventilation: minimal impact on serum bicarbonate, creatinine, potassium, or urea nitrogen.

**PubMed:** PMID 42130369 (High Bicarbonate Dialysis With or Without Extracorporeal Car); PMID 41090683 (Impact of enteral nutrition guidance on immune function in C)

---

## qc_00081  ·  subject None / hadm c001660

**Question:** Two patients underwent different procedures: Patient A received continuous renal replacement therapy (CRRT) and Patient B received non‑invasive ventilation. The following post‑procedure laboratory values were recorded for one of the patients: Bicarbonate rose from 21.0 to 28.0, Creatinine fell from 3.3 to 1.0, Potassium decreased from 5.2 to 4.0, and Urea Nitrogen dropped from 48.0 to 13.0. Which patient’s procedure produced this laboratory trajectory?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Non-invasive Ventilation
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** CRRT removes urea, creatinine, and potassium while replacing bicarbonate, matching the observed trend; non‑invasive ventilation has no such metabolic effect.
- CRRT: rapid decline in creatinine, urea, potassium and rise in serum bicarbonate
- Non‑invasive ventilation: minimal impact on renal clearance or acid–base status

**PubMed:** PMID 41877111 (Clearance of small and middle molecules during continuous re); PMID 39601911 (Chloride removal and bicarbonate replacement by isotonic sod)

---

## qc_00082  ·  subject None / hadm c000125

**Question:** Patient A underwent extubation and Patient B underwent continuous renal replacement therapy (CRRT). Both patients had the following pre‑procedure labs: bicarbonate 21.0 mmol/L (A) vs 23.0 mmol/L (B); creatinine 1.9 mg/dL (A) vs 2.7 mg/dL (B); hemoglobin 13.2 g/dL (A) vs 10.3 g/dL (B); lactate 4.1 mmol/L (A) vs 2.5 mmol/L (B); platelet count 96 ×10⁹/L (A) vs 293 ×10⁹/L (B); potassium 4.3 mmol/L (A) vs 4.2 mmol/L (B); sodium 133 mmol/L (A) vs 130 mmol/L (B); urea nitrogen 42 mg/dL (A) vs 57 mg/dL (B). After the procedure, the following post‑procedure labs were observed: bicarbonate fluctuated around 20–23 mmol/L, creatinine decreased to 1.4–2.2 mg/dL, hemoglobin 8.1 g/dL, lactate 1.4–2.8 mmol/L, platelet count 278–353 ×10⁹/L, potassium 3.7–5.3 mmol/L, sodium 125–135 mmol/L, urea nitrogen 13–42 mg/dL. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT removes creatinine, urea, and excess lactate while correcting acidosis, explaining the observed decreases in creatinine, urea nitrogen, and lactate and the rise in bicarbonate; extubation alone would not produce such marked renal clearance.
- Extubation: minimal impact on renal clearance; may transiently improve lactate due to reduced ventilation but does not lower creatinine or urea.
- CRRT: continuous removal of creatinine, urea nitrogen, and lactate, with correction of metabolic acidosis, leading to lower creatinine, urea, lactate and higher bicarbonate.

**PubMed:** PMID 41261569 (Comparative evaluation of continuous renal replacement thera); PMID 41877111 (Clearance of small and middle molecules during continuous re); PMID 40092107 (Effects of regional citrate anticoagulation on clinical outc)

---

## qc_00083  ·  subject None / hadm c000367

**Question:** Patient A underwent extubation and Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory trend was observed: bicarbonate rose from 20.0 to 26.0 mmol/L, creatinine increased from 1.0 to 1.6 mg/dL, hemoglobin was 10.4 g/dL, lactate fluctuated between 0.8 and 2.7 mmol/L, platelet count fell from 112 to 67 ×10^9/L, potassium rose from 3.1 to 5.4 mmol/L, sodium remained around 138–141 mmol/L, and urea nitrogen increased from 9.0 to 12.0 mg/dL. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT provides bicarbonate‑rich dialysate, raising serum bicarbonate, removes creatinine and urea, and can cause transient hyperkalemia and platelet activation, matching the observed trend; extubation alone would not produce these metabolic shifts.
- Extubation: minimal change in bicarbonate, creatinine, potassium, or platelet count
- CRRT: increases bicarbonate, clears creatinine/urea, transiently raises potassium, and can lower platelets

**PubMed:** PMID 42130369 (High Bicarbonate Dialysis With or Without Extracorporeal Car); PMID 42178010 (Metformin-associated lactic acidosis: Bridging pharmacokinet); PMID 41878413 (Outcomes of Extracorporeal Removal in Acute Barium Poisoning)

---

## qc_00084  ·  subject None / hadm c001621

**Question:** Patient A underwent continuous renal replacement therapy (CRRT) while Patient B received non‑invasive ventilation. The following laboratory values were recorded after the procedures: Bicarbonate rose from 26.0 to 28.0, then fell to 26.0, then spiked to 31.0 and returned to 28.0; Creatinine increased from 1.1 to 1.3, peaked at 1.5, then fell to 1.0 and 0.9; Lactate decreased from 2.5 to 1.6, then to 1.5, then rose to 1.6 and fell to 1.0; Platelet count rose from 197 to 268; Potassium fluctuated from 3.5 to 4.2; Sodium rose from 133 to 140; Urea nitrogen fell from 23.0 to 15.0. Which patient’s procedure produced this post‑procedure laboratory pattern?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Non-invasive Ventilation
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** The observed decline in creatinine, urea nitrogen, and potassium, along with the transient rise in bicarbonate, is characteristic of CRRT’s solute clearance and fluid removal, whereas non‑invasive ventilation does not alter these parameters; thus the pattern matches Patient B’s CRRT.
- CRRT: Rapid removal of creatinine, urea, and potassium; correction of metabolic acidosis with bicarbonate replacement; transient shifts in electrolytes and lactate.
- Non‑invasive ventilation: No significant effect on renal solute clearance or serum bicarbonate, potassium, or urea levels.

**PubMed:** PMID 41877111 (Clearance of small and middle molecules during continuous re); PMID 39601911 (Chloride removal and bicarbonate replacement by isotonic sod); PMID 41878413 (Outcomes of Extracorporeal Removal in Acute Barium Poisoning)

---

## qc_00085  ·  subject None / hadm c001059

**Question:** Patient A underwent continuous renal replacement therapy (CRRT) and Patient B underwent intubation. The following post‑procedure laboratory values are observed: Bicarbonate decreased from 26.0 to 20.0 to 19.0, Creatinine remained 0.9, Lactate dropped to 1.0, Platelet Count rose from 71.0 to 109.0 to 118.0 to 190.0, Potassium fluctuated from 4.4 to 3.2 to 3.5 to 3.3, Sodium increased from 137.0 to 140.0, and Urea Nitrogen rose from 15.0 to 20.0 to 18.0 to 19.0. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Intubation
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT typically causes metabolic acidosis (bicarbonate fall) and platelet consumption (drop), whereas intubation improves oxygenation and can lower lactate; the observed rise in platelets and lactate reduction are consistent with intubation and inconsistent with CRRT.
- CRRT: causes metabolic acidosis (↓bicarbonate) and platelet consumption (↓platelets)
- Intubation: improves oxygen delivery, often reducing lactate and may lead to platelet increases due to transfusion or hemodynamic stabilization

**PubMed:** PMID 42088147 (Regional citrate anticoagulation for renal replacement thera); PMID 39134011 (Coagulation Risk Predicting in Anticoagulant-Free Continuous)

---

## qc_00086  ·  subject None / hadm c001371

**Question:** Two patients underwent different procedures: Patient A received continuous renal replacement therapy (CRRT) and Patient B was intubated. The following post‑procedure laboratory trajectory was observed: Bicarbonate decreased from 21.0 to 15.0 then rose to 21.0; Creatinine fell from 1.8 to 1.4; Hemoglobin fluctuated around 10–11; Lactate rose from 0.8 to 2.3 then returned to 1.2; Platelet count dropped to 89; Potassium decreased from 4.6 to 3.7; Sodium increased from 130 to 134; Urea nitrogen fell from 32 to 11. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Intubation
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** CRRT efficiently removes creatinine, urea, potassium and corrects metabolic acidosis, producing the observed decreases in creatinine, urea nitrogen, potassium and bicarbonate, whereas intubation alone does not markedly lower these solutes.
- CRRT: rapid decline in creatinine, urea nitrogen, potassium and correction of acidosis (↑bicarbonate)

**PubMed:** PMID 42130369 (High Bicarbonate Dialysis With or Without Extracorporeal Car); PMID 41090683 (Impact of enteral nutrition guidance on immune function in C)

---

## qc_00087  ·  subject None / hadm c000869

**Question:** Patient A underwent extubation and Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory values were observed: Bicarbonate 22.0→22.0→25.0→27.0→23.0→25.0, Creatinine 4.2→4.0→4.0→3.8→4.0→3.7, Lactate 0.8→0.8, Platelet Count 170.0→179.0→189.0, Potassium 4.1→4.1→3.2→3.0→3.5→4.0, Sodium 145.0→146.0→147.0→141.0→142.0→134.0, Urea Nitrogen 66.0→69.0→70.0→71.0→71.0→70.0. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** The gradual decline in creatinine and urea nitrogen with only modest potassium shifts is typical of a patient recovering from renal failure after extubation, whereas CRRT would produce a more pronounced and rapid reduction in creatinine and urea nitrogen and a sustained potassium decline, which is not seen here.
- Extubation: Minor improvement in renal markers; creatinine and urea nitrogen may slowly fall as patient stabilizes, potassium remains relatively stable.
- CRRT: Rapid clearance of creatinine and urea nitrogen and significant potassium removal, leading to a pronounced drop in these labs.

**PubMed:** PMID 36694734 (Effects of continuous renal replacement therapy on Apache-II)

---

## qc_00088  ·  subject None / hadm c001394

**Question:** Patient A underwent continuous renal replacement therapy (CRRT) while Patient B was intubated. After the procedures, the following laboratory values were recorded: Bicarbonate 20.0→20.0→22.0→24.0→25.0→24.0→25.0→26.0, Creatinine 3.2→3.5→2.0→1.7→1.5→1.4, Hemoglobin 8.3→11.3→10.7, Lactate 1.8→1.8→1.5→1.4→1.4→1.4→1.4→1.7→1.4→1.4→1.6→1.8→2.0, Platelet Count 137.0→125.0→87.0→92.0, Potassium 4.1→3.8→3.7→3.8→3.6→3.5→3.9→3.6→3.6, Sodium 138.0→137.0→136.0→135.0→135.0→134.0→131.0→133.0→133.0, Urea Nitrogen 54.0→56.0→25.0→22.0→19.0→17.0. Which patient’s procedure produced this post‑procedure laboratory profile?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Intubation
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** The gradual rise in bicarbonate and fall in creatinine and urea nitrogen are classic CRRT effects, but the observed pattern of lactate decrease and potassium decline aligns with the metabolic correction seen after intubation and improved ventilation, not with the dialysis‑induced changes seen in Patient A.
- CRRT: increases bicarbonate, removes creatinine and urea, lowers potassium, may transiently raise lactate due to hemolysis
- Intubation: improves oxygenation, reduces lactate, modestly lowers potassium, minimal effect on bicarbonate or creatinine

**PubMed:** PMID 41877111 (Clearance of small and middle molecules during continuous re); PMID 39601911 (Chloride removal and bicarbonate replacement by isotonic sod); PMID 42017096 (Early Plasma Exchange for Multiple Organ Failure Following M)

---

## qc_00089  ·  subject None / hadm c000593

**Question:** Patient A underwent extubation and Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory values were observed: Bicarbonate 26.0→25.0→25.0→23.0→24.0→28.0→29.0, Creatinine 2.1→1.8→1.5→1.1→1.0→1.6, Platelet Count 238.0→251.0→241.0, Potassium 3.7→3.8→3.8→4.0→4.8→4.0→3.9, Sodium 131.0→133.0→133.0→135.0→131.0→135.0→137.0, Urea Nitrogen 19.0→15.0→13.0→9.0→7.0→11.0. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT rapidly clears creatinine, urea nitrogen, and potassium, producing the observed declines, whereas extubation has no such effect on these labs.
- Extubation: minimal impact on renal clearance markers (creatinine, urea nitrogen) or electrolytes
- CRRT: decreases creatinine, urea nitrogen, and potassium while potentially altering bicarbonate

**PubMed:** PMID 24929959 (Continuous renal replacement therapy (CRRT) for rhabdomyolys); PMID 41877111 (Clearance of small and middle molecules during continuous re)

---

## qc_00090  ·  subject None / hadm c000349

**Question:** Two patients underwent different procedures: one was extubated after invasive ventilation, the other received continuous renal replacement therapy (CRRT) for acute kidney injury. Their pre‑procedure laboratory values are shown below. After the procedures, the following laboratory trajectory was observed: Bicarbonate remained 21.0, then 19.0, then 22.0; Creatinine fluctuated 1.4→1.6→1.4; Platelet Count rose 124→132→181→202; Potassium decreased 4.6→4.4→4.2→4.3→3.7; Sodium remained around 131; Urea Nitrogen increased 40→42→47→52→53. Which patient’s procedure produced this post‑procedure laboratory pattern?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** The platelet count rise is typical of CRRT‑induced platelet consumption and subsequent recovery, whereas extubation alone would not produce such a marked platelet increase; the modest bicarbonate fluctuation aligns with CRRT bicarbonate replacement, not with extubation.
- Extubation: minimal change in bicarbonate, creatinine, or platelet count
- CRRT: initial platelet consumption with later rise, bicarbonate replacement causing transient shifts, and creatinine decline with intermittent rebound

**PubMed:** PMID 39134011 (Coagulation Risk Predicting in Anticoagulant-Free Continuous); PMID 41247497 (Comparison of two different bicarbonate replacement fluids d)

---

## qc_00091  ·  subject None / hadm c000226

**Question:** Two patients underwent different procedures: Patient A was extubated after a prolonged mechanical ventilation, while Patient B received continuous renal replacement therapy (CRRT) for acute kidney injury. The following post‑procedure laboratory values were recorded (in the order shown): Bicarbonate 28.0→27.0→27.0→25.0→24.0→22.0→22.0→21.0→23.0→20.0, Creatinine 1.6→1.4→1.5→1.3→1.3→1.4→1.3→1.4→1.3→1.2, Hemoglobin 7.2, Lactate 1.8→1.5→1.3→1.5→1.2→1.1→0.9→1.1→1.0→1.2→1.0→0.8→0.8→1.0→0.8, Platelet Count 68.0→65.0→61.0→59.0→64.0→70.0→79.0→81.0, Potassium 4.3→4.1→4.2→3.9→4.0→4.2→4.1→4.2→4.1→4.3→4.4→4.0, Sodium 139.0→139.0→135.0→138.0→134.0→135.0→139.0→137.0→139.0→133.0, Urea Nitrogen 32.0→31.0→30.0→30.0→32.0→31.0→31.0→31.0→28.0→26.0. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT removes creatinine, urea, and excess lactate while correcting acidosis, matching the observed declines in creatinine, urea nitrogen, and lactate and the rise in bicarbonate; extubation alone would not produce these renal and metabolic changes.
- Extubation: Minimal impact on renal clearance or acid–base status; lactate and bicarbonate remain largely unchanged.
- CRRT: Rapid reduction of creatinine, urea nitrogen, and lactate with concurrent correction of metabolic acidosis (increase in bicarbonate).

**PubMed:** PMID 35242474 (Comparison of the Treatment Efficacy of Continuous Renal Rep); PMID 16750454 (Metformin-associated lactic acidosis treated with continuous)

---

## qc_00092  ·  subject None / hadm c001737

**Question:** Two patients underwent different procedures: Patient A received continuous renal replacement therapy (CRRT) and Patient B received non‑invasive ventilation. After the procedures, the following laboratory values were recorded at three time points: Bicarbonate 30.0→27.0→24.0, Creatinine 3.2→2.4→3.7, Platelet Count 91.0→104.0→91.0, Potassium 5.4→4.4→4.8, Sodium 141.0→140.0→140.0, Urea Nitrogen 67.0→42.0→77.0. Which patient’s procedure produced this post‑procedure laboratory trajectory?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Non-invasive Ventilation
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT in Patient B explains the transient drop in creatinine and urea nitrogen followed by rebound, while non‑invasive ventilation in Patient A would not produce such a pattern.
- Continuous renal replacement therapy (CRRT): Rapid removal of urea nitrogen and creatinine, causing an early decrease followed by rebound if therapy is stopped.
- Non‑invasive ventilation: No significant effect on renal clearance; creatinine and urea nitrogen remain stable or rise with ongoing kidney injury.

**PubMed:** PMID 41261569 (Comparative evaluation of continuous renal replacement thera); PMID 41877111 (Clearance of small and middle molecules during continuous re)

---

## qc_00093  ·  subject None / hadm c000420

**Question:** Patient A underwent extubation and Patient B underwent continuous renal replacement therapy (CRRT). After the procedure, the following laboratory trend was observed: bicarbonate rose from 19.0 to 26.0 mmol/L and then fell to 23.0 mmol/L; creatinine fell from 1.8 to 1.4 mmol/L; lactate decreased from 1.5 to 0.8 mmol/L; platelet count dropped from 149 to 110 ×10⁹/L; potassium decreased from 3.9 to 3.5 mmol/L; sodium remained around 135 mmol/L; urea nitrogen fell from 26 to 19 mg/dL. Which patient’s procedure produced this post‑procedure laboratory profile?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT removes bicarbonate‑rich fluid, raising serum bicarbonate, and clears creatinine and urea, explaining their rise and fall; it also removes potassium, accounting for the drop, while extubation alone would not produce these changes.
- Extubation: minimal impact on bicarbonate, creatinine, potassium, or urea levels; primarily improves oxygenation.
- CRRT: increases bicarbonate, decreases creatinine and urea, and removes potassium, leading to the observed lab shifts.

**PubMed:** PMID 42130369 (High Bicarbonate Dialysis With or Without Extracorporeal Car); PMID 41877111 (Clearance of small and middle molecules during continuous re)

---

## qc_00094  ·  subject None / hadm c000621

**Question:** Patient A underwent extubation and Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory trajectory was observed: Bicarbonate rose from 22.0 to 27.0, Creatinine fell from 1.8 to 1.3, Lactate decreased from 2.1 to 1.2, Platelet count increased from 135 to 144, Potassium fluctuated from 4.5 to 3.7, Sodium rose from 138 to 142, and Urea Nitrogen fell from 29 to 25. Which patient’s procedure produced this laboratory pattern?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** Extubation improves oxygenation and reduces metabolic stress, leading to a rapid fall in lactate and modest creatinine decline, while CRRT primarily clears solutes and would not cause the observed lactate decrease or the modest creatinine drop seen here.
- Extubation: Rapid lactate reduction and modest creatinine decline due to improved ventilation and perfusion.
- CRRT: Significant creatinine and urea nitrogen clearance but minimal impact on lactate levels.

**PubMed:** PMID 42365098 (Lactate kinetics during regional citrate anticoagulation in ); PMID 41158371 (Survival prediction model for hypoxemic patients receiving p)

---

## qc_00095  ·  subject None / hadm c000432

**Question:** Two patients underwent different procedures: Patient A had extubation after invasive ventilation, while Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory values were recorded: Bicarbonate 25.0→31.0→31.0, Creatinine 0.9→1.1→1.0, Platelet Count 126.0→150.0→150.0, Potassium 4.6→4.2→4.5→4.3, Sodium 133.0→128.0→133.0→134.0, Urea Nitrogen 10.0→15.0→20.0. Which patient’s procedure produced this laboratory profile?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** Extubation improves ventilation, reducing CO₂ and causing a compensatory rise in bicarbonate, while creatinine remains unchanged; CRRT would lower creatinine and alter electrolytes differently.
- Extubation: Increases bicarbonate due to respiratory alkalosis, minimal change in creatinine
- CRRT: Reduces creatinine and urea nitrogen, may lower bicarbonate depending on dialysate composition

**PubMed:** PMID 20217045 (Effectiveness of acetazolamide for reversal of metabolic alk); PMID 41615333 (Continuous Renal Replacement Therapy During Liver Transplant)

---

## qc_00096  ·  subject None / hadm c000311

**Question:** Patient A underwent extubation and Patient B underwent continuous renal replacement therapy (CRRT). The following post‑procedure laboratory values were recorded: Bicarbonate: 24.0→25.0→27.0→31.0→30.0, Creatinine: 1.8→1.5→1.3→1.1→1.1, Lactate: 2.2→2.2→1.9→2.3→2.5→2.2→1.6→1.8→1.7→1.6→1.6→1.6→1.5→1.3, Platelet Count: 105.0→104.0→113.0→87.0→77.0→78.0, Potassium: 4.6→4.7→4.6→4.4→4.3, Sodium: 136.0→137.0→140.0→138.0→138.0, Urea Nitrogen: 27.0→20.0→15.0→13.0→15.0. Which patient’s procedure produced this post‑state?

**Patient A procedure:** Extubation  ·  **Patient B procedure:** Dialysis - CRRT
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT removes uremic toxins and corrects metabolic acidosis, explaining the rise in bicarbonate and fall in creatinine and urea; extubation alone would not produce these changes.
- Extubation: minimal impact on bicarbonate, creatinine, or lactate; no significant change in renal clearance.
- CRRT: increases serum bicarbonate, decreases creatinine and urea nitrogen, and reduces lactate via solute clearance.

**PubMed:** PMID 37558740 (Kinetics of small and middle molecule clearance during conti); PMID 41090683 (Impact of enteral nutrition guidance on immune function in C)

---

## qc_00097  ·  subject None / hadm c001748

**Question:** Two patients underwent different procedures: Patient A received continuous renal replacement therapy (CRRT) and Patient B received non‑invasive ventilation. After the procedures, the following laboratory values were observed: Bicarbonate 21.0→19.0→20.0→19.0→20.0→21.0, Creatinine 5.3→5.3→5.0→5.2→5.2→5.1, Platelet Count 162.0→136.0→143.0, Potassium 4.3→4.4→4.3→3.8→3.6→3.5, Sodium 145.0→144.0→145.0→144.0→144.0→138.0, Urea Nitrogen 94.0→100.0→105.0→109.0→112.0→113.0. Which patient’s procedure produced this post‑procedure laboratory profile?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Non-invasive Ventilation
**Shown post-state owner (GOLD):** B  ·  **predicted_owner:** None

**Causal justification:** CRRT efficiently removes urea, creatinine, and potassium, producing the gradual declines seen in patient B’s labs; non‑invasive ventilation does not alter these solutes, so the observed changes match the CRRT patient.
- CRRT: Rapid clearance of creatinine, urea nitrogen, and potassium, with modest shifts in bicarbonate and sodium
- Non‑invasive ventilation: No significant effect on renal solutes; labs remain largely unchanged

**PubMed:** PMID 41877111 (Clearance of small and middle molecules during continuous re); PMID 41878413 (Outcomes of Extracorporeal Removal in Acute Barium Poisoning); PMID 42264032 (Model‑Informed Dosing Optimization of Colistin Sulfate in Cr)

---

## qc_00098  ·  subject None / hadm c001119

**Question:** Two patients underwent different procedures: Patient A received continuous renal replacement therapy (CRRT) and Patient B was intubated. After the procedures, the following laboratory values were observed (in order of appearance): Bicarbonate: 25.0→22.0→21.0→20.0→18.0→17.0→20.0, Creatinine: 1.1→0.8→0.8→0.8→1.0→1.0, Hemoglobin: 7.2, Lactate: 0.9→0.7→0.7→0.8→0.6→0.9→0.8→0.9→1.0→0.9, Platelet Count: 127.0→124.0→130.0→152.0→183.0→192.0→189.0→199.0, Potassium: 3.8→5.0→5.3→5.0→4.4→4.4, Sodium: 142.0→139.0→138.0→137.0→136.0→134.0→140.0, Urea Nitrogen: 40.0→30.0→24.0→24.0→24.0→26.0. Which patient’s procedure produced this post‑procedure laboratory profile?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Intubation
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** CRRT removes urea and potassium, lowers bicarbonate, and improves lactate clearance, matching the observed trends; intubation alone would not cause the marked shifts in these electrolytes and acid–base parameters.
- CRRT: dialytic removal of urea and potassium, correction of metabolic acidosis (↓bicarbonate) and lactate reduction
- Intubation: minimal direct effect on serum bicarbonate, potassium, or urea; changes would be due to underlying disease rather than the procedure

**PubMed:** PMID 39601911 (Chloride removal and bicarbonate replacement by isotonic sod); PMID 41877111 (Clearance of small and middle molecules during continuous re)

---

## qc_00099  ·  subject None / hadm c001042

**Question:** Two patients underwent different procedures: one received continuous renal replacement therapy (CRRT) and the other was intubated. Their pre‑procedure laboratory values are shown below. After the procedures, a series of laboratory measurements were taken. Which patient’s procedure produced the observed post‑procedure laboratory trajectory?

**Patient A procedure:** Dialysis - CRRT  ·  **Patient B procedure:** Intubation
**Shown post-state owner (GOLD):** A  ·  **predicted_owner:** None

**Causal justification:** CRRT removes solutes such as creatinine, urea nitrogen, and potassium while correcting acid–base status, producing the gradual declines in creatinine, urea nitrogen, and potassium and the transient drop in bicarbonate seen in the post‑state; intubation alone does not produce these systematic changes.
- CRRT: Rapid reduction of serum creatinine, urea nitrogen, and potassium with a transient decrease in bicarbonate due to dialysate composition
- Intubation: Minimal direct effect on renal solute clearance or acid–base balance; laboratory changes would be driven by underlying disease rather than the procedure

**PubMed:** PMID 41261569 (Comparative evaluation of continuous renal replacement thera); PMID 41137351 (Effect of ICU specialist care quality control team managemen)