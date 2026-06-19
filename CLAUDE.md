# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Does

AKI (Acute Kidney Injury) next-event prediction benchmark. An LLM agent is given a clinical question about an AKI patient, must query MIMIC-IV lab data through MCP tools, and predict the next major procedural intervention (e.g. CRRT, dialysis, mechanical ventilation). The system generates questions, evaluates agent trajectories, and grades them with a supervisor team.

---

## Running the Components

### Kidney MCP Server (Python)
```bash
cd kidney-mcp-server
pip install -r requirements.txt
python3 server/index.py
```
Builds the FAISS RAG index on first run (slow); subsequent runs load from `cache/`. Set `MIMIC_DATA_DIR` to override the default MIMIC-IV hosp path.

### PubMed MCP Server (Node.js)
```bash
cd PubMed-MCP-Server
npm install
npm run build   # compiles TypeScript → build/
npm start
```
Optional env vars: `NCBI_API_KEY` (raises rate limit from 3 → 10 req/s), `NCBI_EMAIL`.

### Benchmark Data Preparation
```bash
python3 benchmark/prep_patients.py              # builds patient_data/*.json from MIMIC-IV
python3 benchmark/generate_patient_scripts.py   # embeds patients into patient_workflows/*.js
```
`prep_patients.py` produces `patient_data/patient_<id>.json` (full) and `patient_data/patient_<id>_trimmed.json` (with fields `patient_context`, `lab_data`, `ground_truth_procedure`). `generate_patient_scripts.py` reads the trimmed files listed in `TRIMMED_FILES` at the top of the script.

### Invoking Benchmark Workflows

All `.js` files in `benchmark/` are Claude Code Workflow scripts — they run via the `Workflow` tool, not Node.js directly.

```
# Full experiment (all 4 cases × both conditions):
Workflow({ scriptPath: 'benchmark/experiment.js' })

# Targeted run:
Workflow({ scriptPath: 'benchmark/experiment.js' }, { case_ids: [1], conditions: ['with_lab_tools'] })

# Single answering agent:
Workflow({ scriptPath: 'benchmark/answer_agent.js' }, { condition: 'with_lab_tools', case_id: 1 })

# Grade a pre-saved trajectory (file path form):
Workflow({ scriptPath: 'benchmark/supervisor_grader.js' }, { trajectory_file: '/path/to/trajectory.json' })

# Grade inline:
Workflow({ scriptPath: 'benchmark/supervisor_grader.js' }, { case_id: 1, trajectory: { ... } })

# Generate question for one patient:
Workflow({ scriptPath: 'benchmark/patient_workflows/patient_10039708.js' })
```

`benchmark/all_patients_args.json` contains pre-built args objects for all 4 cases (for passing to experiment.js).

### Smoke-test scripts
```bash
# These are workflow scripts — run via Workflow tool, not node:
benchmark/test_supervisor.js       # grades benchmark/test_trajectory.json against case 1
benchmark/test_schemas.js          # validates ANSWER_SCHEMA / REWARD_SCHEMA structure
benchmark/test_generator_patient.js
benchmark/test_pubmed.js
benchmark/test_embed.js
```

---

## Architecture

### Three-Layer Pipeline

```
Benchmark Workflows (Claude Code .js scripts)
        │
        ├── kidney-mcp-server (Python, stdio MCP)
        │       ├── search_kidney_guidelines  — RAG over KDIGO PDFs
        │       ├── request_all_labs_no_values — shows lab names + dates only; must be called first
        │       └── request_a_lab              — returns actual values; gated behind tool above
        │
        └── PubMed-MCP-Server (Node.js, stdio MCP)
                └── 16 tools for PubMed search, retrieval, citation
```

### Kidney MCP Server internals
- `rag/kidney_rag.py` — loads KDIGO PDFs, chunks by double-newline then sliding window, builds FAISS IndexFlatIP with `all-MiniLM-L6-v2` embeddings, caches to `cache/`
- `tools/lab_tools.py` — reads `labevents.csv.gz` + `d_labitems.csv.gz` lazily (cached per subject_id). Session-level state `_labs_viewed` gates `request_a_lab` per patient. `request_all_labs_no_values` appends a directive telling the agent to exhaust all lab combinations. Restarting the server clears `_labs_viewed`.
- `server/index.py` — registers all three tools; builds RAG index at startup

### Benchmark Workflows
All `.js` files in `benchmark/` are Claude Code workflow scripts (not plain Node.js). They use `agent()`, `parallel()`, `pipeline()`, `phase()`, `log()`, `args`.

