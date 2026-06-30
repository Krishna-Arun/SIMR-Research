#!/bin/bash
for pat in "run_all.sh" "eval.run_eval"; do
  for p in $(pgrep -f "$pat" 2>/dev/null); do kill "$p" 2>/dev/null && echo "TERM $p ($pat)"; done
done
sleep 2
for p in $(pgrep -f "eval.run_eval" 2>/dev/null); do kill -9 "$p" 2>/dev/null; done
echo "eval stopped"
