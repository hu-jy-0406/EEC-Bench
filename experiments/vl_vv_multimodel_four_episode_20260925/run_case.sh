#!/usr/bin/env bash
# Run one immutable model/episode case through detection, matching, DINO, and issue discovery.
# The caller must start this only on a verified idle physical GPU.
set -euo pipefail
if [[ $# -ne 3 ]]; then
  echo "usage: $0 CASE GPU_INDEX GPU_UUID" >&2
  exit 2
fi
case=$1
gpu=$2
gpu_uuid=$3
root=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench
py=/vast/users/guangyi.chen/anaconda3/bin/python
api=("$root/scripts/openai_api_env.sh" "$py" "$root/scripts/run_vl_vv_detection.py")
cd "$root"
mkdir -p "$case/logs"
rocm-smi -d "$gpu" --showuse --showmeminfo vram --showuniqueid --showpids > "$case/gpu_launch_check.txt"
printf 'started_at=%s\ncase=%s\ngpu=%s\ngpu_uuid=%s\n' "$(date -Is)" "$case" "$gpu" "$gpu_uuid" > "$case/pipeline_launch.txt"
"${api[@]}" detect --case "$case" --gpu "$gpu" --gpu-uuid "$gpu_uuid" --shot-workers 3 --device cuda
"${api[@]}" match --case "$case"
"${api[@]}" dino_prepare --case "$case"
"${api[@]}" dino --case "$case" --gpu "$gpu" --gpu-uuid "$gpu_uuid"
"${api[@]}" attach_dino --case "$case"
"${api[@]}" discover_issues --case "$case" --issue-output "$case/issue_discovery"
printf 'finished_at=%s\n' "$(date -Is)" >> "$case/pipeline_launch.txt"
