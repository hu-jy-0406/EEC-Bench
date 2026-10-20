#!/usr/bin/env bash
set -euo pipefail
root=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench
out=$root/experiments/vl_vv_multimodel_four_episode_20260925
launch() {
  local node=$1 gpu=$2 uuid=$3 model=$4 ep=$5
  srun --jobid=214135 --overlap --nodes=1 --ntasks=1 --nodelist="$node" --cpus-per-task=8 \
    "$out/run_case.sh" "$out/$model/$ep/case" "$gpu" "$uuid" \
    > "$out/$model/$ep/case/worker.log" 2>&1 &
}
ep2=8iDEmCxXz-A_s00025_n6_clean_v2
ep3=9ugYT3Xc59s_s00093_n4_clean_v2
launch auh7-1b-gpu-208 0 GPU-b0dca8a4c31bd66f veo31 "$ep2"
launch auh7-1b-gpu-208 1 GPU-1ab83aef0da4b5a9 wan22 "$ep2"
launch auh7-1b-gpu-208 2 GPU-425a1b56db1d6091 storymem "$ep2"
launch auh7-1b-gpu-208 3 GPU-34da6e14e5faf110 holocine "$ep2"
launch auh7-1b-gpu-209 0 GPU-4b239e1b43fc817b veo31 "$ep3"
launch auh7-1b-gpu-209 1 GPU-01349b18dcb8d4fa wan22 "$ep3"
launch auh7-1b-gpu-209 2 GPU-2c7f4c8c046156c0 storymem "$ep3"
launch auh7-1b-gpu-209 3 GPU-d2218b471577c2c7 holocine "$ep3"
wait
