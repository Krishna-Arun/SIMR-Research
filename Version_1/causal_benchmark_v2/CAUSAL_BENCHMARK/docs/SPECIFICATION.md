# Causal Intervention-Conditioned Trajectory Prediction Benchmark

## Executive Summary

This benchmark evaluates whether models can predict physiological trajectories conditioned on interventions while correctly accounting for observational confounding. **Critically: we make no claims about counterfactual outcomes.** Instead, we evaluate model predictions against matched observational causal contrasts using a principled evaluation framework that reviewers cannot dismiss as "trajectory forecasting with causal wording."

### Why This Matters

Most medical ML papers with "causal" claims fail review because they:
- Treat observational data as if it contains counterfactual ground truth
- Ignore confounders when claiming to estimate treatment effects
- Memorize spurious correlations (sicker → intervention → worse outcome)

**This benchmark fixes that.** We explicitly state:
1. No true counterfactual labels exist
2. Evaluation is based on matched observational contrasts
3. Causal inference is identifiable only under stratification by severity

---

## 1. Problem Formulation

### 1.1 Observational Data

For each patient episode:
$$X = \{x_{t-w:t}\} \text{ (multivariate time series)}$$

- Labs (Troponin I, BNP, Creatinine, Potassium, etc.)
- Vitals (BP, HR, RR, O₂ sat)
- Demographics (age, gender)
- Diagnoses (ICD codes)
- Pre-trend features (last 48h direction + magnitude)
- Severity embedding (SOFA-like score or learned)

**Intervention:**
$$a \in A = \{\text{PCI, CABG, vasopressors, antibiotics, dialysis, ...\}}$$

**Outcome (never observed as counterfactual):**
$$Y_{t:t+h} = \{y_{t+1}, \ldots, y_{t+h}\}$$

Trajectory distribution: $P(Y|X, a)$

### 1.2 The Core Challenge

**What we observe:**
$$(X, a_{\text{observed}}, Y_{\text{observed}})$$

**What we cannot observe:**
$$(X, a_{\text{counterfactual}}, Y_{\text{counterfactual}})$$

Therefore, we evaluate using **matched pairs with different interventions but similar confounders**.

---

## 2. Episode Extraction (Intervention-Anchored)

### 2.1 Intervention Identification

From EHRSHOT/MIMIC, identify intervention timestamps:

| Category | Examples |
|----------|----------|
| Cardiac | PCI, CABG, pacemaker |
| Respiratory | mechanical ventilation, extubation |
| Renal | dialysis, CRRT, ultrafiltration |
| Infection | antibiotics (classes: beta-lactam, vanc, fluoroquinolone, etc.) |
| Hemodynamic | vasopressors (norepinephrine, epinephrine, vasopressin) |
| None | observation only (baseline) |

**Hierarchical taxonomy prevents trivial memorization.**

### 2.2 Episode Windows

For each intervention $a$ at time $t_0$:

- **Pre-window:** $[-48\text{h}, 0]$ — all clinical context before intervention
- **Post-window:** $[0, +48\text{h}]$ — trajectory after intervention
- **Adaptive resampling:** Align to fixed-length latent timeline (e.g., 96 timepoints)

**Key invariant:** All pre-context must be available at $t_0$; post-window is the prediction target.

### 2.3 Missing Data Handling

- Forward-fill stable measurements (vitals, static demographics)
- Interpolate labs linearly (avoid extrapolation)
- Mark missing indicators as a feature (not imputation)
- Drop episodes with >30% missing post-window data

---

## 3. Confounder Encoding (CRITICAL)

Without confounding features, models learn spurious patterns: "sicker → intervention → worse outcome."

### 3.1 Severity Embedding

**Option A: Clinical score**
$$\text{SOFA} = \text{score}(\text{PaO}_2, \text{bilirubin}, \text{creatinine}, \text{platelets}, \text{MAP}, \text{GCS})$$

Discretize into bins: [0-6], [7-9], [10-15], [15+] (severity strata).

**Option B: Learned embedding**
$$s = \text{MLP}(\text{concat}[\text{labs}_{t \leq 0}, \text{vitals}_{t \leq 0}])$$

Train contrastively with outcome labels to capture confounding.

### 3.2 Comorbidity Vector

Extract from diagnoses (ICD codes):
- Diabetes, hypertension, CKD, CAD, heart failure, COPD, etc.
- One-hot or embedding (e.g., CCS grouping)
- 10-20 dimensions total

### 3.3 Pre-Trend Features

