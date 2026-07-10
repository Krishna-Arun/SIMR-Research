#!/bin/bash
#SBATCH -p dev
#SBATCH -t 00:30:00
#SBATCH --mem=16GB
#SBATCH -c 4
#SBATCH -J causal_bench_cpu
#SBATCH -o benchmark_cpu_%j.log
#SBATCH -e benchmark_cpu_%j.err

set -euo pipefail

echo "=== Starting Causal Benchmark (CPU Mode - Quick Test) ==="
echo "Job ID: $SLURM_JOB_ID"
echo "Date: $(date)"

# Load required modules
echo "Loading modules..."
ml load math py-pytorch/2.4.1_py312
ml load math py-transformers/4.57.3_py314

# Verify Python environment
echo "Python check:"
python3 --version
python3 -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA: {torch.cuda.is_available()}')"

# Set environment variables for caching
export HF_HOME=$SCRATCH/.huggingface
export TRANSFORMERS_CACHE=$SCRATCH/.huggingface/transformers
export TORCH_HOME=$SCRATCH/.torch

mkdir -p $HF_HOME $TRANSFORMERS_CACHE $TORCH_HOME

# Change to benchmark directory
cd /scratch/users/karun09/CAUSAL_BENCHMARK

echo ""
echo "=== Running Causal Benchmark (CPU) ==="
echo "Note: CPU mode is slower but good for quick testing"
echo ""

# Run with smaller models for quick test
python3 scripts/run_question_benchmark.py

echo ""
echo "=== Benchmark Complete ==="
echo "Results saved to: outputs/"
echo ""

if [ -f outputs/RESULTS.md ]; then
    echo "=== Results Summary ==="
    cat outputs/RESULTS.md
fi

echo "Completed at: $(date)"
