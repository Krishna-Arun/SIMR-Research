#!/bin/bash
#SBATCH --job-name=cfa_preprocess
#SBATCH --partition=normal
#SBATCH --cpus-per-task=4
#SBATCH --mem=16GB
#SBATCH --time=00:20:00
#SBATCH --output=/scratch/users/karun09/Counterfactual_Algorithm/logs/preprocess_%j.out
#SBATCH --error=/scratch/users/karun09/Counterfactual_Algorithm/logs/preprocess_%j.out

# Stage 1: build per-patient trajectories from the MIMIC-IV demo (CPU). Output to $SCRATCH.
set -euo pipefail

PROJ=/scratch/users/karun09/Counterfactual_Algorithm
VENV=$SCRATCH/Counterfactual_Algorithm/envs/cfa_cpu
export PIP_CACHE_DIR=$SCRATCH/.cache/pip
export PYTHONPATH=$PROJ
mkdir -p "$PIP_CACHE_DIR" "$PROJ/logs" "$PROJ/data"

ml purge
ml load devel python/3.9.0

# Lightweight CPU venv (no torch) — fast to build, independent of the GPU/CLMBR env.
if [ ! -x "$VENV/bin/python" ]; then
  echo "=== creating CPU venv $VENV ==="
  python3 -m venv "$VENV"
  "$VENV/bin/python" -m pip install --upgrade pip wheel
  "$VENV/bin/python" -m pip install "numpy<2" "pandas==2.0.3" "pyyaml"
fi
source "$VENV/bin/activate"
python --version

cd "$PROJ"
python preprocessing/build_trajectories.py configs/default.yaml
echo "=== STAGE1_DONE ==="
