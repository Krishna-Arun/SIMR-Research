# Benchmark C — Real Run Runbook

Generate the Benchmark C intervention-attribution question set on a GPU node, then
serve it to answering agents. Design summary: [CLAUDE.md](CLAUDE.md).

> Built + validated on the 100-patient MIMIC-IV **demo**; structured to scale to full
> MIMIC-IV (swap the loader in `context_builder.py`). **Standalone task — no MCP server.**

## 0. Task recap
Two patients (A, B) with **similar baselines** each underwent a **different** procedure.
Show one observed post-procedure lab panel (72h, absolute) from one of them; the agent
identifies **which patient** and justifies via the procedures' causal effects.
Score **0/1** on identification; confidence recorded, not scored.

## 1. Environment (same as A/B)
```bash
cd Version_3
pip install -r requirements.txt
pip install pandas pyarrow            # 'mcp' NOT needed for C
echo 'HF_TOKEN=hf_xxx' > .env
```

## 2. Models (shared — download once)
```bash
cd Version_3/loaded_models
python download_models.py mistral-small-3.1 phi-4-mini gpt-oss-20b
```

## 3. Smoke tests (no GPU / no network)
```bash
cd Version_3/Benchmark_C/Question_Gen
python -m py_compile *.py
python -c "import schema; schema.validate(schema.EXAMPLE); print('schema OK')"
python orchestrator.py --dry-run --n 5
#   -> outputs/questions.jsonl + outputs/answering/*.json, NO models/network
```
Verify: records validate, answering views leak nothing, answer balance ~50/50.

## 4. The real generation run (GPU)
```bash
cd Version_3/Benchmark_C/Question_Gen
python orchestrator.py --n 20         # pilot
python orchestrator.py --n 500        # full
```
Per item: context (pairing + observed panel + answer from data) -> Optimizer authors
stem + causal chain -> Evaluator critique -> refine (<=3, else discard) -> Scorer rubric
-> validate -> append to `outputs/questions.jsonl` + write `outputs/answering/<qid>.json`.

**Outputs**
- `outputs/questions.jsonl` — full record **incl. answer + reasoning**. Keep private.
- `outputs/answering/<question_id>.json` — **strict whitelist**: question_id, question_type,
  patient_A, patient_B, shared_labs, observed_post, stem. This is what you serve.

## 5. Serving to answering agents
No server — feed the answering-view JSON into the agent's prompt. The agent returns
`{chosen_patient: "A"|"B", confidence, causal_justification}`. Score 1 if
`chosen_patient == answer` (from `questions.jsonl`) else 0; add to the A-style rubric.
Confidence is logged and compared with the model's activation probability externally.

## 6. Tuning knobs
- `prompts.MAX_PRESTATE_DISTANCE` (0.75) — **the key difficulty knob**. Lower ⇒ more
  confusable, more causal-reasoning-dependent pairs (but fewer of them). Sweep it.
- `prompts.MIN_SHARED_LABS` (3), `prompts.POST_WINDOW_HOURS` (72).
- `context_builder.MAX_UNITS` (400) — caps the O(n²) pairing search; raise for full MIMIC-IV
  (or precompute an index — see §7).
- `context_builder._EXCLUDE_LABEL_SUBSTR` — which `procedureevents` count as therapeutic
  interventions. **Review the printed pair list**; add any non-therapeutic labels you see.

## 7. Scaling to full MIMIC-IV
Two costs grow: unit construction (per-procedure core labs) and the O(n²) pairing. Precompute
units + their shared-lab z-vectors to parquet once, then block pairing by procedure type or by
an ANN over the z-vectors instead of the full quadratic scan. The record CONTRACT is unchanged.

## 8. Known limitations
- **Demo timestamps** are frequently date-level (00:00:00) → coarse 72h windows.
- With only 100 patients, "similar baseline" pairs are limited; expect ~100 pairs at
  `MAX_PRESTATE_DISTANCE=0.75`. Full MIMIC-IV yields far more and lets you tighten the threshold.
- Pairing uses the **last** pre value and **last** post-72h value per lab; change `_core_labs`
  for a robust summary if desired.
```
