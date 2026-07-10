# Causal Benchmark v2 — Findings & Design

Built from a golden-sample inspection (10 pairs × 3 models, side by side) plus a
rule-based oracle positive control. The aggregate MCCS (~0.49–0.50 for all models)
hid every one of the problems below.

## How to inspect
- `inspection/golden_viewer.html` — open locally (MIMIC DUA: do **not** upload). Side-by-side
  raw inputs, predictions, ground truth, with flaw flags per pair.
- `oracle/rule_based_oracle.py` — the positive control; prints the ceiling under both metrics.

---

## Headline finding — the v1 label does not test causal reasoning

The rule-based oracle (positive control) on the primary contrast `pci_vs_control / Troponin T`:

| Oracle | uses intervention? | MCCS (v1 "level") | MCCS (v2 "DiD") |
|---|---|---|---|
| physiology (periprocedural hump vs control resolution) | yes | 0.679 | **0.645** |
| pretrend extrapolation | no | 0.584 | 0.523 |
| **baseline_copy (predict NO change)** | **no** | **0.648** | **0.000** |
| *LLMs (Qwen3-8B, DeepSeek-R1-7B)* | — | *~0.49* | *not yet measured* |

**Under the current "level" metric, an oracle that predicts nothing changes scores 0.648 —
within 0.03 of the physiology oracle, and far above every LLM.** MCCS is mostly measuring
"did you preserve the baseline ordering" (sicker PCI patients start higher and stay higher),
not causal effect. The LLMs score *below* baseline-copy because they hallucinate scale.

**The fix (demonstrated):** score the *difference-in-differences* — compare each arm's change
from its OWN baseline. Under DiD the blind baseline-copy oracle collapses to 0.000 while the
physiology oracle holds 0.645. DiD also makes the negative control meaningful (physiology
correctly finds ~0 differential effect on sodium).

---

## Flaws the side-by-side exposed (with evidence)

1. **Label rewards the wrong reasoning (level metric).** PCI troponin *rises* (periprocedural
   injury: ep_pci_00000 2.29→2.77) while matched controls fall, so the "correct" answer is
   "treated ends higher." A model reasoning "PCI helps → troponin falls" is marked wrong.
   → **Fix:** DiD metric + report direction separately from benefit.

2. **Baseline-ordering confound dominates** (see oracle table). → **Fix:** DiD.

3. **Pairs are not independent.** ep_pci_00000 appears in pair_000001/2/3…; 654 "pairs" ≈ 218
   unique PCI episodes reused ×3. Significance inflated ~3×. → **Fix:** cluster-robust CIs by
   treated episode, or 1:1 matching without reuse; report effective N.

4. **Negative control is trivially gamed (level metric).** Every model echoes the sodium
   baseline and predicts "stable", so sodium-MCCS = baseline ordering. → **Fix:** under DiD a
   good model must predict ~0 differential effect on sodium; spurious movement is penalized.

5. **Two contradictory directions recorded.** Parsed-text direction vs logit-confidence
   direction disagree in 68–83% of episodes; ECE and MCCS grade incompatible signals.
   → **Fix:** one canonical signal — derive direction from the predicted trajectory only;
   drop the separate logit probe or reconcile it explicitly.

6. **Broken outputs scored as valid.** DeepSeek frequently emits 0.0 / wrong-scale values
   (troponin 0.0→0.0; 24→96). These enter MCCS as real. → **Fix:** validity gate — outputs
   failing scale/format checks are scored as abstentions and reported as a separate
   "well-formed rate," not silently averaged into causal accuracy.

7. **Credit on assay noise.** "Best match" pairs distinguish 0.01 vs 0.05 troponin (within
   noise) for full credit. → **Fix:** require a minimum effect size (Δ beyond assay CV) for a
   pair to be scorable; ties/sub-threshold → excluded or half-credit.

8. **Raw model text not stored.** Only parsed trajectories survive, so a wrong score can't be
   attributed to model vs parser. The ep_pci_00000 "0.8 start" (baseline 2.29) anomaly is
   unauditable. → **Fix:** v2 inference must persist raw completion text per episode.

9. **Existing leakage in the prompt.** 52% of episodes had HPI sentences narrating the
   procedure/aftermath (discharge-summary source). → **Fixed** in `build_episodes_v2.py`
   (sentence-level scrub; 499 sentences dropped).

10. **Date-only procedure timestamps → ±12h anchor ambiguity** (noon split), on the same
    timescale as the troponin hump. → **Fix (structural, requires re-extraction):** recover
    sub-day procedure timing, or score peak/AUC over a wide window instead of a sharp pre/post
    split.

---

## v2 changes implemented so far
- `scripts/build_episodes_v2.py` — leakage scrub (#9) + comorbidity injection (helpful, safe).
- `oracle/rule_based_oracle.py` — positive control + DiD metric demonstration (#1,2,4).
- `inspection/` — golden extractor + local side-by-side viewer (surfaced #1–8).

## v2 changes still to wire into the runner
- DiD as the primary metric; level kept as a reported secondary.
- Single canonical direction signal (#5).
- Output validity gate + well-formed rate (#6,7).
- Raw-text capture in inference (#8).
- Cluster-robust significance by treated episode (#3).
- Sub-day anchoring re-extraction (#10).
