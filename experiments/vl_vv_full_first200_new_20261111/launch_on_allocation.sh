#!/bin/bash
# Usage (inside srun --jobid=J --overlap): launch_on_allocation.sh THREADS_PER_GPU [SLOTS_PER_GPU]
# Probes the allocation's GPUs (two samples 30 s apart) and starts run_full_new.py on the idle ones only.
set -e
cd /vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/vl_vv_full_first200_new_20261111
J=$SLURM_JOB_ID
ARGS=$(/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python /vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/vl_vv_full_first200_v3_20261109/probe_gpus.py gpu_probe_launch_$J.json | /vast/users/guangyi.chen/anaconda3/envs/vace/bin/python -c 'import json,sys; print(" ".join("--gpu "+g for g in json.load(sys.stdin)["idle"]))')
N=$(echo $ARGS | grep -o -- '--gpu' | wc -l)
echo "allocation $J host $(hostname) idle GPUs: $ARGS"
[ "$N" -gt 0 ] || { echo "no idle GPU"; exit 3; }
exec /vast/users/guangyi.chen/anaconda3/envs/vace/bin/python run_full_new.py $ARGS --threads $((N * $1)) --slots-per-gpu ${2:-1} --cap 140
