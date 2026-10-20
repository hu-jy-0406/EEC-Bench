#!/usr/bin/env bash
# Three API-bound streams in one overlapping step of existing allocation 236651
# (node270: checked load 0.08, ~2 TB free memory; no GPU used).
set -euo pipefail
HERE=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/vl_vv_partial_review_20261006
API=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/scripts/openai_api_env.sh
PY=/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python
exec srun --jobid=236651 --overlap -n1 -c2 --cpu-bind=none bash -c "
  export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
  for s in 0 1 2; do nice -n 10 $API $PY $HERE/run_rereview.py \$s 3 > $HERE/stream\$s.log 2>&1 & done
  wait"
