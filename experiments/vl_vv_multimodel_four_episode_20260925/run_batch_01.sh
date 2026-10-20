#!/usr/bin/env bash
set -euo pipefail
root=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench
out=$root/experiments/vl_vv_multimodel_four_episode_20260925
run() {
  local node=$1 uuid=$2 model=$3 episode=$4
  srun --jobid=214135 --overlap --nodes=1 --ntasks=1 --nodelist="$node" --cpus-per-task=8 \
    "$out/run_case.sh" "$out/$model/$episode/case" 0 "$uuid" \
    > "$out/$model/$episode/case/worker.log" 2>&1 &
  printf '%s node=%s model=%s episode=%s pid=%s\n' "$(date -Is)" "$node" "$model" "$episode" "$!" >> "$out/batch_01.launches.log"
}
episode=52apMIyJVlc_s00176_n6_clean_v2
run auh7-1b-gpu-208 GPU-b0dca8a4c31bd66f veo31 "$episode"
run auh7-1b-gpu-209 GPU-4b239e1b43fc817b wan22 "$episode"
run auh7-1b-gpu-241 GPU-88c2b6b231e4a217 storymem "$episode"
wait
