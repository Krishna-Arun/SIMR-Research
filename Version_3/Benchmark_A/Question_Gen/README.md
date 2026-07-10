# Benchmark A — Question Generation

Three local-model agents generate the benchmark questions in an
evaluator-optimizer loop, then a scorer finalizes each accepted question.

| Agent | Model | Role |
|---|---|---|
| `optimizer_agent.py` | Mistral Small 3.1 (`mistral-small-3.1`) | Draft & refine the question + answer key |
| `evaluator_agent.py` | Phi-4-mini (`phi-4-mini`) | Critique on 4 acceptance dimensions; accept or send back |
| `scorer_agent.py` | GPT-OSS 20B (`gpt-oss-20b`) | Final quality score + grading rubric for accepted questions |

Loop: **optimizer.draft → evaluator.evaluate → (refine on reject, ≤3 rounds; discard if
still failing) → scorer.score**.

- `backend.py` — shared `LocalLLM` wrapper; loads weights from `../../loaded_models/<key>`
  (falls back to the HF hub via `../../.env`).
- `prompts.py` — **single source of truth** for the benchmark spec spliced into every
  agent's system prompt (targets, time-zero, supplemental categories, golden-set rule,
  MC rules, PubMed rule, request-scoring rubric, anti-leakage rules). Edit rules here.
- `schema.py` — the question-record contract + `validate()` (stdlib only). `EXAMPLE`
  is a schema-valid reference record.
- Models are keyed to `../../loaded_models/models.yaml`.

## What Benchmark A tests
An answering agent gets a multiple-choice question about ONE MIMIC-IV patient frozen at
**time-zero**. Patient detail is hidden behind the MCP tools. The agent must (1) discover
what supplementals exist, (2) request the ones it needs **with patient-specific
justification** (not textbook), and (3) answer with a **causal chain**.

### Design (finalized)
- **Scope**: built on the 100-patient MIMIC-IV demo; structured to scale to full MIMIC-IV.
- **Question types & time-zero**: `next_procedure` (ICU intime), `deterioration`
  (24h after admit), `readmission_30d` (dischtime), `mortality_1y` (dischtime).
- **Supplemental categories**: labs, microbiology, medications, vitals_exam, dx_history,
  prior_procedures, fluids_output.
- **Golden supplementals**: minimal must-request set spanning any category; question is
  **unsolvable** without the full set, solvable with it.
- **Multiple-choice**: multi-select, no buzzwords, always ends with **"None of the above"**;
  Optimizer generates the distractors.
- **PubMed grounding**: required for `next_procedure` & `mortality_1y`; optional otherwise.
- **Request scoring** (encoded by the Scorer into each answer key): each request =
  justification quality (`0` irrelevant/inaccurate, `0.5` generic/textbook,
  `1` patient-specific + multi-item reasoning) **plus +1 for each requested item in the
  golden set**. A golden item can thus score up to `2.0`; a non-golden request at most `1.0`.
- **Loop**: max 3 optimizer↔evaluator rounds.

## Tools available to the agents
- **PubMed MCP server** (`../PubMed-MCP-Server/`) — ✅ **connected**. Built
  (`npm install && npm run build` done) and reachable from Python via
  `mcp_client.py`. Exposes 16 tools (`search_articles`, `advanced_search`,
  `search_by_mesh_terms`, `get_abstract`, `get_article_details`, `validate_pmid`, …).
  The Optimizer uses it to ground `next_procedure`/`mortality_1y` citations.
  - `mcp_client.py` — stdio JSON-RPC client; `pubmed_client()` spawns + handshakes
    the server. Smoke test: `python mcp_client.py` (needs network to NCBI; set
    `NCBI_API_KEY`/`NCBI_EMAIL` to raise rate limits).
- Custom supplementals MCP server: `../MCP_Server/server.py`
  (`Access_All_supplementals_no_values`, `Request_a_supplemental` — currently stubs).

## Modules
| File | Role |
|---|---|
| `prompts.py` | Shared spec (single source of truth) spliced into every agent prompt. |
| `schema.py` | Question-record contract + `validate()`. |
| `backend.py` | `LocalLLM` HF wrapper (loads from `../../loaded_models/`). |
| `optimizer/evaluator/scorer_agent.py` | The three generation agents. |
| `context_builder.py` | MIMIC (demo) → context: time-zero, before/after split, labels, eligibility. |
| `mcp_client.py` | stdio MCP client; `pubmed_client()` factory. |
| `tools.py` | PubMed tool catalog + dispatcher + PHI/identifier query guard. |
| `agentic_loop.py` | ReAct tool-calling driver for the local models. |
| `orchestrator.py` | The full loop: context → draft → evaluate (≤3) → score → validate → persist + bundle. |

## Status — pipeline complete end to end
All stages are built and wired. The **PubMed MCP server is connected + verified live**;
the **supplemental MCP server serves real pre-t0 values** from bundles the orchestrator
writes. Generation runs on a GPU node (Mistral/Phi/GPT-OSS). See `../RUN.md` for the
full runbook.

## Verify (no GPU / no network)
```bash
python -m py_compile *.py
python -c "import schema; schema.validate(schema.EXAMPLE); print('schema OK')"
python orchestrator.py --dry-run --n 5 --types next_procedure mortality_1y
#   -> outputs/questions.jsonl + MCP_Server/supplementals/*.json, no models/network
```
The dry run synthesizes schema-valid records straight from real contexts, so it
exercises the whole loop (context → validate → persist → bundle) without models.
Real generation is deferred to the GPU node (weights in `../../loaded_models/`).
