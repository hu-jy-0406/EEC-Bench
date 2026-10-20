#!/usr/bin/env bash
set -u
if [[ $# -ne 5 ]]; then
  echo "usage: $0 EPISODE GPU_INDEX GPU_UUID SLOT CPUSET" >&2
  exit 2
fi
episode=$1
gpu=$2
gpu_uuid=$3
slot=$4
cpuset=$5
root=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench
exp="$root/experiments/vl_vv_wan_storymem_holocine_10_20260925"
models=(wan22 storymem holocine)
failures=0
for offset in 0 1 2; do
  model=${models[$(((slot + offset) % 3))]}
  case_root="$exp/$model/$episode"
  case_dir="$case_root/case"
  mkdir -p "$case_root/logs"
  if taskset -c "$cpuset" bash "$exp/run_case_reviewed.sh" "$case_dir" "$gpu" "$gpu_uuid" \
      > "$case_root/logs/pipeline.log" 2>&1; then
    printf '%s %s success\n' "$(date -Is)" "$model" >> "$exp/episode_runs.log"
  else
    rc=$?
    failures=$((failures + 1))
    printf '%s %s failed exit=%s\n' "$(date -Is)" "$model" "$rc" >> "$exp/episode_runs.log"
  fi
done
printf '{"episode_id":"%s","slot":%s,"gpu_index":%s,"gpu_uuid":"%s","cpuset":"%s","failed_model_cases":%s,"finished_at":"%s"}\n' \
  "$episode" "$slot" "$gpu" "$gpu_uuid" "$cpuset" "$failures" "$(date -Is)" \
  > "$exp/$episode.slot_status.json"
[[ $failures -eq 0 ]]
