#!/usr/bin/env bash
set -euo pipefail
EXP_ROOT="/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/vl_vv_multimodel_first200_run02_b"
P="/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench"
# Controller B: priorities 101-200 on own allocation 229942 (auh7-1b-gpu-296), cards 0-4.
exec srun --jobid=229942 --overlap -N1 -n1 "$P/EECBench/scripts/openai_api_env.sh" \
  /vast/users/guangyi.chen/anaconda3/envs/vace/bin/python "$P/EECBench/experiments/vl_vv_multimodel_first200_20260926/run_batch.py" \
  --batch "$P/EECBench/experiments/vl_vv_multimodel_first200_20260926/batch" --exp-dir "$EXP_ROOT" --min-priority 101 \
  --gpu 0=GPU-9cd6ef589ebf6b59 --gpu 1=GPU-cec5a2cd65f49430 --gpu 2=GPU-7c5a6636e5a935b4 --gpu 3=GPU-f05ced084a91fe7d --gpu 4=GPU-adbaf98a231ddbca \
  --max-workers 5 --shot-workers 2 > "$EXP_ROOT/controller.log" 2>&1
