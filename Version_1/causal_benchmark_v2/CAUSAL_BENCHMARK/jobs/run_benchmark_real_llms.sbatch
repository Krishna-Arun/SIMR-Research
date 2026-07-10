#!/bin/bash
#SBATCH -p gpu
#SBATCH --gres=gpu:1
#SBATCH -t 02:00:00
#SBATCH --mem=32GB
#SBATCH -c 8
#SBATCH -J real_llms_bench
#SBATCH -o benchmark_real_%j.log
#SBATCH -e benchmark_real_%j.err

set -euo pipefail

echo "=== Starting Real LLM Benchmark ==="
echo "Job ID: $SLURM_JOB_ID"
echo "Date: $(date)"

# Load required modules
echo "Loading modules..."
ml purge
ml load math py-pytorch/2.9.1_py314
ml load math py-transformers/4.57.3_py314

# Verify CUDA
echo "CUDA check:"
python3 -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA available: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0)}')"

# Set cache directories
export HF_HOME=$SCRATCH/.huggingface
export TRANSFORMERS_CACHE=$SCRATCH/.huggingface/transformers
export TORCH_HOME=$SCRATCH/.torch
mkdir -p $HF_HOME $TRANSFORMERS_CACHE $TORCH_HOME

# Change to benchmark directory
cd /scratch/users/karun09/CAUSAL_BENCHMARK

echo ""
echo "=== Running Real LLM Benchmark ==="
echo "Models: Qwen2-1.5B-Instruct, Phi-2"
echo "Data: 50 real MIMIC-IV episodes + 30 matched pairs"
echo ""

# Run with unbuffered output
python3 -u scripts/run_benchmark.py 2>&1

echo ""
echo "=== Benchmark Complete ==="
if [ -f outputs/RESULTS.md ]; then
    echo "Results:"
    cat outputs/RESULTS.md
fi

echo "Job completed at: $(date)"
