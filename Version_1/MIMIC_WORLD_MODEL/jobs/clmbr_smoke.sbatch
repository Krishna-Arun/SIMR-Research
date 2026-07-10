#!/bin/bash
#SBATCH --job-name=clmbr_smoke
#SBATCH --partition=gpu
#SBATCH --gpus=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32GB
#SBATCH --time=01:30:00
#SBATCH --output=/scratch/users/karun09/MIMIC_WORLD_MODEL/logs/clmbr_smoke_%j.out
#SBATCH --error=/scratch/users/karun09/MIMIC_WORLD_MODEL/logs/clmbr_smoke_%j.out

# Stage 0: validate the official frozen CLMBR (StanfordShahLab/clmbr-t-base) loads + runs via femr.
# Public GPU partition only (never roxanad). All install/cache on $SCRATCH (never $HOME).
set -euo pipefail

PROJ=/scratch/users/karun09/MIMIC_WORLD_MODEL
VENV=$SCRATCH/MIMIC_WORLD_MODEL/envs/clmbr39

# Caches -> $SCRATCH (keep $HOME's 15GB clear)
export PIP_CACHE_DIR=$SCRATCH/.cache/pip
export XDG_CACHE_HOME=$SCRATCH/.cache
export HF_HOME=$SCRATCH/.cache/huggingface
export HF_HUB_CACHE=$HF_HOME/hub
export TRANSFORMERS_CACHE=$HF_HOME/hub
export TORCH_HOME=$SCRATCH/.cache/torch
mkdir -p "$PIP_CACHE_DIR" "$HF_HUB_CACHE" "$TORCH_HOME" "$PROJ/logs"

echo "=== node: $(hostname) ==="
nvidia-smi || true

ml purge
ml load devel python/3.9.0

# Build the CLMBR venv once (torch 2.1.2 needs py<=3.11; the notebook's cell 1 installs the
# pinned ML stack into this venv).
if [ ! -x "$VENV/bin/python" ]; then
  echo "=== creating venv $VENV ==="
  python -m venv "$VENV"
  "$VENV/bin/python" -m pip install --upgrade pip wheel setuptools
  "$VENV/bin/python" -m pip install "jupyter" "nbconvert" "ipykernel"
fi
source "$VENV/bin/activate"
python --version
which python

cd "$PROJ"
echo "=== executing notebook (pip install happens in cell 1) ==="
jupyter nbconvert --to notebook --execute --inplace \
  --ExecutePreprocessor.timeout=3600 \
  --ExecutePreprocessor.kernel_name=python3 \
  notebooks/clmbr_smoke.ipynb

echo "=== done; rendering executed outputs to text ==="
jupyter nbconvert --to script --stdout notebooks/clmbr_smoke.ipynb || true
echo "=== STAGE0_OK ==="
