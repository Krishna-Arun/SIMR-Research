#!/bin/bash
#SBATCH --job-name=simr-grpo
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1                 # H100 or L40S
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=12:00:00
#SBATCH --output=grpo_%j.log
# GRPO fine-tune an open LLM on the SIMR longitudinal benchmark (reward = rubric),
# with the simulate() CF-sim tool available. Step 5 of the SIMR plan (cluster).
#
# Prereqs on the cluster:
#   pip install "trl>=0.9" transformers accelerate datasets peft
#   - a trained world-model checkpoint:  export CFSIM_CKPT=/path/to/worldmodel.pt
#   - the 100-patient question set generated on the dev box, copied to Longitudinal/outputs/
#
# Output: a GRPO-fine-tuned model dir; set GRPO_CKPT to it for the +sim(GRPO) ablation arm.

set -euo pipefail
cd "$(dirname "$0")"

MODEL="${MODEL:-Qwen/Qwen3-8B}"        # test subject to fine-tune (Qwen3-8B / Llama-3.1-8B / gemma)
OUT="${OUT:-runs/grpo_$(date +%s)}"

python3 train_grpo.py \
  --model "$MODEL" \
  --epochs "${EPOCHS:-2}" \
  --output_dir "$OUT"

echo "GRPO done -> $OUT   (use GRPO_CKPT=$OUT for the +sim(GRPO) ablation arm)"
