#!/bin/bash
#SBATCH -p gpu
#SBATCH -C "GPU_MEM:24GB|GPU_MEM:32GB|GPU_MEM:48GB|GPU_MEM:80GB"
#SBATCH -G 1
#SBATCH -c 4
#SBATCH --mem=32GB
#SBATCH -t 03:00:00
#SBATCH -J taskC_gpu
#SBATCH -o logs/taskC_gpu_%j.log
#SBATCH -e logs/taskC_gpu_%j.err

# Task C real-LLM counterfactual inference on the PUBLIC gpu partition (never roxanad).
# Single-GPU fp16 (no device_map; py314 accelerate is broken on this cluster).
# Checkpoints per (model, prompt) and auto-resubmits to resume — same pattern as
# run_frontier_gpu.sbatch. SMOKE: prepend CAUSAL_MAX_EPISODES=8 CAUSAL_MODELS=Qwen/Qwen3-8B.

set -euo pipefail
cd /scratch/users/karun09/CAUSAL_BENCHMARK
mkdir -p logs

ml purge
ml load math
ml load py-pytorch/2.9.1_py314 py-transformers/4.57.3_py314

export HF_HOME=$SCRATCH/.huggingface
export HF_HUB_CACHE=$SCRATCH/.huggingface/hub
export TRANSFORMERS_CACHE=$SCRATCH/.huggingface/transformers
export TORCH_HOME=$SCRATCH/.torch
export TOKENIZERS_PARALLELISM=false
mkdir -p "$HF_HOME" "$HF_HUB_CACHE" "$TRANSFORMERS_CACHE" "$TORCH_HOME"

echo "=== Task C · GPU inference · job $SLURM_JOB_ID on $(hostname) · $(date) ==="
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true
python3 -c "import torch;print('torch',torch.__version__,'cuda',torch.cuda.is_available())"

# Three distinct small instruction models (ungated, fp16 on one 24-32GB GPU). Override w/ env.
export CAUSAL_MODELS="${CAUSAL_MODELS:-Qwen/Qwen3-8B,mistralai/Mistral-7B-Instruct-v0.3,deepseek-ai/DeepSeek-R1-Distill-Qwen-7B}"
export CAUSAL_PROMPTS="${CAUSAL_PROMPTS:-zero_shot,cot}"
export CAUSAL_MAX_NEW_TOKENS_SCALAR="${CAUSAL_MAX_NEW_TOKENS_SCALAR:-512}"
export CAUSAL_TIME_BUDGET_S="${CAUSAL_TIME_BUDGET_S:-9600}"   # checkpoint at ~2h40m

python3 -u scripts/run_taskC.py || true

# Score whatever predictions exist (needs sklearn/pandas -> swap to the py39 math stack).
echo "=== Scoring ==="
ml purge
ml load math py-scikit-learn/1.3.2_py39 py-pandas/2.0.1_py39
python3 -u scripts/score_taskC.py || true

echo "=== Done $(date) ==="
# Auto-resume if inference not complete (resumes from per-config checkpoints).
if [ ! -f outputs/TASKC_ALL_COMPLETE ]; then
  n=$(cat .taskC_resume 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > .taskC_resume
  if [ "$n" -le 15 ]; then
    echo "Not complete — resubmitting (attempt $n/15)"
    sbatch jobs/run_taskC_gpu.sbatch
  else
    echo "Max resume attempts reached — stopping."
  fi
else
  echo "TASKC_ALL_COMPLETE present — finished."; rm -f .taskC_resume
  sed -n '1,80p' outputs/TASKC_RESULTS.md 2>/dev/null || true
fi
