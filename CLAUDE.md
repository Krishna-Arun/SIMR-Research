# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Does

**AKI Benchmark**: An LLM agent is given a clinical question about an AKI patient, must query MIMIC-IV lab data through MCP tools, and predict the next major procedural intervention (e.g. CRRT, dialysis, mechanical ventilation). The system generates questions, evaluates agent trajectories, and grades them with a supervisor team.

**Cardiac Benchmarks**: EHRSHOT-based cardiac benchmarks covering serial Troponin I prediction (labs-only and full-EHR variants), direction-reversal scenarios, and masked-troponin multi-lab prediction — all testing whether agents can use cross-lab signals to make clinical predictions.

**Species Benchmark**: A species-invariant clinical reasoning benchmark that tests whether AI agents reason from *provided lab reference ranges* versus applying *memorized human clinical norms*. Real EHRSHOT cases are translated into fictional species (dog, horse, Velox noctis) using z-score preservation; models relying on memorized human ranges fail because the same numerical value can be normal in one species and critically abnormal in another.

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

#### AKI Benchmark (MIMIC-IV)
```bash
python3 benchmarks/aki/prep_patients.py              # builds patient_data/*.json from MIMIC-IV (4 patients)
python3 benchmarks/aki/generate_patient_scripts.py   # embeds patients into patient_workflows/*.js
```
`prep_patients.py` produces `patient_data/patient_<id>.json` (full) and `patient_data/patient_<id>_trimmed.json`. `generate_patient_scripts.py` reads the trimmed files listed in `TRIMMED_FILES` at the top of the script.

#### Cardiac Benchmark (EHRSHOT)
```bash
python3 benchmarks/common/prep_patients_ehrshot.py              # extracts 67 EHRSHOT cardiac cases → benchmarks/patient_data_ehrshot/
python3 benchmarks/cardiac-nextlab/prep_cardiac_nextlab.py               # labs-only next-Troponin-I benchmark (20 patients)
python3 benchmarks/cardiac-nextlab/prep_cardiac_nextlab_fullehr.py       # full-EHR variant (same 20 patients, full context)
```

#### Species Benchmark
```bash
python3 species-benchmark/scripts/data_prep/select_ehrshot_cases.py   # scan EHRSHOT for CVD patients → candidate_cases.json
python3 species-benchmark/scripts/data_prep/translate_cases.py        # z-score translate to dog/horse/Velox noctis
python3 species-benchmark/scripts/data_prep/build_benchmark.py        # build main benchmark (30 cases)
python3 species-benchmark/scripts/data_prep/build_anti_memo_v2.py    # build harder anti-memorization variant
```

---

## Invoking Benchmarks

### AKI Benchmark — Workflow Scripts

All `.js` files in `benchmarks/` are Claude Code Workflow scripts — they run via the `Workflow` tool, not Node.js directly.

```
# Full experiment (all 4 cases × both conditions):
Workflow({ scriptPath: 'benchmarks/aki/experiment.js' })

# Targeted run:
Workflow({ scriptPath: 'benchmarks/aki/experiment.js' }, { case_ids: [1], conditions: ['with_lab_tools'] })

# Single answering agent:
Workflow({ scriptPath: 'benchmarks/aki/answer_agent.js' }, { condition: 'with_lab_tools', case_id: 1 })

# Grade a pre-saved trajectory (file path form):
Workflow({ scriptPath: 'benchmarks/aki/supervisor_grader.js' }, { trajectory_file: '/path/to/trajectory.json' })

# Grade inline:
Workflow({ scriptPath: 'benchmarks/aki/supervisor_grader.js' }, { case_id: 1, trajectory: { ... } })

# Generate question for one patient:
Workflow({ scriptPath: 'benchmarks/aki/patient_workflows/patient_10039708.js' })
```

`benchmarks/aki/all_patients_args.json` contains pre-built args objects for all 4 AKI cases.

### Cardiac Benchmarks — Workflow Scripts

#### Next-Troponin-I (labs-only)
```
# Run 20 cases:
Workflow({ scriptPath: 'benchmarks/cardiac-nextlab/nextlab_experiment.js' })

# PubMed ablation (20 cases × 2 conditions):
Workflow({ scriptPath: 'benchmarks/cardiac-nextlab/nextlab_experiment_pubmed.js' })

# Full-EHR comparison:
Workflow({ scriptPath: 'benchmarks/cardiac-nextlab/nextlab_experiment_fullehr.js' })
```

#### Direction-Reversal (100 cases, trend reversals)
```
# All 100 cases in parallel:
Workflow({ scriptPath: 'benchmarks/cardiac-dirchange/dirchange_experiment.js' })

# Light version: one case per reversal type (4 total), sequential:
Workflow({ scriptPath: 'benchmarks/cardiac-dirchange/dirchange_one_each_seq.js' })
```

