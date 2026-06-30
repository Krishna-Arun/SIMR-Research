#!/bin/bash
# GPU Ollama via the official container (the cluster module is CPU-only). Models come from the Oak cache.
H=/scratch/users/karun09/Version_2/h100_session
SB=/lscratch/karun09/ollama_sb
export APPTAINER_CACHEDIR=$SCRATCH/.apptainer/cache APPTAINER_TMPDIR=/lscratch/karun09/aptmp
setsid apptainer exec --nv --bind /scratch,/oak \
  --env OLLAMA_MODELS=/scratch/users/karun09/.ollama/models \
  --env OLLAMA_HOST=127.0.0.1:11434 \
  --env OLLAMA_FLASH_ATTENTION=1 \
  --env OLLAMA_KEEP_ALIVE=30m \
  --env OLLAMA_MAX_LOADED_MODELS=1 \
  --env OLLAMA_NUM_PARALLEL=6 \
  "$SB" ollama serve > "$H/ollama.log" 2>&1 &
echo "ollama (container) pid=$!"
