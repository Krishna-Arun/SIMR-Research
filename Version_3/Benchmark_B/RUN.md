# Benchmark B — Real Run Runbook

Generate the Benchmark B lab-trajectory question set on a GPU node, then serve it
to answering agents. See [CLAUDE.md](CLAUDE.md) for the design summary.

> Built + validated on the 100-patient MIMIC-IV **demo**; structured to scale to full
> MIMIC-IV (swap the loader in `context_builder.py`). **Standalone task — no MCP server.**

## 0. Task recap
Given pre-procedure labs/micro (with values) + the procedure, predict each core lab's
72h trend (**Rising/Falling/Stable**) with causal justification. Confidence is recorded,
not scored. Direction score (1 / 0.5 / 0) adds onto Benchmark A's answer rubric.

## 1. Environment (same as A)
```bash
cd Version_3
pip install -r requirements.txt
pip install pandas pyarrow            # 'mcp' NOT needed for B (no supplementals server)
echo 'HF_TOKEN=hf_xxx' > .env
```

## 2. Models (shared with A — download once)
```bash
cd Version_3/loaded_models
python download_models.py mistral-small-3.1 phi-4-mini gpt-oss-20b
```
Optimizer=`mistral-small-3.1` (4-bit), Evaluator=`phi-4-mini`, Scorer=`gpt-oss-20b`.

## 3. Smoke tests (no GPU / no network)
```bash
cd Version_3/Benchmark_B/Question_Gen
python -m py_compile *.py
python -c "import schema; schema.validate(schema.EXAMPLE); print('schema OK')"
python orchestrator.py --dry-run --n 5
#   -> outputs/questions.jsonl + outputs/answering/*.json, NO models/network
```
The dry run synthesizes the authored fields from the data-derived directions and
exercises the full loop (context -> assemble -> validate -> persist -> answering view).

## 4. The real generation run (GPU)
```bash
cd Version_3/Benchmark_B/Question_Gen
python orchestrator.py --n 20         # pilot
python orchestrator.py --n 500        # full
```
Per item: context (targets + ground-truth directions from data) -> Optimizer authors
stem + causal chain -> Evaluator critique -> refine (<=3, else discard) -> Scorer rubric
-> validate -> append to `outputs/questions.jsonl` + write `outputs/answering/<qid>.json`.

**Outputs**
- `outputs/questions.jsonl` — full record **incl. ground_truth** (answer key). Keep private.
- `outputs/answering/<question_id>.json` — **ground_truth stripped**; this is what you
  hand to an answering agent (stem + pre-procedure inputs + target labs + post sample times).

## 5. Serving to answering agents
B is standalone — no server. Feed the answering-view JSON directly into the agent's prompt.
The agent returns, per target lab: `{direction, confidence:{Rising,Falling,Stable}, causal_justification}`.
Score each lab with `questions.jsonl`'s ground-truth direction using the 1/0.5/0 rule
(confidence recorded, not scored); aggregate = mean over labs; add to the A-style answer rubric.

## 6. Tuning knobs
- `prompts.STABLE_BAND_FRAC` (default 0.25) — the Stable band as a fraction of reference-range
  width. Lower => fewer Stable labels. Sweep and inspect the Stable fraction on the real set.
- `prompts.POST_WINDOW_HOURS` (default 72).
- `context_builder.MIN_PRE / MIN_POST / MIN_CORE_LABS` — core-lab strictness.
- `context_builder._EXCLUDE_CATEGORIES / _EXCLUDE_LABEL_SUBSTR` — which `procedureevents`
  count as clinical interventions.

## 7. Scaling to full MIMIC-IV
`context_builder.py` reads demo CSVs directly. For full data, cache a per-hadm lab index +
the procedure list to parquet once (mirror Version_2 `qgen/cohort.py`) and point `MimicDemo`
at the slices. The context CONTRACT and everything downstream stay unchanged.

## 8. Known limitations
- **Demo lab charttimes** are frequently date-level (00:00:00) → coarse 72h splits; full
  MIMIC-IV has real timestamps.
- Some ICU `procedureevents` are administrative; the exclusion list handles the obvious ones
  but review `top procedures` output before a full run.
- Directions are computed on the **last** pre and **last** post-72h values; if you prefer a
  robust summary (median/slope), change `_core_labs` — the rest is unaffected.
```
