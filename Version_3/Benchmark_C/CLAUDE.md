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
