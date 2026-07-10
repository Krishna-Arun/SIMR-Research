#!/bin/bash
#SBATCH -p gpu
#SBATCH -C "GPU_MEM:24GB|GPU_MEM:32GB|GPU_MEM:48GB|GPU_MEM:80GB"
#SBATCH -G 1
#SBATCH -c 4
#SBATCH --mem=32GB
#SBATCH -t 03:00:00
#SBATCH -J cardiac_cf_gpu
#SBATCH -o logs/gpu_%j.log
#SBATCH -e logs/gpu_%j.err

# Real-LLM 3-arm inference (public gpu partition; single-GPU fp16) + scoring.
# SMOKE: prepend CAUSAL_MAX_EPISODES=8 CAUSAL_MODELS=Qwen/Qwen3-8B.
set -euo pipefail
cd /scratch/users/karun09/CARDIAC_COUNTERFACTUAL
mkdir -p logs

ml purge
ml load math py-pytorch/2.9.1_py314 py-transformers/4.57.3_py314
export HF_HOME=$SCRATCH/.huggingface HF_HUB_CACHE=$SCRATCH/.huggingface/hub
export TRANSFORMERS_CACHE=$SCRATCH/.huggingface/transformers TORCH_HOME=$SCRATCH/.torch
export TOKENIZERS_PARALLELISM=false
mkdir -p "$HF_HOME" "$HF_HUB_CACHE" "$TRANSFORMERS_CACHE" "$TORCH_HOME"

echo "=== cardiac-CF GPU · job $SLURM_JOB_ID on $(hostname) · $(date) ==="
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true
export CAUSAL_MODELS="${CAUSAL_MODELS:-Qwen/Qwen3-8B,mistralai/Mistral-7B-Instruct-v0.3,deepseek-ai/DeepSeek-R1-Distill-Qwen-7B}"
export CAUSAL_PROMPTS="${CAUSAL_PROMPTS:-zero_shot,cot}"
export CAUSAL_TIME_BUDGET_S="${CAUSAL_TIME_BUDGET_S:-9600}"
python3 -u scripts/run_taskC_multiarm.py || true

echo "=== Scoring ==="
ml purge; ml load math py-scikit-learn/1.3.2_py39 py-pandas/2.0.1_py39
python3 -u scripts/score_taskC_multiarm.py || true
echo "=== Done $(date) ==="
if [ ! -f outputs/TASKC_MULTIARM_COMPLETE ]; then
  n=$(cat .resume 2>/dev/null || echo 0); n=$((n+1)); echo "$n" > .resume
  [ "$n" -le 15 ] && { echo "resubmitting ($n/15)"; sbatch jobs/run_gpu.sbatch; } || echo "max resumes reached"
else
  rm -f .resume; sed -n '1,60p' outputs/TASKC_MULTIARM_RESULTS.md 2>/dev/null || true
fi
