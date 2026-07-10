#!/bin/bash
#SBATCH -J load_models
#SBATCH -p normal
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=8GB
#SBATCH -o /scratch/users/karun09/Version_2/logs/load_models_%j.out
#SBATCH -e /scratch/users/karun09/Version_2/logs/load_models_%j.err

set -uo pipefail

# ---- env -------------------------------------------------------------------
source /scratch/users/karun09/miniforge3/etc/profile.d/conda.sh
conda activate simr

export HF_HOME=/scratch/users/karun09/.huggingface
unset HF_HUB_OFFLINE                 # we need to reach the Hub
export HF_HUB_ENABLE_HF_TRANSFER=0   # hf_transfer not installed
export TOKENIZERS_PARALLELISM=false
HUB="$HF_HOME/hub"
DEST=/scratch/users/karun09/loaded_models

# Token (only needed for gated repos). Current one is invalid -> gated skipped.
TOKFILE=/scratch/users/karun09/Version_2/counterfactual_simulation/.hf_token
[ -f "$TOKFILE" ] && export HF_TOKEN="$(tr -d '\n' < "$TOKFILE")"

echo "==== load_models job on $(hostname) ===="
echo "HF_HOME=$HF_HOME"; echo "DEST=$DEST"

# ---- helpers ---------------------------------------------------------------
# download <repo_id> [extra hf-download args...]
download () {
  local repo="$1"; shift
  echo ">>> downloading $repo $*"
  hf download "$repo" --repo-type model "$@" \
    && echo "    OK $repo" || echo "    FAILED $repo"
}

# link <repo_id> <friendly_name>
link () {
  local repo="$1" name="$2"
  local cachedir="$HUB/models--${repo//\//--}"
  local ref="$cachedir/refs/main"
  if [ ! -f "$ref" ]; then echo "    !! no cache for $repo, skip link"; return 1; fi
  local hash; hash="$(cat "$ref")"
  local snap="$cachedir/snapshots/$hash"
  # sanity: must contain weights, not just a stub (follow symlinks into blobs)
  local nw; nw=$(find -L "$snap" -maxdepth 1 \( -name '*.safetensors' -o -name '*.bin' \) 2>/dev/null | wc -l)
  if [ "$nw" -eq 0 ]; then
    echo "    !! $repo snapshot has no weights (gated/stub?), skip link"; return 1
  fi
  ln -sfn "$snap" "$DEST/$name"
  echo "    linked $name -> $snap"
}

# ---- 1. download ungated missing models ------------------------------------
download "Qwen/Qwen3-8B"
download "microsoft/Phi-4-mini-instruct"
# skip the redundant 45G mistral-format single file; keep HF-format sharded weights
download "mistralai/Mistral-Small-3.1-24B-Instruct-2503" --exclude "consolidated.safetensors"
# reclaim the orphaned consolidated.safetensors blob from the earlier broken run
mdir="$HUB/models--mistralai--Mistral-Small-3.1-24B-Instruct-2503"
if [ -L "$mdir/snapshots/$(cat "$mdir/refs/main")/consolidated.safetensors" ]; then
  blob=$(readlink -f "$mdir/snapshots/$(cat "$mdir/refs/main")/consolidated.safetensors")
  rm -f "$mdir/snapshots/$(cat "$mdir/refs/main")/consolidated.safetensors" "$blob"
  echo "    removed orphan consolidated.safetensors"
fi

# Gemma 4 E4B is ungated (google/gemma-4-E4B-it) -- no license wall
download "google/gemma-4-E4B-it"

# ---- 2. symlink everything into loaded_models ------------------------------
echo "==== linking into $DEST ===="
link "StanfordShahLab/clmbr-t-base"                    "CLMBR-t-base"
link "Qwen/Qwen3-8B"                                   "Qwen3-8B"
link "NousResearch/Meta-Llama-3.1-8B-Instruct"         "Llama-3.1-8B-Instruct"
link "google/gemma-4-E4B-it"                           "Gemma-4-E4B-it"
link "mistralai/Mistral-Small-3.1-24B-Instruct-2503"   "Mistral-Small-3.1-24B-Instruct"
link "microsoft/Phi-4-mini-instruct"                   "Phi-4-mini-instruct"
link "openai/gpt-oss-20b"                              "GPT-OSS-20B"

echo "==== final loaded_models ===="
ls -l "$DEST"
echo "==== DONE ===="
