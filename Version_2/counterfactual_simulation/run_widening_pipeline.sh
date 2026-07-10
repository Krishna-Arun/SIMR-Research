#!/bin/bash
set -e
CS=/scratch/users/karun09/Version_2/counterfactual_simulation; CA=/scratch/users/karun09/Version_1/Counterfactual_Algorithm
SIMR=/scratch/users/karun09/miniforge3/envs/simr/bin/python
CLMBR=/scratch/users/karun09/Version_1/Counterfactual_Algorithm/envs/clmbr311/bin/python
export HF_TOKEN="$(tr -d ' \n\r' < $CS/.hf_token)"
export HF_HOME=/scratch/users/karun09/.huggingface HF_HUB_OFFLINE=1 TOKENIZERS_PARALLELISM=false

echo "ORCH wait-for-MEDS $(date)"
until [ -f $CS/data_icu/trajectories.pkl ] && [ -f $CS/data_icu/mimic_meds/data/icu_000.parquet ]; do
  if ! pgrep -f build_icu_meds.py >/dev/null && [ ! -f $CS/data_icu/trajectories.pkl ]; then
    echo "ORCH FAIL: MEDS build exited without output"; exit 1; fi
  sleep 60
done
echo "ORCH MEDS-ready $(date)"

echo "ORCH STAGE encode start $(date)"
cd $CA && $CLMBR models/encode_clmbr.py $CS/configs_icu.yaml
echo "ORCH STAGE encode done $(date)"

cd $CS
echo "ORCH STAGE actions start $(date)"; $SIMR build_enriched_actions_icu.py; echo "ORCH STAGE actions done"
echo "ORCH STAGE substrate start $(date)"; $SIMR build_train_substrate_icu.py; echo "ORCH STAGE substrate done"
echo "ORCH STAGE train start $(date)"; $SIMR train_delta_decoder.py; echo "ORCH STAGE train done"
echo "ORCH ALL DONE $(date)"
