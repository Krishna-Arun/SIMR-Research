#!/bin/bash
#SBATCH -J reencode_clmbr
#SBATCH -p gpu
#SBATCH -G 1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64GB
#SBATCH --time=01:30:00
#SBATCH -o /scratch/users/karun09/Version_2/counterfactual_simulation/logs/reencode_%j.out
#SBATCH -e /scratch/users/karun09/Version_2/counterfactual_simulation/logs/reencode_%j.err

set -euo pipefail
CA=/scratch/users/karun09/Version_1/Counterfactual_Algorithm
CS=/scratch/users/karun09/Version_2/counterfactual_simulation

export HF_TOKEN="$(tr -d ' \n\r' < "$CS/.hf_token")"
export HF_HOME=/scratch/users/karun09/.huggingface
export HF_HUB_OFFLINE=1            # clmbr-t-base is cached
export TOKENIZERS_PARALLELISM=false

cd "$CA"
echo "host: $(hostname)  gpu: ${CUDA_VISIBLE_DEVICES:-none}  start: $(date)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true

# Re-encode with the patched reassemble() that also saves abs_times.
# Deterministic frozen CLMBR -> identical s/action_ids/hours, PLUS absolute feature times.
"$CA/envs/clmbr311/bin/python" models/encode_clmbr.py configs/default.yaml

echo "done: $(date)"
