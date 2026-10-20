#!/usr/bin/env bash
set -euo pipefail
cd /vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench
export OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=4
exec /vast/users/guangyi.chen/anaconda3/bin/python \
 EECBench/experiments/study2_detection_only_fresh_20260918/guard_gpu.py 6 GPU-9bd66cc06860c5b4 \
 /vast/users/guangyi.chen/anaconda3/bin/python EECBench/scripts/run_gs_integrated.py \
 --manifest EECBench/experiments/study3_appearance_full_20260921/raw_manifest.json \
 --narrative EECBench/experiments/study3_appearance_full_20260921/narrative.json \
 --output EECBench/experiments/pipeline_parallel_20260921/run \
 --alignment-method roma_fps32 --consistency-protocol temporal_v2 \
 --runtime-profile temporal_spatial_v1 --schedule-profile parallel_v1 --stop-after full \
 --gpu 6 --gpu-uuid GPU-9bd66cc06860c5b4