#### Multi-Lab Masked-Troponin (100 cases)
```
Workflow({ scriptPath: 'benchmarks/cardiac-multilab/multilab_experiment.js' })
```

### Species Benchmark — Workflow Scripts

```
# Main benchmark evaluator (30 cases):
Workflow({ scriptPath: 'species-benchmark/evaluate.js' })

# Counterfactual sensitivity test (7 cases × 2 conditions):
Workflow({ scriptPath: 'species-benchmark/benchmark/run_counterfactual.js' })
```

### Smoke-test scripts
```bash
# These are workflow scripts — run via Workflow tool, not node:
benchmarks/common/test_supervisor.js       # grades benchmarks/aki/output/aki_benchmark_v1.json against case 1
benchmarks/common/test_schemas.js          # validates ANSWER_SCHEMA / REWARD_SCHEMA structure
benchmarks/common/test_generator_patient.js
benchmarks/common/test_pubmed.js
benchmarks/common/test_embed.js
```

---

## Architecture

### Three-Layer Pipeline (AKI)

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

### Benchmark Workflows (AKI)
All `.js` files in `benchmarks/aki/` are Claude Code workflow scripts (not plain Node.js). They use `agent()`, `parallel()`, `pipeline()`, `phase()`, `log()`, `args`.

| File | Purpose | Args |
|---|---|---|
| `evaluator_optimizer.js` | Generates + validates benchmark questions via Generate → Evaluate → Rubric loop | patient context object |
| `patient_workflows/patient_<id>.js` | Per-patient self-contained question generation (patient data embedded) | none |
| `answer_agent.js` | Answering agent sub-workflow — runs one condition for one case, returns trajectory | `{ condition, case_id }` |
| `experiment.js` | Orchestrator — runs both conditions × all cases, grades each, returns comparison table | `{ case_ids?, conditions? }` |
| `supervisor_grader.js` | Grades a pre-collected answering agent trajectory with Reward → Critic → Optimizer | `{ case_id, trajectory }` or `{ trajectory_file }` |

### Question generation loop (AKI patient_workflows)
Each `patient_workflows/patient_<id>.js` runs a **Generate → Evaluate → Rubric** loop (up to 5 rounds):
1. **Generate** — drafts a question stem (no lab values) + classifies L_core / L_optional / L_irrelevant; first calls PubMed to ground L_core in KDIGO citations
2. **Evaluate** — strict 4-criterion check (A: unanswerable without labs; B: next major procedure; C: correct lab classification with KDIGO citations; D: correct demographics); rejects and loops with feedback on any failure
3. **Rubric** — builds full answer rubric (c1–c4) and lab scoring rubric for the approved question; stored in `benchmarks/aki/output/`

These scripts are generated by `generate_patient_scripts.py` — edit the template in that file, not the generated `.js` files.

### Cardiac Benchmark Architecture

**Data flow**: EHRSHOT database (`EHRSHOT Hackathon Project/meds_reader_omop_ehrshot/`) → Python prep scripts → JSON case files → Workflow evaluation.

| Prep script | Output benchmark | Cases | Scope |
|---|---|---|---|
| `prep_patients_ehrshot.py` | — | 67 patients | ACS + HF cardiac cases with action labels |
| `prep_cardiac_nextlab.py` | `cardiac_nextlab_benchmark_v1.json` | 20 | Labs-only, next-Troponin-I prediction |
| `prep_cardiac_nextlab_fullehr.py` | `cardiac_nextlab_fullehr_benchmark_v1.json` | 20 | Full-EHR (dx + meds + procs + obs + visits + labs) |

Cardiac answer agents:
- `nextlab_answer_agent.js` — loads case, prompts with lab table, predicts next Troponin I
- `nextlab_answer_agent_fullehr.js` — same prompt with full EHR context included
- `nextlab_answer_agent_v2.js` — agent with `with_pubmed`/`without_pubmed` condition toggle

Cardinal scoring (labs-only): `direction_correct=0.40`, `within_50%=0.35`, `within_20%=0.25` (max 1.0).

Direction-reversal design: Every case has a visible troponin trend that reverses at the target time, making both last-value and trend-extrapolation heuristics wrong by construction. Agents must use cross-lab signal (BNP, creatinine, vitals, meds) to detect the reversal.

Multi-lab masked-troponin: The last visible troponin value is hidden; agents predict using cross-lab signals that continue up to the target time. 50% hard (1 visible troponin), 50% medium/easy (2+).

### Species Benchmark Architecture

