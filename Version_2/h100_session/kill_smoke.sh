#!/bin/bash
# Kill the running smoke (run_generate + smoke_gptoss) by PID — script file avoids pkill -f self-match.
for p in $(pgrep -f "qgen.run_generate" 2>/dev/null); do kill "$p" 2>/dev/null && echo "TERM run_generate $p"; done
for p in $(pgrep -f "smoke_gptoss.sh" 2>/dev/null); do kill "$p" 2>/dev/null && echo "TERM smoke $p"; done
sleep 2
pgrep -f "qgen.run_generate" >/dev/null 2>&1 && { for p in $(pgrep -f "qgen.run_generate"); do kill -9 "$p" 2>/dev/null; done; }
echo "smoke stopped"
