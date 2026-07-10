#!/bin/bash
#SBATCH -p gpu
#SBATCH -C GPU_SKU:H100_SXM5
#SBATCH -G 1
#SBATCH -c 16
#SBATCH --mem=128GB
#SBATCH -t 1-00:00:00
#SBATCH -J h100_qgen
#SBATCH -o /scratch/users/karun09/Version_2/h100_session/h100.%j.out
#SBATCH -e /scratch/users/karun09/Version_2/h100_session/h100.%j.out
bash /scratch/users/karun09/Version_2/h100_session/run_h100.sh
