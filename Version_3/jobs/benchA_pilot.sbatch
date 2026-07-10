#!/bin/bash
#SBATCH --job-name=benchA_qgen_pilot
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --gpus=1
#SBATCH --constraint=GPU_MEM:48GB
#SBATCH --cpus-per-task=8
#SBATCH --mem=96GB
#SBATCH --time=06:00:00
#SBATCH --output=/scratch/users/karun09/Version_3/SIMR-Research/Version_3/logs/benchA_pilot_%j.out
#SBATCH --error=/scratch/users/karun09/Version_3/SIMR-Research/Version_3/logs/benchA_pilot_%j.err

set -uo pipefail

ROOT=/scratch/users/karun09/Version_3/SIMR-Research/Version_3
cd "$ROOT"

# ── RACE ARBITRATION ─────────────────────────────────────────────────────────
# Multiple GPU-class jobs may be queued for this pilot (e.g. L40S vs RTX_3090).
# The first to START grabs the lock (atomic mkdir), cancels its siblings, and
# runs. Any sibling that starts later sees the lock and exits immediately, so
# the shared outputs/ are never written by two jobs at once.
RACE_DIR="$ROOT/.race"
LOCK="$RACE_DIR/lock"
mkdir -p "$RACE_DIR"
if mkdir "$LOCK" 2>/dev/null; then
  echo "$SLURM_JOB_ID $(hostname) $(date)" > "$LOCK/winner"
  echo "[race] WON by job ${SLURM_JOB_ID} on $(hostname)"
  if [ -f "$RACE_DIR/jobids" ]; then
    for jid in $(cat "$RACE_DIR/jobids"); do
      if [ "$jid" != "${SLURM_JOB_ID}" ]; then
        scancel "$jid" 2>/dev/null && echo "[race] cancelled sibling job $jid"
      fi
    done
  fi
else
  echo "[race] LOST — winner is: $(cat "$LOCK/winner" 2>/dev/null). Exiting cleanly."
  exit 0
fi

# ── environment ──────────────────────────────────────────────────────────────
export PY=/scratch/users/karun09/miniforge3/envs/simr/bin/python
export PATH=/scratch/users/karun09/miniforge3/envs/simr/bin:$PATH
export HF_HOME=/scratch/users/karun09/.huggingface
export HF_HUB_OFFLINE=0
export TOKENIZERS_PARALLELISM=false

echo "############################################################"
echo "# Benchmark A question-gen pilot"
echo "# node=$(hostname)  jobid=${SLURM_JOB_ID:-?}  $(date)"
echo "############################################################"

# ── stage 1: GPU + env sanity ────────────────────────────────────────────────
echo "===== [1] GPU + env sanity ====="
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv || true
$PY -c "import torch;print('torch',torch.__version__,'cuda',torch.cuda.is_available(),'ngpu',torch.cuda.device_count());[print(' ',i,torch.cuda.get_device_name(i)) for i in range(torch.cuda.device_count())]" || true

# ── stage 2: build PubMed MCP server (needed for A citations) ─────────────────
echo "===== [2] build PubMed MCP server ====="
( cd "$ROOT/Benchmark_A/PubMed-MCP-Server" \
    && npm install --no-audit --no-fund \
    && npm run build \
    && echo "PubMed server build OK" ) || echo "WARN: PubMed build failed (citation types may discard)"

# ── stage 3: CPU dry-run plumbing check for A/B/C ─────────────────────────────
echo "===== [3] CPU dry-run A/B/C (no models/network) ====="
for B in Benchmark_A Benchmark_B Benchmark_C; do
  echo "--- $B dry-run"
  ( cd "$ROOT/$B/Question_Gen" \
      && $PY -m py_compile *.py \
      && $PY orchestrator.py --dry-run --n 5 ) || echo "WARN: $B dry-run failed"
done

# ── stage 4: GPU pilot — Benchmark A, 20 questions, all types ─────────────────
echo "===== [4] GPU pilot: Benchmark A orchestrator --n 20 ====="
cd "$ROOT/Benchmark_A/Question_Gen"
[ -f outputs/questions.jsonl ] && cp outputs/questions.jsonl "outputs/questions.dryrun.$(date +%s).jsonl.bak" || true
$PY orchestrator.py --n 20 || echo "WARN: pilot exited nonzero"

echo "===== DONE $(date) ====="
echo "records in questions.jsonl:"; wc -l outputs/questions.jsonl 2>/dev/null || true
