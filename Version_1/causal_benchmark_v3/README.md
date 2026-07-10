# causal_benchmark_v3 — Counterfactual Treatment Benefit (CTB)

Tests whether a model can tell if a treatment actually HELPS a specific patient (vs a matched
untreated twin), not just whether a lab number moves. See `docs/BENCHMARK_SPEC.md` (6 sections).

## Layout
- `docs/BENCHMARK_SPEC.md`     — the spec: one-liner, scoring, novelty, prior art, methodology, anti-cheat
- `scripts/score_v3.py`        — CTB scorer: oracles + models; decisive acc, NC false-effect, ECE, validity gate
- `scripts/extract_benefit_outcome.py` + `run_extract.sbatch` — long-horizon resolution outcome (run as a job)
- `oracle/`                    — (reuses v2 rule_based_oracle pattern; physiology = target profile)
- `inspection/extract_golden_v3.py` + `build_viewer_v3.py` — 10 golden samples WITH activation probabilities
- `inspection/golden_viewer_v3.html` — open locally (MIMIC DUA: do NOT upload)
- `outputs/ctb_scores.json`    — measured oracle + model profiles

## Reproduce
    cd scripts && python3 score_v3.py                 # scores (96h demo outcome)
    cd inspection && python3 extract_golden_v3.py && python3 build_viewer_v3.py
    sbatch scripts/run_extract.sbatch                 # then re-score on the benefit outcome

## Key results (measured)
- Lazy "nothing-changes" oracle: decisive accuracy = 0.00  (caught)
- "Treatment-helps-everything" oracle: negative-control false-effect = 0.88  (caught)
- Physiology oracle (real reasoner): decisive 0.59, NC-FP 0.00  (target profile)
- 7B LLMs: decisive 0.34–0.41; DeepSeek NC-FP 0.44 + only 66% well-formed (hidden by aggregate MCCS)