| File | Purpose | Args |
|---|---|---|
| `evaluator_optimizer.js` | Generates + validates benchmark questions via Generate → Evaluate → Rubric loop | patient context object |
| `patient_workflows/patient_<id>.js` | Per-patient self-contained question generation (patient data embedded) | none |
| `answer_agent.js` | Answering agent sub-workflow — runs one condition for one case, returns trajectory | `{ condition, case_id }` |
| `experiment.js` | Orchestrator — runs both conditions × all cases, grades each, returns comparison table | `{ case_ids?, conditions? }` |
| `supervisor_grader.js` | Grades a pre-collected answering agent trajectory with Reward → Critic → Optimizer | `{ case_id, trajectory }` or `{ trajectory_file }` |

### Question generation loop (patient_workflows)
Each `patient_workflows/patient_<id>.js` runs a **Generate → Evaluate → Rubric** loop (up to 5 rounds):
1. **Generate** — drafts a question stem (no lab values) + classifies L_core / L_optional / L_irrelevant; first calls PubMed to ground L_core in KDIGO citations
2. **Evaluate** — strict 4-criterion check (A: unanswerable without labs; B: next major procedure; C: correct lab classification with KDIGO citations; D: correct demographics); rejects and loops with feedback on any failure
3. **Rubric** — builds full answer rubric (c1–c4) and lab scoring rubric for the approved question; stored in `benchmark/output/`

These scripts are generated by `generate_patient_scripts.py` — edit the template in that file, not the generated `.js` files.

### Two-condition experiment system

`answer_agent.js` is the modular seam — `CONDITION_CONFIGS` at the top defines every condition variant. Adding a new condition = one new entry in that object. Conditions: `with_lab_tools` (two lab MCP tools only, no guidelines/PubMed), `no_tools` (zero external tools, pure reasoning).

`experiment.js` calls `answer_agent.js` then `supervisor_grader.js` for each (condition × case_id) pair. To swap models, set `model: 'claude-opus-4-8'` in the config entry; `model: null` inherits the session model.

### supervisor_grader.js agent team
- **Reward Agent** — outputs all numeric scores: R_core, R_wrong, R_under, R_over, R_justification → `lab_score` (max 0.70); c1–c4 → `answer_score` (max 1.00); total max 1.70. Scores justification 0/0.5/1 for **every** lab request (L_core, L_optional, and L_irrelevant each have different criteria).
- **Critic Agent** — no scoring authority; explains each score, quotes agent text, provides model score-1 examples.
- **Optimizer Agent** — placeholder for future RL; currently outputs prompt-level policy suggestions ranked by expected score delta.

### Benchmark data
- `benchmark/output/aki_benchmark_v1.json` — 4 cases, each with question stem, L_core/L_optional/L_irrelevant lab sets, full answer rubric (c1–c4), lab scoring rubric (R formulas, justification criteria), and ground truth.
- Question stems include `Patient MIMIC subject_id: <id>` as the first line so answering agents can pass it to the lab tools.
- MIMIC-IV demo data: `mimic-iv-clinical-database-demo-2.2/hosp/` — 100 patients, 107K lab events.

### Scoring formula
```
lab_score   = min(0.70, 0.35·R_core + 0.20·R_wrong + 0.10·R_under + 0.20·R_over + 0.15·R_justification)
answer_score = mean(c1, c2, c3, c4)          # each criterion 0–1
total        = lab_score + answer_score       # max 1.70
```
Penalty params: β=2 (R_under), α=0.5 (R_over).

---

## Key Conventions

- MCP tool names in workflow prompts follow the pattern `mcp__<server-name>__<tool-name>`. The kidney server is named `kidney-guidelines-rag`, so tools are `mcp__kidney-guidelines-rag__request_all_labs_no_values` etc.
- Workflow scripts cannot use `Date.now()`, `Math.random()`, or `new Date()` (breaks resume). No filesystem access in script body — use `agent()` with the Read tool to load files.
- `subject_id` is the MIMIC-IV patient identifier (e.g. `"10039708"`). It is distinct from `case_id` (1–4, the benchmark case index).
- The lab tools gate: `request_all_labs_no_values` must be called before `request_a_lab` for a given `subject_id` within a session. State is in-memory, per-server-process.
- **Absolute paths are hardcoded** in `answer_agent.js`, `experiment.js`, and `supervisor_grader.js` (`BENCHMARK_PATH`, `ANSWER_AGENT_PATH`, `SUPERVISOR_PATH`). If the repo moves, update these constants.
- `patient_workflows/patient_<id>.js` files are **generated** — run `generate_patient_scripts.py` to regenerate them. Edit the template in that file, not the generated output.
