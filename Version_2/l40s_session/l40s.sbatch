#!/bin/bash
#SBATCH -p gpu
#SBATCH -C GPU_SKU:L40S
#SBATCH -G 3
#SBATCH -c 16
#SBATCH --mem=128GB
#SBATCH -t 1-00:00:00
#SBATCH -J qgen_l40s
#SBATCH -o /scratch/users/karun09/Version_2/l40s_session/l40s.%j.out
#SBATCH -e /scratch/users/karun09/Version_2/l40s_session/l40s.%j.out
# Smoke (10/benchmark) then full (500/benchmark). Edit to taste.
bash /scratch/users/karun09/Version_2/l40s_session/smoke_l40s.sh 10
bash /scratch/users/karun09/Version_2/l40s_session/run_l40s.sh 500
