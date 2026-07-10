#!/bin/bash
#SBATCH -p gpu
#SBATCH -C GPU_SKU:H100_SXM5
#SBATCH -N 1
#SBATCH -G 3
#SBATCH -c 32
#SBATCH --mem=256GB
#SBATCH -t 1-00:00:00
#SBATCH -J qgen_h100x4
#SBATCH -o /scratch/users/karun09/Version_2/h100_session/h100x4.%j.out
#SBATCH -e /scratch/users/karun09/Version_2/h100_session/h100x4.%j.out
set -eo pipefail
echo "===== 4x H100 on $(hostname) at $(date) ====="
nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader
echo "node=$(hostname) jobid=$SLURM_JOB_ID started=$(date)" > /scratch/users/karun09/Version_2/h100_session/H100_READY
# 32B+32B optimizer/evaluator (qgen.yaml). Smoke 10/benchmark, then full 500/benchmark.
bash /scratch/users/karun09/Version_2/l40s_session/smoke_l40s.sh 10
bash /scratch/users/karun09/Version_2/l40s_session/run_l40s.sh 500
