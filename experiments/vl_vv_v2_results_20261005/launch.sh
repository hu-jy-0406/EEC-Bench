#!/usr/bin/env bash
# Three API-bound streams in one overlapping step of existing allocation 236651
# (node270: checked load ~0.13, ~2 TB free; no GPU used).
set -euo pipefail
HERE=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/vl_vv_v2_results_20261005
API=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/scripts/openai_api_env.sh
PY=/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python
exec srun --jobid=236651 --overlap -n1 -c2 --cpu-bind=none bash -c "
  export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
  for r in run_a run_b run_c; do nice -n 10 $API $PY $HERE/run_remaining.py \$r > $HERE/stream_\$r.log 2>&1 & done
  wait"
