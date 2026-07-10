#!/bin/bash
#SBATCH --job-name=clmbr_smoke
#SBATCH --partition=gpu
#SBATCH --gpus=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32GB
#SBATCH --time=01:30:00
#SBATCH --output=/scratch/users/karun09/Counterfactual_Algorithm/logs/clmbr_smoke_%j.out
#SBATCH --error=/scratch/users/karun09/Counterfactual_Algorithm/logs/clmbr_smoke_%j.out

# Stage 0: validate the official frozen CLMBR (StanfordShahLab/clmbr-t-base) loads + runs via femr.
# femr==0.2.3 needs Python >3.9 but torch==2.1.2 has no cp312 wheel, and the cluster only ships
# python 3.6/3.9/3.12/3.14 -> use `uv` to provision a self-contained CPython 3.11 on $SCRATCH.
# Public GPU partition only (never roxanad). All install/cache on $SCRATCH (never $HOME).
set -euo pipefail

PROJ=/scratch/users/karun09/Counterfactual_Algorithm
BOOT=$SCRATCH/Counterfactual_Algorithm/envs/boot39      # tiny py3.9 venv just to host `uv`
VENV=$SCRATCH/Counterfactual_Algorithm/envs/clmbr311    # the real project env (CPython 3.11)

# Caches -> $SCRATCH
export PIP_CACHE_DIR=$SCRATCH/.cache/pip
export UV_CACHE_DIR=$SCRATCH/.cache/uv
export UV_PYTHON_INSTALL_DIR=$SCRATCH/.cache/uv/python
export XDG_CACHE_HOME=$SCRATCH/.cache
export HF_HOME=$SCRATCH/.cache/huggingface
export HF_HUB_CACHE=$HF_HOME/hub
export TRANSFORMERS_CACHE=$HF_HOME/hub
export TORCH_HOME=$SCRATCH/.cache/torch
mkdir -p "$PIP_CACHE_DIR" "$UV_CACHE_DIR" "$UV_PYTHON_INSTALL_DIR" "$HF_HUB_CACHE" \
         "$TORCH_HOME" "$PROJ/logs"

echo "=== node: $(hostname) ==="
nvidia-smi || true

ml purge
ml load devel python/3.9.0 gcc/12.4.0    # gcc for small C-extension source builds (pyzmq/argon2)

# Bootstrap uv inside a throwaway py3.9 venv (uv wheels run on 3.9; the env it *builds* is 3.11).
if [ ! -x "$BOOT/bin/uv" ]; then
  echo "=== bootstrapping uv ==="
  python3 -m venv "$BOOT"
  "$BOOT/bin/python" -m pip install --upgrade pip
  "$BOOT/bin/python" -m pip install uv
fi
UV="$BOOT/bin/uv"

# Provision a self-contained CPython 3.11 and create the project venv from it.
if [ ! -x "$VENV/bin/python" ]; then
  echo "=== provisioning CPython 3.11 via uv ==="
  "$UV" python install 3.11
  "$UV" venv --python 3.11 --seed "$VENV"
fi

# Install the pinned CLMBR stack + project deps. xformers pinned to the torch-2.1.2 companion
# release so the resolver cannot drag torch forward.
echo "=== installing pinned CLMBR stack into $VENV ==="
# pyarrow/pyzmq pinned to versions that ship el7 (manylinux2014/glibc-2.17) cp311 wheels, so the
# resolver does NOT fall back to a Rust/C++ source build (the el7 glibc is too old for latest wheels).
"$UV" pip install --python "$VENV/bin/python" \
  torch==2.1.2 femr==0.2.3 datasets==2.15.0 xformers==0.0.23.post1 transformers==4.35.2 \
  "pyarrow==14.0.2" "pyzmq==25.1.2" \
  jupyter nbconvert ipykernel "numpy<2" "pandas==2.0.3" pyyaml gymnasium tqdm scikit-learn

source "$VENV/bin/activate"
python --version
python -c "import femr, torch; print('femr OK | torch', torch.__version__, '| cuda', torch.cuda.is_available())"

cd "$PROJ"
echo "=== executing notebook ==="
jupyter nbconvert --to notebook --execute --inplace \
  --ExecutePreprocessor.timeout=3600 \
  --ExecutePreprocessor.kernel_name=python3 \
  notebooks/clmbr_smoke.ipynb

echo "=== STAGE0_OK ==="
