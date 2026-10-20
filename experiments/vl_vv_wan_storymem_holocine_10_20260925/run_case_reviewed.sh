#!/usr/bin/env bash
set -uo pipefail
if [[ $# -ne 3 ]]; then
  echo "usage: $0 CASE_DIR GPU_INDEX GPU_UUID" >&2
  exit 2
fi
case_dir=$(realpath "$1")
gpu=$2
gpu_uuid=$3
root=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench
py=/vast/users/guangyi.chen/anaconda3/bin/python
legacy="$root/experiments/vl_vv_multimodel_four_episode_20260925/run_case.sh"
api="$root/scripts/openai_api_env.sh"
mkdir -p "$case_dir"
start_ns=$(date +%s%N)
pipeline_start_ns=0
pipeline_end_ns=0
review_start_ns=0
review_end_ns=0
pipeline_status=not_started
review_status=not_started
case_status=failed
exit_code=1
write_timing() {
  local end_ns
  end_ns=$(date +%s%N)
  cat > "$case_dir/case_timing.json" <<EOF
{
  "status": "$case_status",
  "pipeline_status": "$pipeline_status",
  "review_status": "$review_status",
  "gpu_index": $gpu,
  "gpu_uuid": "$gpu_uuid",
  "started_epoch_ns": $start_ns,
  "pipeline_started_epoch_ns": $pipeline_start_ns,
  "pipeline_finished_epoch_ns": $pipeline_end_ns,
  "review_started_epoch_ns": $review_start_ns,
  "review_finished_epoch_ns": $review_end_ns,
  "finished_epoch_ns": $end_ns
}
EOF
}
trap write_timing EXIT

pipeline_start_ns=$(date +%s%N)
if bash "$legacy" "$case_dir" "$gpu" "$gpu_uuid"; then
  pipeline_status=success
else
  pipeline_rc=$?
  pipeline_status=failed
  exit_code=$pipeline_rc
  exit "$exit_code"
fi
pipeline_end_ns=$(date +%s%N)

review_start_ns=$(date +%s%N)
if "$api" "$py" "$root/scripts/run_vl_vv_issue_review.py" \
    --case "$case_dir" --issues "$case_dir/issue_discovery/result.json" \
    --output "$case_dir/issue_review"; then
  review_status=success
  review_end_ns=$(date +%s%N)
  case_status=success
  exit_code=0
else
  review_rc=$?
  review_status=failed
  review_end_ns=$(date +%s%N)
  exit_code=$review_rc
fi
exit "$exit_code"
