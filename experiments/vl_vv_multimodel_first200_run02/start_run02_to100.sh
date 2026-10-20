#!/usr/bin/env bash
set -euo pipefail

EXP_ROOT="/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/vl_vv_multimodel_first200_run02"
PROJECT_ROOT="/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench"

exec srun --jobid=229943 \
  "${PROJECT_ROOT}/EECBench/scripts/openai_api_env.sh" \
  /vast/users/guangyi.chen/anaconda3/envs/vace/bin/python \
  "${PROJECT_ROOT}/EECBench/experiments/vl_vv_multimodel_first200_20260926/run_batch.py" \
  --batch "${PROJECT_ROOT}/EECBench/experiments/vl_vv_multimodel_first200_20260926/batch" \
  --exp-dir "${EXP_ROOT}" \
  --gpu 0=GPU-128c020251686b41 \
  --gpu 1=GPU-dcc345a9a86b12d2 \
  --gpu 2=GPU-6bbcff4bcfa6870e \
  --gpu 3=GPU-edf23653bf69808b \
  --gpu 4=GPU-98f3fa39b787bd92 \
  --max-workers 5 \
  --shot-workers 2 \
  --stop-after-priority 100 \
  > "${EXP_ROOT}/controller.log" 2>&1
