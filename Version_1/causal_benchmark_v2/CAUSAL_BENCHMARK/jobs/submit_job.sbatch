#!/bin/bash
#SBATCH -p gpu
#SBATCH --gpus=1
#SBATCH -C GPU_MEM:16GB
#SBATCH --time=03:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=32GB
#SBATCH -J causal_benchmark

module load cuda/12.0
python3 -m pip install --user -q numpy pandas scipy transformers torch 2>/dev/null

cd /scratch/users/karun09/CAUSAL_BENCHMARK

# Update models to test
python3 << 'PYTHON'
import re
with open('scripts/run_question_benchmark.py', 'r') as f:
    code = f.read()

# Replace MODELS_TO_TEST section
old = '''MODELS_TO_TEST = [
    # Open-source models via Hugging Face
    ("Qwen/Qwen2-7B-Instruct", "huggingface"),
    ("deepseek-ai/deepseek-llm-7b-chat", "huggingface"),
    ("meta-llama/Llama-2-7b-chat-hf", "huggingface"),
    ("mistralai/Mistral-7B-Instruct-v0.1", "huggingface"),'''

new = '''MODELS_TO_TEST = [
    # Open-source models via Hugging Face
    ("Qwen/Qwen2-7B-Instruct", "huggingface"),
    ("deepseek-ai/deepseek-llm-7b-chat", "huggingface"),
    ("mistralai/Mistral-7B-Instruct-v0.1", "huggingface"),'''

code = code.replace(old, new)
with open('scripts/run_question_benchmark.py', 'w') as f:
    f.write(code)
print("✓ Updated to test: Qwen, DeepSeek, Mistral")
PYTHON

python3 scripts/run_question_benchmark.py

echo ""
echo "DONE! Results saved to:"
echo "  /scratch/users/karun09/CAUSAL_BENCHMARK/outputs/RESULTS.md"
