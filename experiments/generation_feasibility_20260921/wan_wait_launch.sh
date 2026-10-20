#!/usr/bin/env bash
set -euo pipefail
cd /vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench
for attempt in $(seq 1 360); do
 if test -f EECBench/experiments/generation_feasibility_20260921/models/Wan2.2-T2V-A14B/download_complete.json; then
  date -u
  exec bash EECBench/experiments/generation_feasibility_20260921/run_wan_benchmark.sh --shots 4
 fi
 if (( attempt % 4 == 1 )); then echo "WAIT_MODEL attempt=$attempt"; date -u; fi
 sleep 15
done
exit 124
