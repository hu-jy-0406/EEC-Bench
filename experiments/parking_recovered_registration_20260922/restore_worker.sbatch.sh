#!/usr/bin/env bash
# Run inside the original existing allocation. Shared lease + idle guard ensure
# that automatic manager recovery and explicit restoration cannot both launch.
set -euo pipefail
worker=$1
mode=$2
physical_gpu=$3
uuid=$4
cpus=$5
root=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/holocine_generation_200_20260922
py=/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python
exec "$py" "$root/lease_guard.py" "$physical_gpu" "$uuid" taskset -c "$cpus" "$py" -u "$root/campaign.py" worker --worker "$worker" --mode "$mode"
