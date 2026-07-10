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
