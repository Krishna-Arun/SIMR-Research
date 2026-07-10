# CLMBR — counterfactual_simulation

Uses `StanfordShahLab/clmbr-t-base` as a frozen 768-d patient-state encoder
via the `femr` library.

## Quick start

### 1. Fill in your HuggingFace token

Edit `.env`:
```
HF_TOKEN=hf_YOUR_TOKEN_HERE
```

> The model is **gated**. Accept the license at
> https://huggingface.co/StanfordShahLab/clmbr-t-base with your HF account
> before running the download.

### 2. Download the model weights

```bash
sbatch jobs/download_clmbr.sbatch
# or on an interactive node:
source .env && export HF_TOKEN HF_HOME
python scripts/verify_clmbr.py   # after download finishes
```

### 3. Verify the model loads

```bash
source .env
$SCRATCH/Counterfactual_Algorithm/envs/clmbr311/bin/python scripts/verify_clmbr.py
```

Expected output: `clmbr-t-base OK` with hidden_size=768.

## Environment

Uses the existing `clmbr311` venv at
`$SCRATCH/Counterfactual_Algorithm/envs/clmbr311` (femr 0.2.3, torch 2.1.2,
Python 3.11 via uv). See that project's README for env rebuild steps.

## Notes

- Model cache goes to `$HF_HOME` (set in `.env` → `$SCRATCH/.cache/huggingface`)
  to avoid filling `$HOME`'s 15 GB quota.
- `.env` and `data/` are git-ignored — never commit your token.
- Athena OMOP vocabulary (`data/athena/CONCEPT.csv`) is required for real
  encoding. Download from https://athena.ohdsi.org (SNOMED, LOINC, RxNorm,
  ICD9/10, CPT4, NDC, ATC).
