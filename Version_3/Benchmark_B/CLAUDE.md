# CLAUDE.md — Benchmark B (Version 3)

Context for Claude Code / any agent working this benchmark on the compute cluster.
Step-by-step procedure: **[RUN.md](RUN.md)**.

## What Benchmark B tests
Given a patient's **pre-procedure** clinical state (labs + microbiology, with values)
and the **procedure(s)** performed, an answering agent must **predict how each of a set
of core labs will trend over the 72h AFTER the procedure** — **Rising / Falling / Stable** —
with a **causal justification**. It also reports a confidence distribution (recorded for
calibration, **not scored**). This is a **standalone prediction** task: the pre-procedure
data is given directly; there is **no data-request mechanism** and **no supplementals MCP
server** (unlike Benchmark A).

## Design decisions (locked)
- **Anchor / time-zero**: the procedure start time. Post window = **72h**.
- **Core lab**: measured **≥2 times before** AND **≥2 times within 72h after** the procedure,
  with a valid reference range. A question needs **≥3 core labs** and ≥1 non-Stable.
- **Direction rule (reference-range-relative)**: with width `W = ref_high - ref_low`,
  `pre` = last value before t0, `post` = last value within 72h after t0, `delta = post - pre`:
  **Stable** if `|delta| ≤ 0.25·W`, else **Rising**/**Falling** by sign.
  (`STABLE_BAND_FRAC = 0.25` in `prompts.py` — tunable.)
- **Granularity**: one direction per lab across the procedure (pre→post), not segmented.
- **Scoring** (per lab, added onto A's answer rubric): `1` correct direction; `0.5` actual
  Rising/Falling but predicted Stable; `0` opposite (or actual Stable, predicted a direction).
- **Confidence**: agent outputs a distribution over the 3 classes — recorded, **not scored**.
- **Directions are DATA-DERIVED** (context_builder), not authored. The generation agents
  only write the framing + causal explanation of those given directions.

## Module map (`Question_Gen/`)
| File | Role |
|---|---|
| `prompts.py` | Shared spec (task, direction rule, 72h window, scoring). `STABLE_BAND_FRAC`, `POST_WINDOW_HOURS`. |
| `schema.py` | Trajectory-record contract + `validate()` (enforces no post-value leakage in `targets`). |
| `context_builder.py` | Procedure-anchored; core-lab detection; reference-range direction labeling. Own `MimicDemo`. |
| `optimizer_agent.py` | Mistral — authors stem + causal chain + reference answer (does NOT set directions). |
| `evaluator_agent.py` | Phi — checks causal soundness / coverage / non-trivial / no leakage / answer matches. |
| `scorer_agent.py` | GPT-OSS — quality score + per-lab direction rubric. |
| `orchestrator.py` | Full loop + offline `--dry-run`; writes `questions.jsonl` + `outputs/answering/` (ground truth stripped). |
| `backend.py`, `mcp_client.py`, `tools.py`, `agentic_loop.py` | Generic infra copied from Benchmark A (PubMed optional; not required for B). |

## Quick commands
```bash
cd Question_Gen
python orchestrator.py --dry-run --n 5      # no models/network — verifies the loop
python orchestrator.py --n 20               # GPU pilot
python orchestrator.py --n 500              # full run
```
Outputs: `Question_Gen/outputs/questions.jsonl` (full, WITH answer key) +
`Question_Gen/outputs/answering/<question_id>.json` (answer key stripped — serve THIS to agents).

## Status & watch-outs
- **Verified locally**: context build (**611 eligible** procedure-questions), schema validation,
  full dry-run loop, answering-view export.
- **Deferred to GPU**: the three models authoring/critiquing the causal framing.
- **Procedure filter**: non-clinical `procedureevents` (Communication, "updated by", gauges,
  cultures, imaging labels) are excluded in `context_builder._procedures` — tunable.
- **Demo timestamps** are often date-level → 72h windows are coarse; full MIMIC-IV has real times.
- **Direction threshold** (`STABLE_BAND_FRAC=0.25`) is a judgement call — sweep it if the
  Stable fraction looks off for the real set.

## Conventions
- Plain Python modules (`python <module>.py`), run from `Question_Gen/`. Not Workflow scripts.
- Real PHI stays local; PubMed (optional here) receives only de-identified concepts.

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
