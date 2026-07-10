#!/bin/bash
#SBATCH -p gpu
#SBATCH --gpus=1
#SBATCH --time=00:30:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=16GB

module load cuda/12.0
python3 -m pip install -q numpy pandas scipy transformers torch 2>/dev/null

cd /scratch/users/karun09/CAUSAL_BENCHMARK
python3 scripts/run_question_benchmark.py
