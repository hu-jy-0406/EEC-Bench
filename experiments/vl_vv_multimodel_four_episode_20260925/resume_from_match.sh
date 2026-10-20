#!/usr/bin/env bash
set -euo pipefail
case=$1; gpu=$2; uuid=$3
root=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench
api=("$root/scripts/openai_api_env.sh" /vast/users/guangyi.chen/anaconda3/bin/python "$root/scripts/run_vl_vv_detection.py")
cd "$root"
"${api[@]}" match --case "$case"
"${api[@]}" dino_prepare --case "$case"
"${api[@]}" dino --case "$case" --gpu "$gpu" --gpu-uuid "$uuid"
"${api[@]}" attach_dino --case "$case"
"${api[@]}" discover_issues --case "$case" --issue-output "$case/issue_discovery"
