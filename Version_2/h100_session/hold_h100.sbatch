#!/bin/bash
#SBATCH -p gpu
#SBATCH -C GPU_SKU:H100_SXM5
#SBATCH -G 1
#SBATCH -c 16
#SBATCH --mem=128GB
#SBATCH -t 08:00:00
#SBATCH -J h100_qgen
#SBATCH -o /scratch/users/karun09/Version_2/h100_session/h100.%j.out
#SBATCH -e /scratch/users/karun09/Version_2/h100_session/h100.%j.out

set -eo pipefail
S=/scratch/users/karun09/Version_2/h100_session
export HF_HOME=$SCRATCH/.huggingface HF_HUB_CACHE=$SCRATCH/.huggingface/hub
echo "H100 ALLOCATED on $(hostname) at $(date)"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
# signal readiness for the user (node + jobid) so they can srun into this allocation
echo "node=$(hostname) jobid=$SLURM_JOB_ID started=$(date)" > "$S/H100_READY"
echo "Allocation held for 8h. To use it:  srun --jobid=$SLURM_JOB_ID --pty bash"
# keep the allocation alive for the full walltime
sleep 8h
