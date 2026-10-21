#!/usr/bin/env bash
# API-bound streams in one overlapping step of an existing allocation (load checked before launch; no GPU).
# Usage: launch.sh JOBID SET NSTREAMS
set -euo pipefail
JOB=$1; SET=$2; N=$3
HERE=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/vl_vv_transition_provenance_20261021
API=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/scripts/openai_api_env.sh
PY=/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python
exec srun --jobid=$JOB --overlap -n1 -c2 --cpu-bind=none bash -c "
  export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
  for s in \$(seq 0 $((N-1))); do nice -n 10 $API $PY $HERE/run_jobs.py $SET \$s $N > $HERE/${SET}_stream\$s.log 2>&1 & done
  wait"
