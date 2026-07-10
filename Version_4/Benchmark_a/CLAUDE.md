# CLAUDE.md — Benchmark A (Version 3)

Context for Claude Code / any agent working this benchmark on the compute cluster.
For the step-by-step operational procedure, see **[RUN.md](RUN.md)**.

## What Benchmark A tests
An answering agent is given a **multiple-choice** clinical question about ONE real
MIMIC-IV patient, frozen at **time-zero**. The patient's raw data is hidden behind
two MCP tools. To score well the agent must: (1) discover what supplemental data
exists, (2) **request** the items it needs **with patient-specific justification**
(and skip irrelevant ones), and (3) answer with an explicit **causal chain**.
It tests evidence-seeking causal reasoning, not recall.

## Pipeline (all built + verified; models run on GPU)
```
MIMIC-IV demo ─► context_builder ─► Optimizer(Mistral) ─► Evaluator(Phi) ─► Scorer(GPT-OSS) ─► questions.jsonl
                                         ▲                     │                                  + supplemental bundles
                                         └──── refine ◄────────┘ (≤3 rounds, else discard)
                                     (PubMed citation via agentic_loop for procedure/mortality)
```
Orchestrated by `Question_Gen/orchestrator.py`. Answering agents are later served
by `MCP_Server/server.py`.

## Module map (`Question_Gen/`)
| File | Role |
|---|---|
| `prompts.py` | **Single source of truth** for the benchmark spec, spliced into every agent prompt. Edit rules here. |
| `schema.py` | Question-record contract + `validate()`. |
| `backend.py` | `LocalLLM` HF wrapper; loads weights from `../../loaded_models/<key>`. |
| `optimizer_agent.py` / `evaluator_agent.py` / `scorer_agent.py` | The three generation agents (accept an injected `llm`). |
| `context_builder.py` | MIMIC(demo) → context: time-zero, before/after split, label derivation, eligibility. |
| `mcp_client.py` | stdio MCP client; `pubmed_client()` factory. |
| `tools.py` | PubMed tool catalog + dispatcher + PHI/identifier query guard. |
| `agentic_loop.py` | ReAct tool-calling driver for the local models. |
| `orchestrator.py` | The full loop + offline `--dry-run`. |
| `MCP_Server/server.py` | Serves gated pre-t0 supplementals to answering agents. |
| `PubMed-MCP-Server/` | Node MCP server (built); grounds citations. |

## Design decisions (locked)
- **Scope**: built on the 100-patient MIMIC-IV demo; structured to scale to full MIMIC-IV (see RUN.md §7).
- **Question types & time-zero**: `next_procedure` (ICU intime), `deterioration` (admit+24h),
  `readmission_30d` (dischtime), `mortality_1y` (dischtime).
- **Supplemental categories**: labs, microbiology, medications, vitals_exam, dx_history,
  prior_procedures, fluids_output.
- **Golden supplementals**: minimal must-request set spanning any category; question is
  **unsolvable** without the full set, solvable with it.
- **Multiple-choice**: multi-select, no buzzwords, always ends with **"None of the above"**;
  Optimizer writes the distractors.
- **PubMed grounding**: required for `next_procedure` & `mortality_1y`; optional otherwise.
- **Request scoring** (Scorer writes into each answer key): per request = justification
  quality `0/0.5/1` **plus +1 for each requested golden item** (golden item ≤ 2.0; non-golden ≤ 1.0).
  Plus MC correctness + causal-chain quality.
- **Loop**: ≤3 Optimizer↔Evaluator rounds, else discard.
- **Generation agents see the FULL context incl. the answer** (they build the benchmark);
  the **answering agent sees only the stem + gated tool results**, never `outcome`.

## Backends
`backend.py` chooses via `SIMR_BACKEND`: `ollama` (default, local — talks to
localhost:11434; keys map to tags in `OLLAMA_TAGS`) or `hf` (cluster/GPU — loads
weights from `../../loaded_models/`). No torch needed for the Ollama path.

