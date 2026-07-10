# CLAUDE.md — Benchmark C (Version 3)

Context for Claude Code / any agent working this benchmark on the compute cluster.
Step-by-step procedure: **[RUN.md](RUN.md)**.

## What Benchmark C tests
Two patients (**A** and **B**), each with a pre-intervention state (labs + micro) and
each having undergone a **different** procedure, are chosen to have **similar baselines**.
The agent is shown **one** observed post-procedure lab panel (72h, absolute values) that
belongs to exactly one of them, and must identify **which patient** it came from — using
the **causal effects** of each procedure, not baseline matching (baselines are similar by
construction). Standalone task, **no MCP server**. Score **0/1** on identification;
confidence recorded (compared with activation probability), **not scored**. Added onto
Benchmark A's answer rubric; causal justification also graded.

## Design decisions (locked)
- **Pairing**: two patients with **similar pre-state** (small z-distance over shared labs) and
  **different procedure types**, from **different subjects**. This forces causal reasoning.
- **Post evidence**: **absolute** post values (both pre-states given so the agent can reason about deltas).
- **Shared labs**: the observed panel + comparison are restricted to labs both patients have as
  core labs (≥2 pre & ≥2 post-72h, valid ref range); ≥3 shared required.
- **Answer balance**: ground truth alternates A/B across questions (50/50).
- **Confidence**: recorded, not scored. Score is purely 0/1.
- **Pairing + answer are DATA-DERIVED**; the agents only author/vet the causal framing.

## Pairing knobs (`prompts.py` / `context_builder.py`)
- `MAX_PRESTATE_DISTANCE = 0.75` — max mean |z| over shared labs for a pair to count as "similar".
- `MIN_SHARED_LABS = 3`, `POST_WINDOW_HOURS = 72`, `MIN_PRE/MIN_POST = 2`, `MAX_UNITS = 400` (O(n²) cap).
- `_EXCLUDE_LABEL_SUBSTR` drops non-therapeutic events (EKG, CT, imaging, transport, lines docs…).

## Module map (`Question_Gen/`)
| File | Role |
|---|---|
| `prompts.py` | Shared spec (task, pairing rule, 0/1 scoring). |
| `schema.py` | Attribution-record contract + `validate()` (two different procedures; observed ⊆ shared). |
| `context_builder.py` | Units → similar-baseline/different-procedure pairing → observed panel + answer. Own `MimicDemo`. |
| `optimizer_agent.py` | Mistral — authors stem + causal chain + reference answer (does NOT choose the answer). |
| `evaluator_agent.py` | Phi — checks different procedures / causal discrimination / matches observed / no leakage. |
| `scorer_agent.py` | GPT-OSS — quality score + 0/1 identification rubric. |
| `orchestrator.py` | Full loop + offline `--dry-run`; strict answering-view whitelist. |
| `backend.py`, `mcp_client.py`, `tools.py`, `agentic_loop.py` | Generic infra copied from A (PubMed optional). |

## Quick commands
```bash
cd Question_Gen
python orchestrator.py --dry-run --n 5     # no models/network — verifies the loop
python orchestrator.py --n 20              # GPU pilot
python orchestrator.py --n 500             # full run
```
Outputs: `outputs/questions.jsonl` (full, WITH answer) + `outputs/answering/<qid>.json`
(**strict whitelist** — answer, causal chain, reference answer, winner effects all stripped).

## Status & watch-outs
- **Verified locally**: 400 units → **103 similar-baseline pairs**; dry-run valid; answering
  views leak nothing; answer balance ~50/50.
- **Deferred to GPU**: the three models authoring/critiquing the causal framing.
- **Similarity threshold** `MAX_PRESTATE_DISTANCE` is the key difficulty knob — lower ⇒ more
  confusable pairs (harder, more causal). Sweep on the real set.
- **Procedure quality**: the exclusion list removes diagnostics/monitoring; review the pair list
  before a full run so both arms are genuinely therapeutic with divergent lab effects.
- **Demo timestamps** are often date-level → coarse 72h windows; full MIMIC-IV has real times.

## Conventions
- Plain Python modules run from `Question_Gen/`. Not Workflow scripts.
- Real PHI stays local; PubMed (optional) receives only de-identified concepts.

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
