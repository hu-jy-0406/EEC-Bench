#!/usr/bin/env bash
set -euo pipefail
DIR="/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/wan_generation_400_20260921"
PY="/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python"

exec "$PY" -u "${DIR}/hf_uploader.py" --daemon --interval 20 \
  > "${DIR}/logs/uploader.log" 2>&1
