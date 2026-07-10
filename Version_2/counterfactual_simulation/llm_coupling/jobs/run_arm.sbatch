#!/bin/bash
#SBATCH -p gpu
#SBATCH -G 1
#SBATCH -C GPU_MEM:24GB
#SBATCH -c 4
#SBATCH --mem=64G
#SBATCH -t 04:00:00
#SBATCH -J cf_arm
#SBATCH -o /scratch/users/karun09/Version_2/counterfactual_simulation/llm_coupling/logs/%x_%j.out
#SBATCH -e /scratch/users/karun09/Version_2/counterfactual_simulation/llm_coupling/logs/%x_%j.out
# Usage: sbatch run_arm.sbatch <arm> <model> [extra args...]
set -euo pipefail
ARM="${1:?arm}"; MODEL="${2:?model}"; shift 2 || true
export HF_HOME=/scratch/users/karun09/.huggingface
export PYTHONUNBUFFERED=1 TOKENIZERS_PARALLELISM=false
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
cd /scratch/users/karun09/Version_2/counterfactual_simulation/llm_coupling
echo "host=$(hostname) arm=$ARM model=$MODEL gpu=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader)"
/scratch/users/karun09/miniforge3/envs/simr/bin/python run_arm.py --arm "$ARM" --model "$MODEL" "$@"
echo "DONE arm=$ARM model=$MODEL"
