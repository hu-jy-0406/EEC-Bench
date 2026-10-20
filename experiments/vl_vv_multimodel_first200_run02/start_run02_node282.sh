#!/usr/bin/env bash
set -euo pipefail
EXP_ROOT="/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/vl_vv_multimodel_first200_run02"
PROJECT_ROOT="/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench"
# Borrowed idle cards on job 223928 (auh7-1b-gpu-282); verified 0% util / 0 VRAM / no KFD process.
exec srun --jobid=223928 --overlap -N1 -n1 \
  "${PROJECT_ROOT}/EECBench/scripts/openai_api_env.sh" \
  /vast/users/guangyi.chen/anaconda3/envs/vace/bin/python \
  "${PROJECT_ROOT}/EECBench/experiments/vl_vv_multimodel_first200_20260926/run_batch.py" \
  --batch "${PROJECT_ROOT}/EECBench/experiments/vl_vv_multimodel_first200_20260926/batch" \
  --exp-dir "${EXP_ROOT}" \
  --gpu 0=GPU-2e7a3afcefcaca4b --gpu 1=GPU-63f0fe2c43bc1640 --gpu 4=GPU-b66ccb62112b0571 \
  --gpu 5=GPU-0cec181d5e2ce525 --gpu 6=GPU-daf531ba129c665e \
  --max-workers 5 --shot-workers 2 \
  > "${EXP_ROOT}/controller.log" 2>&1
