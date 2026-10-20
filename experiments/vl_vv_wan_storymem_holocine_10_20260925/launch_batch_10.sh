#!/usr/bin/env bash
set -euo pipefail
job=214135
root=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench
exp="$root/experiments/vl_vv_wan_storymem_holocine_10_20260925"
runner="$exp/run_episode.sh"
if [[ ! -f "$exp/prepared_cases.json" || -e "$exp/batch_launch_started" ]]; then
  echo 'Need fresh prepared_cases.json and no prior batch launch marker.' >&2
  exit 2
fi
if ! squeue -h -j "$job" -t RUNNING | rg -q "$job"; then
  echo "Allocation $job is not RUNNING; do not request new resources here." >&2
  exit 2
fi
date -Is > "$exp/batch_launch_started"
episodes=(
  74Od5-Fmf60_s00006_n4_clean_v2
  74S1Iw0gJrA_s00006_n4_clean_v2
  kTAOppBVgsU_s00001_n6_clean_v2
  7M9pU29bOeY_s00004_n4_clean_v2
  2hEV6a24yXc_s00017_n8_clean_v3_alt8
  6kwhPKkHFpA_s00007_n4_clean_v2
  v9I0QHOiU0Y_s00050_n4_clean_v2
  KFuxHDKp2oc_s00012_n6_clean_v2
  tIB4z4uMeNs_s00023_n4_clean_v2
  MTYQT6fSzaE_s00091_n4_clean_v2
)
nodes=(
  auh7-1b-gpu-251 auh7-1b-gpu-251 auh7-1b-gpu-251
  auh7-1b-gpu-251 auh7-1b-gpu-251 auh7-1b-gpu-251
  auh7-1b-gpu-302 auh7-1b-gpu-302 auh7-1b-gpu-302 auh7-1b-gpu-302
)
gpus=(0 1 2 3 4 5 0 1 2 3)
uuids=(
  GPU-62fb31160610e64f GPU-1cbe8ddb4a66d9be GPU-f3891072d8a2dde1
  GPU-8671781a59366d1f GPU-dc8586ed24f20237 GPU-4cdcc55084aa1f7a
  GPU-0f6e743c1254dd2d GPU-b2a9641bb5819b04 GPU-788b33bf73b2bc68
  GPU-4138d13123e6566d
)
pids=()
for slot in "${!episodes[@]}"; do
  node=${nodes[$slot]}; gpu=${gpus[$slot]}; uuid=${uuids[$slot]}; ep=${episodes[$slot]}
  local_slot=$slot
  if (( local_slot >= 6 )); then local_slot=$((local_slot - 6)); fi
  cpu_start=$((8 + local_slot * 8))
  cpuset="$cpu_start-$((cpu_start + 7))"
  log="$exp/logs/${ep}.log"
  mkdir -p "$exp/logs"
  srun --jobid="$job" --overlap --nodes=1 --ntasks=1 --cpus-per-task=128 \
    --cpu-bind=none --nodelist="$node" \
    taskset -c "$cpuset" bash "$runner" "$ep" "$gpu" "$uuid" "$slot" "$cpuset" \
    > "$log" 2>&1 &
  pids+=("$!")
done
failed=0
for pid in "${pids[@]}"; do
  if ! wait "$pid"; then failed=$((failed + 1)); fi
done
date -Is > "$exp/batch_launch_finished"
printf 'finished=%s failed_episode_workers=%s\n' "$(date -Is)" "$failed" >> "$exp/launch_summary.txt"
exit "$((failed != 0))"
