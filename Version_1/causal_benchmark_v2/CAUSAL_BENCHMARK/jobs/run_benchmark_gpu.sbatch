#!/bin/bash
#SBATCH -p gpu
#SBATCH --gres=gpu:1
#SBATCH -t 02:00:00
#SBATCH --mem=32GB
#SBATCH -c 8
#SBATCH -J causal_benchmark
#SBATCH -o benchmark_%j.log
#SBATCH -e benchmark_%j.err

set -euo pipefail

echo "=== Starting Causal Benchmark ==="
echo "Job ID: $SLURM_JOB_ID"
echo "Date: $(date)"

# Load required modules
echo "Loading modules..."
ml purge
ml load math py-pytorch/2.9.1_py314
ml load math py-transformers/4.57.3_py314

# Verify CUDA
echo "CUDA check:"
python3 -c "import torch; print(f'PyTorch version: {torch.__version__}'); print(f'CUDA available: {torch.cuda.is_available()}'); print(f'GPU device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"None\"}')"

# Set environment variables for caching
export HF_HOME=$SCRATCH/.huggingface
export TRANSFORMERS_CACHE=$SCRATCH/.huggingface/transformers
export TORCH_HOME=$SCRATCH/.torch

mkdir -p $HF_HOME $TRANSFORMERS_CACHE $TORCH_HOME

# Change to benchmark directory
cd /scratch/users/karun09/CAUSAL_BENCHMARK

echo ""
echo "=== Running Causal Benchmark ==="
echo "Models configured in: scripts/run_question_benchmark.py"
echo ""

# Run the benchmark
python3 scripts/run_benchmark.py

echo ""
echo "=== Benchmark Complete ==="
echo "Results saved to: outputs/"
echo "Check outputs/RESULTS.md for summary"
echo ""

# Display results
if [ -f outputs/RESULTS.md ]; then
    echo "=== Results Summary ==="
    cat outputs/RESULTS.md
fi

echo "Job completed at: $(date)"
