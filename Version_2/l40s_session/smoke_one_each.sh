#!/bin/bash
export HF_HOME=$SCRATCH/.huggingface HF_HUB_CACHE=$SCRATCH/.huggingface/hub PYTHONUNBUFFERED=1
PY=/scratch/users/karun09/miniforge3/envs/simr/bin/python
for b in A B C; do
  D=/scratch/users/karun09/Version_2/Benchmark_$b/Question_Generation
  echo "=================== BENCHMARK $b  start $(date +%T) ==================="
  cd $D
  $PY -m qgen.run_generate config/qgen_pilot.yaml --target 1
  echo "=================== BENCHMARK $b  done $(date +%T)  accepted=$(wc -l < outputs/questions.jsonl 2>/dev/null||echo 0) ==================="
done
echo "ALL SMOKE DONE $(date +%T)"
