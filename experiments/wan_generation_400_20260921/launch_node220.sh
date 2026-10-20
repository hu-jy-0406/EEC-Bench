#!/usr/bin/env bash
set -euo pipefail
DIR="/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/wan_generation_400_20260921"
PY="/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python"

exec srun --jobid=218030 \
  "$PY" -u "${DIR}/node_supervisor.py" --cards 0,1,2,3,4,5,6,7 \
  > "${DIR}/logs/supervisor_node220.log" 2>&1
