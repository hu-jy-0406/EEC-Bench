#!/usr/bin/env bash
set -euo pipefail
cd /vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench
R=EECBench/experiments/generation_feasibility_20260921
test -f "$R/models/Wan2.2-T2V-A14B/download_complete.json"
export PYTHONPATH="$R/wan_deps:$R/deps:$R/repos/Wan2.2"
export TOKENIZERS_PARALLELISM=false
exec /vast/users/guangyi.chen/anaconda3/envs/vace/bin/python EECBench/experiments/study2_detection_only_fresh_20260918/guard_gpu.py 2 GPU-aabcddaa244a3d6e /vast/users/guangyi.chen/anaconda3/envs/vace/bin/python -u "$R/wan_benchmark.py" "$@"
