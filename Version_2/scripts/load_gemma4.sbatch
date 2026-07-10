#!/bin/bash
#SBATCH -J load_gemma4
#SBATCH -p normal
#SBATCH --time=01:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=8GB
#SBATCH -o /scratch/users/karun09/Version_2/logs/load_gemma4_%j.out
#SBATCH -e /scratch/users/karun09/Version_2/logs/load_gemma4_%j.err
set -uo pipefail
source /scratch/users/karun09/miniforge3/etc/profile.d/conda.sh
conda activate simr
export HF_HOME=/scratch/users/karun09/.huggingface
unset HF_HUB_OFFLINE
export HF_HUB_ENABLE_HF_TRANSFER=0 TOKENIZERS_PARALLELISM=false
HUB="$HF_HOME/hub"; DEST=/scratch/users/karun09/loaded_models
repo="google/gemma-4-E4B-it"; name="Gemma-4-E4B-it"

echo ">>> downloading $repo"
hf download "$repo" --repo-type model && echo "OK" || { echo "FAILED"; exit 1; }

d="$HUB/models--${repo//\//--}"; snap="$d/snapshots/$(cat "$d/refs/main")"
nw=$(find -L "$snap" -maxdepth 1 \( -name '*.safetensors' -o -name '*.bin' \) | wc -l)
if [ "$nw" -gt 0 ]; then ln -sfn "$snap" "$DEST/$name"; echo "linked $name -> $snap"; else echo "no weights!"; exit 1; fi
ls -l "$DEST"