**Design principle**: Take real human EHR cases with clinically significant lab abnormalities, translate them into species' reference frames using z-score preservation (`animal_value = animal_mean + z * animal_sd`), and present the cases so the correct answer requires reading the provided reference table. A model relying on memorized human ranges will get the wrong answer.

**Data pipeline**:
```
EHRSHOT DB → select_ehrshot_cases.py → candidate_cases.json (17M candidates)
                                    → translate_cases.py → translated_cases.json
                                                    → build_benchmark.py → species_benchmark_v1.json (30 cases)
                                                    → build_anti_memo_v2.py → anti_memo_benchmark_v2.json (harder variant)
```

Species covered: **human** (baseline), **dog** (Tier 1), **horse** (Tier 2), **Velox noctis** / Tier 3, fictional species with inverted physiology (e.g., K+ normal 1.0-2.5 mEq/L vs human 3.5-5.0; creatinine is a hepatic marker, not renal).

Anti-memorization variants:
- v1: pivot labs within human normal but VN-abnormal (K+ 3.8-4.9, Na 136-143, Cr 0.6-1.05)
- v2 (harder): opposite-treatment zones where K+ 2.6-3.1 causes hypokalemia in humans but hyperkalemia in VN; natural variation in non-pivot labs instead of uniform midpoints

**Evaluation**: `evaluate.js` loads cases, runs agent with explicit instruction to use only provided reference ranges, scores on 3 binary criteria (correct_action, pivot_lab_cited, threshold_compared). `run_counterfactual.js` tests sensitivity by running each case twice — real vs counterfactual (pivot lab set to VN-normal midpoint) — grading whether answers differ.

Reference ranges in `reference_ranges/species_reference_ranges.json` (661 lines); physiology guide in `reference_ranges/vn_physiology_guide.md`.

---

## Benchmark Data Catalog

### AKI Output
| File | Description |
|---|---|
| `benchmarks/aki/output/aki_benchmark_v1.json` | 4 cases with question stems, lab classifications, rubrics, ground truth |
| `benchmarks/aki/patient_data/*.json` | 8 files (4 full + 4 trimmed) from MIMIC-IV demo (100 patients, 107K labs) |
| `benchmarks/aki/output/` | AKI-specific output subdirectory (patient run JSONs) |

### Cardiac Output
| File | Description |
|---|---|
| `benchmarks/cardiac-nextlab/output/cardiac_nextlab_benchmark_v1.json` | 20-case labs-only manifest (next-Troponin-I) |
| `benchmarks/cardiac-nextlab/output/cardiac_nextlab_fullehr_benchmark_v1.json` | ~3.3 MB, 20-case full-EHR manifest |
| `benchmarks/cardiac-dirchange/output/cardiac_dirchange_benchmark_v1.json` | 100-case direction-reversal manifest |
| `benchmarks/cardiac-dirchange/output/` | Per-case JSON files for dirchange experiment (case_001.json ... case_100.json) |
| `benchmarks/cardiac-multilab/output/cardiac_multilab_benchmark_v1.json` | 100-case masked-troponin manifest |
| `benchmarks/patient_data_ehrshot/*.json` | 134 files (67 full + 67 trimmed) from EHRSHOT |

### Species Output
| File | Path |
|---|---|
| Main benchmark | `species-benchmark/output/species_benchmark_v1.json` |
| Anti-memo v1 | `species-benchmark/output/anti_memo_benchmark_v1.json` |
| Anti-memo v2 (harder) | `species-benchmark/output/anti_memo_benchmark_v2.json` |
| Case index | `species-benchmark/output/case_index.json` |
| Candidate cases | `species-benchmark/data/candidate_cases.json` (17 MB) |
| Species reference ranges | `species-benchmark/reference_ranges/species_reference_ranges.json` |
| VN physiology guide | `species-benchmark/reference_ranges/vn_physiology_guide.md` |

---

## Scoring Formula (AKI)

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
- **Absolute paths are hardcoded** in `benchmarks/aki/answer_agent.js`, `benchmarks/aki/experiment.js`, and `benchmarks/aki/supervisor_grader.js` (`BENCHMARK_PATH`, `ANSWER_AGENT_PATH`, `SUPERVISOR_PATH`). If the repo moves, update these constants.
- `patient_workflows/patient_<id>.js` files are **generated** — run `generate_patient_scripts.py` to regenerate them. Edit the template in that file, not the generated output.
- **supervisor_grader.js agent team**: Reward Agent (scoring authority), Critic Agent (explanations, no scoring), Optimizer Agent (RL placeholder). Total lab_score max 0.70, answer_score max 1.00, combined max 1.70.
