#!/usr/bin/env bash
# Three API-bound streams in one overlapping step of existing allocation 239124
# (node257: checked load ~5/128 cores, ~1.5 TB free; no GPU used).
set -euo pipefail
HERE=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/vl_vv_old_vs_new_20261005
API=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/scripts/openai_api_env.sh
PY=/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python
exec srun --jobid=239124 --overlap -n1 -c3 --cpu-bind=none bash -c "
  export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
  for s in 1 2 3; do nice -n 10 $API $PY $HERE/run_comparison.py \$s > $HERE/stream\$s.log 2>&1 & done
  wait"
