#!/bin/bash
for p in $(pgrep -f "ollama serve" 2>/dev/null); do kill "$p" 2>/dev/null && echo "TERM $p"; done
sleep 2
for p in $(pgrep -f "ollama serve" 2>/dev/null); do kill -9 "$p" 2>/dev/null; done
echo "ollama stopped"
