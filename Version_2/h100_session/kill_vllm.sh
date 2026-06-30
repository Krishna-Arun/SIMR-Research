#!/bin/bash
# Kill the gpt-oss vLLM server by PID (in a script file so the pattern isn't in an interactive
# command line -> avoids pkill -f self-match).
PAT="vllm serve openai/gpt-oss"
for p in $(pgrep -f "$PAT" 2>/dev/null); do kill "$p" 2>/dev/null && echo "TERM $p"; done
sleep 3
for p in $(pgrep -f "$PAT" 2>/dev/null); do kill -9 "$p" 2>/dev/null && echo "KILL $p"; done
sleep 1
pgrep -f "$PAT" >/dev/null 2>&1 && echo "STILL ALIVE" || echo "stopped"
