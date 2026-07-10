#!/bin/bash
# Launch the two local vLLM servers (optimizer + evaluator) from qgen.yaml on the PUBLIC gpu partition.
# NOTE: -G / tensor-parallel sizing must match models.{optimizer,evaluator}.tensor_parallel_size in
# qgen.yaml. Adjust the GPU count below once model sizes are finalized (see plan "open items").
#SBATCH -p gpu
#SBATCH -C "GPU_MEM:80GB|GPU_MEM:141GB"
#SBATCH -G 5                       # e.g. 4 for Mixtral-8x22B (TP=4) + 1 for DeepSeek-R1-32B
#SBATCH -c 16
#SBATCH --mem=128GB
#SBATCH -t 12:00:00
#SBATCH -J qgen_serve
#SBATCH -o /scratch/users/karun09/Version_2/Benchmark_C/Question_Generation/outputs/serve.%j.out
#SBATCH -e /scratch/users/karun09/Version_2/Benchmark_C/Question_Generation/outputs/serve.%j.out

set -eo pipefail
QG=/scratch/users/karun09/Version_2/Benchmark_C/Question_Generation
export PYTHONPATH=$QG
PY=/scratch/users/karun09/miniforge3/envs/simr/bin/python   # must have vllm installed
export HF_HOME=$SCRATCH/.huggingface HF_HUB_CACHE=$SCRATCH/.huggingface/hub
export TRANSFORMERS_CACHE=$SCRATCH/.huggingface/transformers
mkdir -p "$HF_HOME" "$HF_HUB_CACHE" "$TRANSFORMERS_CACHE"

cd "$QG"
OPT_CMD=$($PY -m qgen.serve_cmd optimizer)
EVAL_CMD=$($PY -m qgen.serve_cmd evaluator)
echo "OPTIMIZER: $OPT_CMD"
echo "EVALUATOR: $EVAL_CMD"

# CUDA_VISIBLE_DEVICES split: first N GPUs to optimizer (TP), remainder to evaluator.
# (Edit the split to match tensor_parallel_size values.)
CUDA_VISIBLE_DEVICES=0,1,2,3 $OPT_CMD &
CUDA_VISIBLE_DEVICES=4       $EVAL_CMD &

# record endpoints for the orchestrator (host:port from config)
$PY - <<'PYEOF'
import json, socket
from qgen.config import load_config
cfg = load_config()
host = socket.gethostname()
eps = {r: {"host": host, "endpoint": cfg["models"][r]["endpoint"], "model_id": cfg["models"][r]["model_id"]}
       for r in cfg["models"]}
open(cfg["data"]["out_dir"] + "/endpoints.json", "w").write(json.dumps(eps, indent=2))
print("wrote endpoints.json:", eps)
PYEOF

wait
