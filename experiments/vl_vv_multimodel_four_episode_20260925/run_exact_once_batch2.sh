#!/usr/bin/env bash
set -euo pipefail
root=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench
out=$root/experiments/vl_vv_multimodel_four_episode_exact_once_rerun_20260925
run(){ srun --jobid=214135 --overlap --nodes=1 --ntasks=1 --nodelist="$1" --cpus-per-task=8 "$root/experiments/vl_vv_multimodel_four_episode_20260925/run_case.sh" "$out/$4/$5/case" "$2" "$3" > "$out/$4/$5/case/worker.log" 2>&1 &
}
e1=9ugYT3Xc59s_s00093_n4_clean_v2; e2=Wl6COOA3V6Y_s00022_n4_clean_v2
run auh7-1b-gpu-208 0 GPU-b0dca8a4c31bd66f veo31 "$e1"
run auh7-1b-gpu-208 1 GPU-1ab83aef0da4b5a9 wan22 "$e1"
run auh7-1b-gpu-208 2 GPU-425a1b56db1d6091 storymem "$e1"
run auh7-1b-gpu-208 3 GPU-34da6e14e5faf110 holocine "$e1"
run auh7-1b-gpu-209 0 GPU-4b239e1b43fc817b veo31 "$e2"
run auh7-1b-gpu-209 1 GPU-01349b18dcb8d4fa wan22 "$e2"
run auh7-1b-gpu-209 2 GPU-2c7f4c8c046156c0 storymem "$e2"
run auh7-1b-gpu-209 3 GPU-d2218b471577c2c7 holocine "$e2"
wait