## Quick commands
```bash
# no GPU / no network — verifies the whole loop
cd Question_Gen && python orchestrator.py --dry-run --n 5

# real run, LOCAL via Ollama (pull mistral-small3.1 / phi4-mini / gpt-oss:20b first):
SIMR_BACKEND=ollama python orchestrator.py --n 2

# real run (GPU cluster): pilot then full
SIMR_BACKEND=hf python orchestrator.py --n 20
python orchestrator.py --n 500 --types next_procedure readmission_30d mortality_1y deterioration

# serve questions to answering agents
cd ../MCP_Server && SUPPLEMENTALS_DIR=$PWD/supplementals python server.py
```
Outputs: `Question_Gen/outputs/questions.jsonl` + `MCP_Server/supplementals/<question_id>.json`.

## Status & known watch-outs
- **Verified locally** (no GPU): context build (982 eligible tuples), eligibility, schema
  validation, full orchestration loop, bundle export, live PubMed connection (16 tools).
  Dry-run: 6/6 questions valid.
- **Deferred to GPU**: the three models actually generating text (drafts/critiques/citations).
- **Before the real run, consider** (not yet built): a `pre_t0` **summarizer** (raw rows can
  overflow Phi's context — pass per-lab summaries instead), configurable **per-subtask lookback
  windows** (input window is currently unbounded-left), and the answering-agent **scorer**
  (`score_answer.py`) that applies each question's rubric.
- **Demo data**: many lab charttimes are date-level (00:00:00) → coarse splits; no ED-triage
  vitals; PubMed PMIDs are placeholders ONLY in `--dry-run`.
- **Eligibility scan** ~3 min on the demo; cache to parquet for full MIMIC-IV (RUN.md §7).

## Conventions
- Workflow-free: these are plain Python modules run with `python <module>.py`, not Claude
  Workflow scripts. Run everything from `Question_Gen/` (imports are flat, not a package).
- Real PHI stays local; only de-identified concepts go to PubMed (enforced by `tools.guard_args`).

---
## V3 LOCAL-RUN UPDATE (final architecture)

Question generation runs **locally on Ollama** and is proven end-to-end (real accepted
questions generated for A, B, and C).

**2-agent loop (Scorer role removed):**
- Optimizer = Mistral Small 3.1 (`mistral-small3.1`) — authors the question.
- Evaluator = **GPT-OSS 20B** (`gpt-oss:20b`) — quality gate (Phi/Phi-4-mini were too weak:
  self-contradiction, malformed JSON). Override via `SIMR_EVAL_MODEL`.
- Grading rubric is attached **deterministically** (`prompts.canonical_rubric()`), not by an LLM.

**Backend:** `backend.py` selects via `SIMR_BACKEND=ollama|hf` (default `ollama`). Ollama uses
native tool-calling for the (A) Optimizer and a large `num_ctx` (`SIMR_NUM_CTX`, default 16384);
`hf` path loads weights from `../../loaded_models/`.

**Run locally:**
```bash
cd Question_Gen
SIMR_BACKEND=ollama python orchestrator.py --n 5        # add SIMR_DEBUG=1 for round-by-round scores
```
Outputs: `outputs/questions.jsonl` (+ `outputs/answering/` for B/C, `../MCP_Server/supplementals/` for A).

**Other final changes:**
- A generation is agentic: Optimizer retrieves only needed values via the 3-tool MCP server
  (`Access_All_supplementals_no_values`, `Request_a_supplemental`, `Request_values`).
- Stems are detailed clinical **vignettes** (patient intro + history); only decisive golden
  values + the answer are withheld.
- A `next_procedure` is anchored to genuinely **lab-driven** procedures (dialysis/transfusion),
  golden set = the **abnormal** decisive labs (minimal/necessary).
- Citations are **best-effort** (real PMID via `search_articles` when found; not a hard gate).

**Demo data-scarcity (100 patients) — expect few accepted questions on the demo:**
- A: ~1 clean lab-driven `next_procedure` case. B: ~1/3 accept over 611 eligible. C: ~1 divergent
  lab-effect pair. All scale on full MIMIC-IV; the demo is for validating the pipeline (done).
