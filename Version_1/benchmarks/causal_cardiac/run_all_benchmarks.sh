#!/bin/bash
# Full pipeline: generate cases → evaluate with Qwen via Ollama

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "Causal Cardiac Benchmarks - Full Pipeline"
echo "========================================"

echo ""
echo "[1/3] Preparing Benchmark A: Intervention → Physiological Effect"
python3 prep_intervention_attribution.py

echo ""
echo "[2/3] Summary of generated cases:"
ls -lh questions/ | tail -5
echo "... (see questions/ for all cases)"

echo ""
echo "[3/3] Running evaluation with Qwen 3.6 via Ollama..."
echo "This will test Benchmark A with and without PubMed access."
echo ""

# Check if Ollama is reachable
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
  echo "ERROR: Ollama not reachable at http://localhost:11434"
  echo "Please ensure Ollama is running and qwen3.6 is pulled:"
  echo "  ollama pull qwen3.6"
  echo "  ollama serve"
  exit 1
fi

node run_causal_evaluation.mjs

echo ""
echo "========================================"
echo "Complete! Results in results/"
echo "========================================"