Last 48 hours before intervention:

$$\text{pre\_trend} = (\text{slope}, \text{direction}, \text{volatility})$$

For each lab:
- Slope: $\frac{y_0 - y_{-48}}{48}$
- Direction: sign(slope)
- Volatility: std dev of residuals around trend

**Why:** Models must not overfit to confounders. A patient on vasopressors is sicker by definition — pre-trend captures that. Correct models should treat pre-trend as fixed and focus on intervention effect.

### 3.4 Output: Encoded Features

```json
{
  "episode_id": "patient_123_intervention_pci_2023_05_15",
  "severity_score": 8,
  "severity_bin": "moderate",
  "comorbidities": [1, 0, 1, 0, 1, 0, ...],
  "pre_trend": {
    "troponin_slope": 0.015,
    "troponin_direction": "rising",
    "troponin_volatility": 0.002,
    ...
  }
}
```

---

## 4. Matched Pair Construction

### 4.1 Matching Strategy

**Goal:** Find pairs of episodes with:
1. Same severity bin (e.g., both SOFA 7-9)
2. Similar pre-trend (same direction, ±20% magnitude)
3. Different interventions
4. Different outcomes (to measure causal signal)

**Algorithm:**

For each episode $(X_i, a_i, Y_i)$:

1. Find candidates in same severity bin
2. Compute pre-trend distance: $d = \sum_j |(\text{slope}_j^i - \text{slope}_j^k) / \text{slope}_j^i|$
3. Keep candidates with $d < 0.2$ (or adaptive threshold)
4. Among candidates with different $a_k \neq a_i$, select nearest by:
   - Euclidean distance in comorbidity space
   - Time proximity (prefer same hospital/ICU stay window)
5. Store pair: $(\text{episode}_i, \text{episode}_k, \text{intervention\_pair})$

### 4.2 Covariate Balance Check (QA)

After matching, verify:
$$\text{SMD} = \frac{\bar{X}_i - \bar{X}_k}{\sqrt{(s_i^2 + s_k^2)/2}} < 0.1$$

(Standardized Mean Difference <0.1 indicates good balance)

Check across: severity, comorbidities, pre-trend slope, volatility.

### 4.3 Output: Matched Pairs

```json
{
  "pair_id": "pair_0001",
  "episode_a": "patient_123_intervention_pci_2023_05_15",
  "episode_b": "patient_456_intervention_none_2023_05_10",
  "intervention_a": "PCI",
  "intervention_b": "none",
  "severity_match": {
    "bin": "moderate",
    "episode_a_score": 8,
    "episode_b_score": 9,
    "smd": 0.08
  },
  "y_a": [0.05, 0.04, 0.03, ...],
  "y_b": [0.06, 0.05, 0.04, ...]
}
```

---

## 5. Task Definition (Three Independent Subtasks)

### Task A: Trajectory Prediction (Factual)

**Input:** $(X, a)$ — history + intervention

**Output:** $\hat{Y}_{a}$ — predicted trajectory (mean + uncertainty)

**Evaluation:** MSE, MAE, CRPS against observed $Y$

**Purpose:** Test whether models can forecast physiological dynamics. Baseline task (non-causal).

### Task B: Treatment Effect Direction

**Input:** Matched pair $(X_i, a_1, Y_i)$ vs $(X_k, a_2, Y_k)$ with same $X_{\text{confounders}}$

**Output:** Sign of predicted difference $\text{sign}(\hat{Y}_{a_1}[h] - \hat{Y}_{a_2}[h])$

**Evaluation:** Accuracy of direction (rising, falling, stable)

**Purpose:** Core causal test. Models must predict correct treatment effect ordering.

### Task C: Temporal Causal Dynamics

**Input:** Predicted trajectory with intervention time

**Output:** Time-to-response, inflection point, lag by intervention class

**Evaluation:** Alignment with matched observational lags

**Purpose:** Test whether models learn physiologically plausible response kinetics:
- PCI: response within 2-6 hours
- Antibiotics: delayed response (24-72 hours)
- Vasopressors: immediate (minutes to 1 hour)

---

## 6. Evaluation Metrics (NeurIPS-Grade)

### 6.1 Primary: MCCS (Matched Counterfactual Consistency Score)

For each matched pair:

$$\text{MCCS} = P(\text{sign}(\hat{Y}_{a_1} - \hat{Y}_{a_2}) = \text{sign}(Y_{a_1} - Y_{a_2}))$$

Aggregate: average across all pairs

