#!/bin/bash

# run_benchmark.sh
# Full pipeline execution script

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "======================================"
echo "Causal Intervention Benchmark"
echo "======================================"
echo ""

# Step 1: Extract episodes
echo "[1/4] Extracting episodes from EHRSHOT..."
cd "$SCRIPT_DIR/scripts"
python extract_episodes.py
echo "✓ Episodes extracted"
echo ""

# Step 2: Encode features
echo "[2/4] Encoding confounding features..."
python encode_features.py
echo "✓ Features encoded"
echo ""

# Step 3: Construct matched pairs
echo "[3/4] Constructing matched pairs..."
python construct_matched_pairs.py
echo "✓ Matched pairs constructed"
echo ""

# Step 4: Run benchmark
echo "[4/4] Running benchmark with LLMs..."
cd "$SCRIPT_DIR/eval"
python benchmark_runner.py
echo "✓ Benchmark complete"
echo ""

echo "======================================"
echo "Benchmark Results"
echo "======================================"
echo ""
echo "Results saved to: $SCRIPT_DIR/output/"
echo ""
echo "View results:"
echo "  cat $SCRIPT_DIR/output/RESULTS.md"
echo ""
