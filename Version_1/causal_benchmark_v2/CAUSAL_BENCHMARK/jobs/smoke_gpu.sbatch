#!/bin/bash
#SBATCH -p gpu
#SBATCH -C GPU_MEM:32GB           # fits the 7B reasoning model in fp16
#SBATCH -G 1
#SBATCH -c 4
#SBATCH --mem=48GB
#SBATCH -t 00:45:00
#SBATCH -J causal_smoke
#SBATCH -o logs/smoke_%j.log
#SBATCH -e logs/smoke_%j.err

set -euo pipefail
mkdir -p logs
echo "Job $SLURM_JOB_ID on $(hostname) — $(date)"
ml purge
ml load math
ml load py-pytorch/2.9.1_py314 py-transformers/4.57.3_py314
export HF_HOME=$SCRATCH/.huggingface
export HF_HUB_CACHE=$SCRATCH/.huggingface/hub
export TRANSFORMERS_CACHE=$SCRATCH/.huggingface/transformers
export TOKENIZERS_PARALLELISM=false
mkdir -p "$HF_HOME" "$HF_HUB_CACHE" "$TRANSFORMERS_CACHE"
python3 -c "import torch;print('cuda',torch.cuda.is_available(),torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"

cd /scratch/users/karun09/CAUSAL_BENCHMARK
# Validate the NEW code paths on real models: multi-marker prompt + per-marker JSON parse
# + logit-based direction confidence. Fast model first, then a reasoning model.
export CAUSAL_MODELS="Qwen/Qwen2.5-0.5B-Instruct,deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
export CAUSAL_PROMPTS="zero_shot"
export CAUSAL_MAX_EPISODES=8
export CAUSAL_MAX_NEW_TOKENS=768
python3 -u scripts/run_benchmark.py

echo "=== post-run: confirm logit confidence populated ==="
python3 - <<'PY'
import json, glob, os
for f in sorted(glob.glob("answers/*_zero_shot_responses.json"), key=os.path.getmtime)[-2:]:
    d=json.load(open(f)); resp=d.get("responses",{})
    n=len(resp)
    conf=[r.get("confidence") for r in resp.values() if r.get("confidence")]
    sample = conf[0] if conf else None
    mk = set()
    for r in resp.values():
        mk |= set((r.get("trajectories") or {}).keys())
    print(f"{d['model']}: {n} responses | logit-confidence populated: {len(conf)}/{n} | markers predicted: {sorted(mk)}")
    print(f"   sample confidence: {sample}")
PY
echo "=== done $(date) ==="
