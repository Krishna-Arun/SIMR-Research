# Benchmark A — Question-Generation System

Generates **500 clinical questions + full answer keys** for Benchmark A, each anchored to a real
MIMIC-IV ICU admission, using Anthropic's **Evaluator-Optimizer** pattern with **agentic PubMed**
tool-calling. Outputs feed `../Benchmark_A/` (the agent harness + scorer).

> NOT a clinical tool. All work stays on `$SCRATCH`. Real PHI never leaves the node — only
> de-identified clinical concepts go to PubMed (enforced by `qgen/sanitizer.py`).

## Roles
- **Optimizer** (Mixtral 8x22B) — drafts/refines a question + answer key. `qgen/optimizer.py`
- **Evaluator** (DeepSeek-R1-32B) — critiques on 4 dims, max 3 iterations. `qgen/evaluator.py`
- Both run **locally via vLLM** (real PHI → no external APIs) and call the **PubMed MCP server**
  (`../PubMed-MCP-Server/`) agentically. Model sizes are config-driven (`config/qgen.yaml`).

## Pipeline
```
build cohort index ─► materialize pool slices ─► serve vLLM models ─► run generator
 (qgen/cohort.py)      (qgen/cohort.py)           (jobs/serve_models)  (qgen/run_generate.py)
```

1. **Cohort** — `python -m qgen.cohort` scans MIMIC-IV once: ICU admissions with dense labs AND
   ≥1 microbiology event → `outputs/eligible_index.parquet` (**64,845 admissions**). Then materializes
   lab/micro slices for a seeded pool of `cohort.pool_size` admissions → `outputs/eligible_labs.parquet`,
   `outputs/eligible_micro.parquet`, `outputs/pool.parquet`.
2. **Serve** — `sbatch jobs/serve_models.sbatch` launches two vLLM OpenAI endpoints (ports 8000/8001).
3. **Generate** — `python -m qgen.run_generate --pilot` (20) or `sbatch jobs/run_qgen.sbatch`
   (full 500, checkpoint-resume). Per patient: optimizer drafts → evaluator critiques (≤3) → on accept,
   answer key is finalized (patient values attached, PMIDs re-validated) → appended to
   `outputs/questions.jsonl`.

## Evaluator's 4 acceptance dimensions (hybrid: automatic + model)
1. **answerable_with_labs_micro** — answerable ONLY from this patient's labs/micro (auto: gold set in chart, no vitals/imaging terms).
2. **patient_specific** — grounded in THIS patient's actual abnormal findings, not a textbook question
   (auto: ≥1 gold lab present AND MIMIC-flagged abnormal in this chart).
3. **requires_causal_reasoning** — needs a ≥2-step causal chain, not a single lookup
   (auto: ≥2 `->` links or ≥1 link + ≥2 mechanism markers).
4. **guideline_grounded** — supported by a real PubMed citation (model verifies PMIDs).
A dim passes only if **both** the automatic check and the model agree. Accept when all 4 pass or after 3 rounds.
"abnormal" = MIMIC's own `labevents.flag` (value outside the test's reference range; binary, not directional).

## Output: `outputs/questions.jsonl` (one record/line)
`question_id, pipeline_version, question_text, type (diagnosis|intervention), subject_id, hadm_id,
time_zero(+policy), gold_labs[] (label, patient_value, unit, abnormal_flag, guideline_citation{pmid,claim,verified}),
gold_micro[], reference_answer, causal_chain[], pubmed_citations[], evaluator_scores{4 dims}, n_iterations, provenance`.

## Environment
SIMR conda env: `/scratch/users/karun09/miniforge3/envs/simr` (pandas/pyarrow/openai). **vLLM must be
added there before serving.** Run everything with `PYTHONPATH=$PWD`.

## Tests
- `python tests/test_agentic_stub.py` — end-to-end agentic tool path vs live PubMed + PHI gate (no model needed).
- `python -m qgen.sanitizer` / `python -m qgen.mcp_client` — unit checks.

## Status / open items
- ✅ cohort, context builder, MCP client/tools/sanitizer, vLLM backend, agentic loop, optimizer,
  evaluator, orchestrator, schema/writer/dedupe, answer key — built; tool path + cohort + context
  validated end-to-end.
- ⏳ **Model sizes TBD** — finalize optimizer/evaluator models in `config/qgen.yaml`, install vLLM in
  the simr env, run the 20-question pilot, then the full 500.
