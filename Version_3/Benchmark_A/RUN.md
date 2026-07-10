# Benchmark A — Real Run Runbook

End-to-end procedure to generate the Benchmark A question set on a GPU node, then
serve the questions to answering agents. Read top to bottom the first time.

> **Scope note.** Built and validated on the 100-patient MIMIC-IV **demo**. The code
> is structured to scale to full MIMIC-IV by swapping the data loader (see §7).
> Real PHI stays local: only de-identified clinical *concepts* go to PubMed (enforced
> by the query guard in `Question_Gen/tools.py`).

---

## 0. What runs where
| Stage | Where | Needs GPU? | Needs network? |
|---|---|---|---|
| Model download | GPU node | no | yes (HF) |
| PubMed server build | any | no | yes (npm) |
| Context build / eligibility | CPU | no | no |
| Question generation (3 agents) | GPU node | **yes** | yes (PubMed/NCBI) |
| Serving to answering agents | CPU | no | no |

---

## 1. Environment
```bash
cd Version_3
pip install -r requirements.txt            # transformers, torch, accelerate, dotenv, pyyaml, bitsandbytes
pip install pandas pyarrow mcp             # data + MCP server deps
# token for gated models:
echo 'HF_TOKEN=hf_xxx' > .env               # (already set if you did the model step)
```
Python 3.10+; a CUDA-enabled torch build on the GPU node.

## 2. Models (once)
```bash
cd Version_3/loaded_models
python download_models.py mistral-small-3.1 phi-4-mini gpt-oss-20b
```
Only these three are used for question generation:
| Role | key | notes |
|---|---|---|
| Optimizer | `mistral-small-3.1` | 24B — loads 4-bit by default (`OptimizerAgent(load_in_4bit=True)`) |
| Evaluator | `phi-4-mini` | small, fast |
| Scorer | `gpt-oss-20b` | harmony chat format (tokenizer handles it) |

Accept the Mistral license on its HF page with the token's account first (gated).

## 3. PubMed MCP server (once)
```bash
cd Version_3/Benchmark_A/PubMed-MCP-Server
npm install && npm run build
# optional, raises NCBI rate limit 3->10/s:
export NCBI_API_KEY=... NCBI_EMAIL=you@inst.edu
```
Verify: `cd ../Question_Gen && python mcp_client.py` should list 16 tools + return a search.

## 4. Smoke tests (no GPU)
```bash
cd Version_3/Benchmark_A/Question_Gen
python -m py_compile *.py
python -c "import schema; schema.validate(schema.EXAMPLE); print('schema OK')"
python orchestrator.py --dry-run --n 5 --types next_procedure mortality_1y
#   -> writes outputs/questions.jsonl + MCP_Server/supplementals/*.json, NO models/network
```
The dry run exercises the full loop (context -> synthesize -> validate -> persist ->
bundle export). If it writes N valid records, the plumbing is sound.

## 5. The real generation run (GPU)
```bash
cd Version_3/Benchmark_A/Question_Gen
# pilot first — 20 questions, all types:
python orchestrator.py --n 20
# full run:
python orchestrator.py --n 500 --types next_procedure readmission_30d mortality_1y deterioration
```
Per item: context -> (procedure/mortality: agentic PubMed citation) -> Optimizer draft ->
Evaluator critique -> refine (<=3 rounds, else discard) -> Scorer rubric -> validate ->
append to `outputs/questions.jsonl` + write `MCP_Server/supplementals/<question_id>.json`.

**Outputs**
- `Question_Gen/outputs/questions.jsonl` — one finalized question + answer key + rubric per line.
- `MCP_Server/supplementals/<question_id>.json` — pre-t0 bundle the server serves (no answer).

Resume/scale: the run is a plain loop; re-run with a larger `--n` (it overwrites
`questions.jsonl`, so copy it aside between runs, or bump `out_name` in `run()`).

## 6. Serving questions to answering agents
```bash
cd Version_3/Benchmark_A/MCP_Server
SUPPLEMENTALS_DIR=$PWD/supplementals python server.py       # stdio MCP
```
Tools the answering agent sees:
- `Access_All_supplementals_no_values(question_id)` — item names/dates, NO values (the gate).
- `Request_a_supplemental(question_id, category, item_name)` — values, gated behind the access call.

The answering agent is scored later with each question's `scorer.rubric`
(per-request 0/0.5/1 justification + **+1 per golden item** + MC correctness + causal chain).

## 7. Scaling to full MIMIC-IV
`context_builder.py` reads the demo CSVs directly. For full MIMIC-IV:
- The one-time **eligibility scan** (`iter_eligible`) is the bottleneck (~3 min on the
  demo because it materializes each candidate context). For full data, cache an
  eligibility index to parquet once and sample from it — mirror Version_2's
  `qgen/cohort.py` (`eligible_index.parquet` + materialized lab/micro slices), then
  point `MimicDemo` at the slices instead of the raw CSVs. The context CONTRACT and
  everything downstream stay unchanged.

## 8. Known limitations / watch-outs
- **Demo timestamps** are date-level for many labs (00:00:00), so a few before/after
  splits are coarse. Full MIMIC-IV has real charttimes.
- **No ED-triage vitals** in the demo — `vitals_exam` = ICU chartevents + outpatient OMR only.
- **PubMed placeholder PMIDs** appear only in `--dry-run`; the real run attaches
  verified PMIDs via the agentic loop. If NCBI is unreachable, procedure/mortality
  drafts will fail the `citation_present` check and be discarded — check connectivity.
- **Optimizer JSON discipline**: generation depends on the model emitting strict JSON;
  `orchestrator.extract_json` tolerates prose/`<think>` but a model that never emits a
  balanced object yields a discard, not a crash.
```
