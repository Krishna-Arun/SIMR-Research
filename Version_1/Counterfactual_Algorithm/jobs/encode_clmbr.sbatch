#!/bin/bash
#SBATCH --job-name=encode_clmbr
#SBATCH --partition=gpu
#SBATCH --gpus=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64GB
#SBATCH --time=04:00:00
#SBATCH --output=/scratch/users/karun09/Counterfactual_Algorithm/logs/encode_clmbr_%j.out
#SBATCH --error=/scratch/users/karun09/Counterfactual_Algorithm/logs/encode_clmbr_%j.out

# Stage 2b: encode patients with the frozen official CLMBR (femr) + Athena ontology.
# Prereqs: (1) build_meds.py has produced data/mimic-meds, (2) data.athena_path points at the
# unzipped Athena OMOP vocabulary (CONCEPT.csv, ...). Public GPU partition only.
set -euo pipefail
PROJ=/scratch/users/karun09/Counterfactual_Algorithm
export PYTHONPATH=$PROJ
export HF_HOME=$SCRATCH/.cache/huggingface HF_HUB_CACHE=$SCRATCH/.cache/huggingface/hub
export TRANSFORMERS_CACHE=$SCRATCH/.cache/huggingface/hub TOKENIZERS_PARALLELISM=false
ml purge; ml load devel python/3.9.0 gcc/12.4.0
source $SCRATCH/Counterfactual_Algorithm/envs/clmbr311/bin/activate
cd "$PROJ"

# (Re)build MEDS only if absent.
[ -d data/mimic-meds/data ] || python preprocessing/build_meds.py configs/default.yaml

python models/encode_clmbr.py configs/default.yaml
echo "=== CLMBR states ready; now run the world model / benchmark / RL with encoder.kind: clmbr ==="
