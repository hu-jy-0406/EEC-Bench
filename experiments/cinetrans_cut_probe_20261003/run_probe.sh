#!/usr/bin/env bash
# One guarded CineTrans-DiT generation per physical card on allocation 229942; same env as the production runner.
set -uo pipefail
HERE=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/cinetrans_cut_probe_20261003
UP=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/cinetrans_dit_rocm_20260925/upstream
GUARD=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/scripts/guard_geocalib_boxer_gpu.py
PY=/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python
export OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=1 TOKENIZERS_PARALLELISM=false PYTHONUNBUFFERED=1 PYTORCH_HIP_ALLOC_CONF=expandable_segments:True
unset HIP_VISIBLE_DEVICES CUDA_VISIBLE_DEVICES
declare -a RUNS=(A_official_demo_2shot_5s B_ep8_2shot_5s C_ep8_3shot_8s D_ep8_2shot_10s)
declare -a UUIDS=(GPU-9cd6ef589ebf6b59 GPU-cec5a2cd65f49430 GPU-7c5a6636e5a935b4 GPU-f05ced084a91fe7d)
for i in 0 1 2 3; do
  name=${RUNS[$i]}; c=/tmp/cinetrans-probe-miopen/$name; mkdir -p $c/db $c/cache $c/mpl
  ( cd $UP && MIOPEN_USER_DB_PATH=$c/db MIOPEN_CUSTOM_CACHE_DIR=$c/cache MPLCONFIGDIR=$c/mpl \
    /usr/bin/time -f "WALL %e" $PY $GUARD $i ${UUIDS[$i]} $PY $UP/generate.py --config $HERE/configs/$name.yaml > $HERE/logs/$name.log 2>&1; echo "EXIT $?" >> $HERE/logs/$name.log ) &
  sleep 20
done
wait
