#!/bin/bash
#SBATCH -p gpu
#SBATCH --gpus=1
#SBATCH -C GPU_MEM:16GB
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=32GB
#SBATCH -J causal_benchmark
#SBATCH -o logs/benchmark_%j.log
#SBATCH -e logs/benchmark_%j.err

# Create logs directory
mkdir -p logs

# Load modules
module load system
module load cudatoolkit/12.0
module load python/3.11

# Install dependencies (first time only)
pip install --user -q numpy pandas scipy transformers torch

# Run benchmark with Qwen, DeepSeek, Gemma
cd /scratch/users/karun09/CAUSAL_BENCHMARK

python3 << 'EOF'
import sys
sys.path.insert(0, '/scratch/users/karun09/CAUSAL_BENCHMARK/scripts')
sys.path.insert(0, '/scratch/users/karun09/CAUSAL_BENCHMARK/models')

# Modify the benchmark runner to use these models
import json
from pathlib import Path

# Read the benchmark runner
runner_path = Path('/scratch/users/karun09/CAUSAL_BENCHMARK/scripts/run_question_benchmark.py')
runner_code = runner_path.read_text()

# Replace MODELS_TO_TEST
old_models = '''MODELS_TO_TEST = [
    # Open-source models via Hugging Face
    ("Qwen/Qwen2-7B-Instruct", "huggingface"),
    ("deepseek-ai/deepseek-llm-7b-chat", "huggingface"),
    ("meta-llama/Llama-2-7b-chat-hf", "huggingface"),
    ("mistralai/Mistral-7B-Instruct-v0.1", "huggingface"),

    # Uncomment to use:
    # ("microsoft/phi-2", "huggingface"),
    # ("ollama/qwen", "ollama"),
    # ("mock", "mock"),
]'''

new_models = '''MODELS_TO_TEST = [
    ("Qwen/Qwen2-7B-Instruct", "huggingface"),
    ("deepseek-ai/deepseek-llm-7b-chat", "huggingface"),
    ("google/gemma-7b-it", "huggingface"),
]'''

runner_code = runner_code.replace(old_models, new_models)

# Write back
runner_path.write_text(runner_code)
print("✓ Updated MODELS_TO_TEST")

EOF

# Run the benchmark
python3 scripts/run_question_benchmark.py

echo ""
echo "=========================================="
echo "Benchmark complete!"
echo "Check results:"
echo "  cat outputs/RESULTS.md"
echo "=========================================="