$$\text{MCCS}_{\text{global}} = \frac{1}{N_{\text{pairs}}} \sum_i \mathbb{1}[\text{correct direction}]$$

**Why:** This is the core causal signal. Reviewers accept it because:
1. No fake counterfactuals
2. Explicit matched design
3. Grounded in observational causal inference theory
4. Cannot be gamed by memorization

**Baseline expectation:** Random = 0.5; good models = 0.65-0.75

### 6.2 Secondary: TCAE (Temporal Causal Alignment Error)

For each intervention class $a$:

$$\text{TCAE}_a = \text{median}(|\hat{t}_{\text{inflection}} - \hat{t}_{\text{matched\_inflection}}|)$$

Where inflection point is detected as:
- Max second derivative (curvature change)
- Or: time to 50% of total trajectory change

Aggregate by intervention class.

**Why:** Causal effects have expected timescales. Correct models respect physiology.

**Baseline expectation:** <6 hours for immediate interventions; <24h for antibiotics

### 6.3 Secondary: IEC (Intervention Effect Calibration)

Wasserstein distance between predicted and matched outcome distributions:

$$\text{IEC} = W_1(P_{\hat{Y}}(y_{\text{final}}|a_1), P_Y(y_{\text{final}}|a_1))$$

Measures whether predicted outcome distributions match empirical distributions.

**Why:** Calibration matters for clinical use.

### 6.4 Test: Pre-Trend Invariance

**Setup:** Shuffle interventions within same severity bin; re-evaluate MCCS.

If model is not confounded: MCCS should drop significantly (chance-level ~0.5)

If model overfits to confounders: MCCS stays high (error!)

$$\Delta\text{MCCS} = \text{MCCS}_{\text{shuffled}} - \text{MCCS}_{\text{real}} \quad \text{(should be negative)}$$

Threshold: $\Delta\text{MCCS} < -0.10$ (MCCS drops by 10+ points)

**Why:** This catches models that learn "sicker patients get sicker" rather than intervention effects.

### 6.5 Auxiliary: Shape Similarity

DTW (Dynamic Time Warping) distance or cosine similarity on learned embeddings.

**Why:** Auxiliary metric. Lower weight (explicitly state this in paper).

---

## 7. Baseline Models

### 7.1 Predictive Baselines

| Model | Type | Key Feature |
|-------|------|-------------|
| LSTM | RNN | Sequential; intervention concatenated to input |
| Transformer | Attention | Multi-head; intervention as token embedding |
| Neural ODE | ODE-based | Latent dynamics; intervention-dependent vector field |
| Temporal Fusion Transformer | Hybrid | Industry standard; variable importance |
| N-BEATS | Univariate | Strong on individual time series |

### 7.2 Causal-Aware Baselines

| Model | Method | Key Feature |
|-------|--------|-------------|
| MSM (Marginal Structural Model) | Propensity weighting | Gold standard; requires correct propensity spec |
| T-Learner | Treatment-specific models | Separate model per intervention arm |
| S-Learner | Single model + CATE | Intervention as feature; extract heterogeneous treatment effects |
| Causal Transformer | Intervention token + causal masking | Attention mask enforces acyclicity |

### 7.3 Ablation Baseline

**Same model (e.g., LSTM) without intervention token:**
$$\hat{Y}_{\text{no\_int}} = \text{LSTM}(X \text{ only})$$

Then condition on intervention post-hoc:
$$\hat{Y} = \hat{Y}_{\text{no\_int}} + f(a)$$

**Purpose:** Quantifies how much causal signal comes from intervention encoding.

---

## 8. Training & Evaluation Protocol

### 8.1 Data Split

- **Train:** 60% of pairs (stratified by severity, intervention, outcome direction)
- **Validation:** 20% (hyperparameter tuning)
- **Test:** 20% (final metric reporting)

### 8.2 Hyperparameter Search

For each model:
- Grid search: learning rate, batch size, hidden dim, dropout
- Optimize on validation MCCS
- Report test MCCS with 95% CI

### 8.3 Metric Computation

For each test episode:
1. Generate trajectory prediction $\hat{Y}$
2. Find 5 nearest matched pairs in test set
3. Compute MCCS, TCAE, IEC against matches
4. Aggregate: mean ± std across test set

### 8.4 Statistical Significance

Bootstrap confidence intervals (1000 resamples) for:
- MCCS difference between models
- TCAE by intervention class
- Pre-trend invariance drop

---

## 9. Intervention Taxonomy (Final)

### Hierarchy

