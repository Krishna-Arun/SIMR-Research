# Benchmarks

This directory contains all benchmarking workflows and data for the SIMR Research project.

## Structure

```
benchmarks/
├── aki/                          # AKI (Acute Kidney Injury) next-event prediction
│   ├── answer_agent.js           # Run answering agent for one case
│   ├── experiment.js             # Orchestrator: both conditions × all cases
│   ├── evaluator_optimizer.js    # Generate + validate questions via loop
│   ├── supervisor_grader.js      # Reward → Critic → Optimizer grading
│   ├── all_patients_args.json    # Pre-built args for 4 AKI cases
│   ├── prep_patients.py          # Extract MIMIC-IV patients (4)
│   ├── generate_patient_scripts.py
│   ├── profile_patient.py
│   ├── patient_data/             # 8 files (4 full + 4 trimmed MIMIC patients)
│   ├── patient_workflows/        # 67 generated question/stem workflows
│   └── output/                   # Benchmark manifests and run JSONs
│       └── aki_benchmark_v1.json
│
├── cardiac-nextlab/              # Next-Troponin-I + cardiac procedure prediction
│   ├── nextlab_answer_agent.js           # Labs-only variant
│   ├── nextlab_answer_agent_v2.js        # With PubMed tool toggle
│   ├── nextlab_answer_agent_fullehr.js   # Full-EHR variant
│   ├── nextlab_experiment.js             # 20-case labs-only experiment
│   ├── nextlab_experiment_fullehr.js     # Full-EHR comparison experiment
│   ├── nextlab_experiment_pubmed.js      # PubMed ablation (2 conditions)
│   ├── comparison_case{,_2,_3,_4}.js     # Baseline comparisons
│   ├── prep_cardiac_nextlab.py           # Prep labs-only benchmark
│   ├── prep_cardiac_nextlab_fullehr.py   # Prep full-EHR benchmark
│   └── output/                             # Benchmark manifests + per-case files
│
├── cardiac-dirchange/            # Direction-reversal troponin scenarios (100 cases)
│   ├── dirchange_experiment.js       # All 100 cases in parallel
│   ├── dirchange_one_each_seq.js     # Light: one per reversal type (4 total)
│   ├── prep_cardiac_dirchange_v1.py  # Prep benchmark data
│   └── output/                         # Per-case JSON files + manifest
│
├── cardiac-multilab/             # Masked-troponin multi-lab prediction (100 cases)
│   ├── multilab_answer_agent.js      # Agent with full_ehr/labs_only/no_tools toggle
│   ├── multilab_experiment.js        # Full-EHR + labs-only experiment
│   ├── prep_cardiac_multilab_v1.py   # Prep benchmark data
│   └── output/                         # Per-case JSON files + manifest
│
├── common/                       # Shared resources
│   ├── prep_patients_ehrshot.py    # EHRSHOT cardiac case extraction (67 patients)
│   ├── test_embed.js               # Embedding test
│   ├── test_generator_patient.js   # Question generator test
│   ├── test_pubmed.js              # PubMed API test
│   ├── test_schemas.js             # Schema validation test
│   ├── test_supervisor.js          # Supervisor grader test
│   └── test_trajectory.json        # Test data
│
├── patient_data_ehrshot/         # 134 files (67 full + 67 trimmed EHRSHOT patients)
└── README.md
