#!/bin/bash
while true; do
  clear
  echo "=== Causal Cardiac Benchmark Evaluation Progress ==="
  echo "Time: $(date)"
  echo ""
  
  if [ -f evaluation.log ]; then
    echo "Latest log lines:"
    tail -10 evaluation.log
    echo ""
    
    # Count completed cases
    a_with=$(grep -c "✓ Case a_" evaluation.log 2>/dev/null || echo 0)
    a_without=$(grep -c "Case a_" evaluation.log | tail -1 2>/dev/null || echo 0)
    
    echo "Progress: $a_with cases processed so far"
  fi
  
  # Check if process is still running
  if ! pgrep -f "node run_causal_evaluation" > /dev/null; then
    echo ""
    echo "✅ Evaluation process completed!"
    break
  fi
  
  sleep 60
done
