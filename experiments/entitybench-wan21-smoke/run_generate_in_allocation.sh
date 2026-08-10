#!/bin/bash
# Invoke only inside an existing, verified-idle allocation:
# srun --jobid=<job_id> --overlap --nodes=1 --ntasks=1 --cpus-per-task=4 \
#   bash experiments/entitybench-wan21-smoke/run_generate_in_allocation.sh

set -euo pipefail

EEC_ROOT=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench
EXPERIMENT_ROOT=${EEC_ROOT}/experiments/entitybench-wan21-smoke
WAN_ROOT=/vast/users/guangyi.chen/causal_group/jinyuan.hu/shotpilot/Wan2.1
WAN_CHECKPOINT=/vast/users/guangyi.chen/causal_group/jinyuan.hu/shotpilot/models/Wan2.1-T2V-1.3B
VACE_PYTHON=/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python
EPISODE_ID=000020ca-f66b-3542-8ad1-5c3172105f7b__run15__i0_j19__T240

if [[ -z "${SLURM_JOB_ID:-}" ]]; then
  echo "Refusing to run outside an existing Slurm allocation" >&2
  exit 2
fi

mkdir -p ${EXPERIMENT_ROOT}/logs ${EXPERIMENT_ROOT}/cache

export PYTHONNOUSERSITE=1
export XDG_CACHE_HOME=${EXPERIMENT_ROOT}/cache
export HF_HOME=${EXPERIMENT_ROOT}/cache/huggingface
export MIOPEN_USER_DB_PATH=${EXPERIMENT_ROOT}/cache/miopen
export MIOPEN_CUSTOM_CACHE_DIR=${EXPERIMENT_ROOT}/cache/miopen
export TOKENIZERS_PARALLELISM=false

cd ${EEC_ROOT}

${VACE_PYTHON} experiments/entitybench-wan21-smoke/generate_episode.py \
  --script-json data/scripts/${EPISODE_ID}.json \
  --output-root experiments/entitybench-wan21-smoke/generated \
  --wan-root ${WAN_ROOT} \
  --checkpoint ${WAN_CHECKPOINT} \
  --base-seed 20260810 \
  --sample-steps 20

