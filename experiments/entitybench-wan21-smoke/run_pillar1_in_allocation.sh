#!/bin/bash
# Invoke only inside an existing, verified-idle allocation:
# srun --jobid=<job_id> --overlap --nodes=1 --ntasks=1 --cpus-per-task=8 \
#   --gres=gpu:mi210:1 bash \
#   experiments/entitybench-wan21-smoke/run_pillar1_in_allocation.sh

set -euo pipefail

EEC_ROOT=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench
EXPERIMENT_ROOT=${EEC_ROOT}/experiments/entitybench-wan21-smoke
VBENCH_PYTHON=/vast/users/guangyi.chen/anaconda3/envs/vbench/bin/python
VBENCH_CACHE=${EXPERIMENT_ROOT}/cache/vbench

if [[ -z "${SLURM_JOB_ID:-}" ]]; then
  echo "Refusing to run outside an existing Slurm allocation" >&2
  exit 2
fi

mkdir -p ${EXPERIMENT_ROOT}/eval_results ${EXPERIMENT_ROOT}/logs

export PYTHONNOUSERSITE=1
export VBENCH_CACHE_DIR=${VBENCH_CACHE}
export XDG_CACHE_HOME=${EXPERIMENT_ROOT}/cache
export TORCH_HOME=${EXPERIMENT_ROOT}/cache/torch
export MIOPEN_USER_DB_PATH=${EXPERIMENT_ROOT}/cache/miopen
export MIOPEN_CUSTOM_CACHE_DIR=${EXPERIMENT_ROOT}/cache/miopen
# VBench 0.1.5's AMT loader predates PyTorch 2.6's weights_only default.
# The checkpoint is the standard, pre-provisioned VBench AMT release.
export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1
export TOKENIZERS_PARALLELISM=false

cd ${EEC_ROOT}

${VBENCH_PYTHON} eval/evaluate_benchmark.py \
  --results_dir experiments/entitybench-wan21-smoke/generated \
  --scripts_dir data/scripts \
  --split_json experiments/entitybench-wan21-smoke/smoke_split.json \
  --out_dir experiments/entitybench-wan21-smoke/eval_results/wan21_pillar1 \
  --method_name wan21_t2v_1.3b_smoke20 \
  --pillars 1 \
  --device cuda \
  --vbench_cache_dir experiments/entitybench-wan21-smoke/cache/vbench \
  --resume