```
Cardiac
├── Coronary Revascularization
│   ├── PCI (percutaneous)
│   └── CABG (surgical)
├── Device
│   ├── Pacemaker
│   └── AICD
└── Supportive
    ├── Mechanical support (IABP, ECMO)
    └── Inotropes (dobutamine, milrinone)

Respiratory
├── Mechanical Ventilation
│   ├── Intubation
│   └── Non-invasive (CPAP, BiPAP)
├── Extubation
└── Oxygen Therapy

Renal
├── Dialysis (hemodialysis, peritoneal)
├── CRRT (continuous renal replacement therapy)
└── Diuretics

Infection
├── Antibiotics (classify by class)
│   ├── Beta-lactams
│   ├── Vancomycin
│   ├── Fluoroquinolones
│   └── Other
├── Antivirals
└── Antifungals

Hemodynamic
├── Vasopressors (norepinephrine, epinephrine, phenylephrine, vasopressin)
├── Vasodilators (nitroglycerin, hydralazine)
└── Fluid Management (bolus, restriction)

Other
└── Observation only (baseline)
```

---

## 10. Expected Contribution (Why This is NeurIPS-Worthy)

### 10.1 Novel Evaluation Framework

- **Not** another trajectory predictor
- **Yes:** Principled evaluation of intervention-conditioned predictions under confounding
- Matched causal contrasts as ground truth (not fake counterfactuals)
- MCCS metric is new and defensible

### 10.2 Methodological Rigor

- Explicit statement: "No true counterfactuals"
- Propensity weighting + stratified matching
- Covariate balance validation (SMD checks)
- Pre-trend invariance test (catches confounding overfit)

### 10.3 Practical Value

- Enables downstream: policy learning, offline RL, digital twins
- Extensible: new interventions, new patient populations, new labs
- Reproducible: matched pairs are concrete, not synthetic

### 10.4 Alignment with Trends

- Causal ML + healthcare ← hot topic
- Sequence modeling under confounding ← timely
- Decision-aware forecasting ← emerging
- Foundation models for EHR ← industry interest

---

## 11. Reproducibility & Code Organization

### Directory Structure

```
benchmarks/
├── causal-intervention/
│   ├── SPECIFICATION.md             ← this file
│   ├── data/
│   │   ├── episodes/                ← raw extracted episodes
│   │   ├── matched_pairs/           ← constructed pairs
│   │   └── features/                ← encoded features
│   ├── scripts/
│   │   ├── extract_episodes.py
│   │   ├── encode_features.py
│   │   ├── construct_matched_pairs.py
│   │   └── validate_balance.py
│   ├── models/
│   │   ├── baseline_lstm.py
│   │   ├── baseline_transformer.py
│   │   ├── causal_msm.py
│   │   ├── causal_tlearner.py
│   │   └── ablation_no_intervention.py
│   ├── metrics/
│   │   ├── mccs.py                  ← core metric
│   │   ├── tcae.py
│   │   ├── iec.py
│   │   ├── pre_trend_invariance.py
│   │   └── shape_similarity.py
│   ├── eval/
│   │   ├── benchmark_runner.py      ← main evaluation harness
│   │   └── report_generator.py
│   └── output/
│       ├── results.json
│       ├── comparison_table.md
│       └── figures/
```

### Reproducibility Checklist

- [ ] All random seeds fixed
- [ ] Hyperparameters logged for each run
- [ ] Matched pairs with SMD <0.1 documented
- [ ] Bootstrap CIs reported
- [ ] Code available on GitHub
- [ ] Results CSV downloadable

---

## 12. Future Extensions

1. **Policy Learning:** Use matched pairs as offline RL data
2. **Counterfactual Simulation:** Predict unobserved (a, Y) combinations
3. **Heterogeneous Treatment Effects:** Patient subgroups with different response
4. **Real-Time Guidance:** Deploy top model as clinical decision support
5. **New Patient Populations:** Sepsis, acute respiratory distress, trauma

---

## References (Key Papers)

- Rotnitzky et al. (2000): Marginal Structural Models
- Kennedy (2020): S-Learner / Doubly Robust Treatment Effect Estimation
- Athey & Wager (2019): Generalized Random Forests for Heterogeneous Treatment Effects
- Nie & Wager (2021): Quasi-Oracle Estimation of Heterogeneous Treatment Effects
- Saria & Goldenberg (2015): Modeling Medical Time Series (EHR review)

---

**Last Updated:** 2026-06-23  
**Status:** Draft for review
