#!/usr/bin/env bash
set -euo pipefail
ROOT=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench
BASE=/vast/users/guangyi.chen/anaconda3/bin/python
OUT="$ROOT/EECBench/experiments/veo31_detection_agent_v1_20260924_cpu_r2"
SRC="$ROOT/EECBench/experiments/veo31_detection_agent_v1_20260924_r3"
LOAD="$ROOT/EECBench/scripts/openai_api_env.sh"
EPISODES=(
  52apMIyJVlc_s00176_n6_clean_v2
  8iDEmCxXz-A_s00025_n6_clean_v2
  9ugYT3Xc59s_s00093_n4_clean_v2
  Wl6COOA3V6Y_s00022_n4_clean_v2
)
run_api() { "$LOAD" "$BASE" "$@"; }
first="${EPISODES[0]}"
case="$OUT/$first/case"
if [[ ! -f "$case/episode_entities.json" ]]; then
  if [[ -d "$case/entities" && ! -d "$case/entities_retry" ]]; then
    run_api "$ROOT/EECBench/scripts/run_wedetect_shot_entities.py" \
      --manifest "$case/raw_manifest.json" --output "$case/entities_retry" \
      --detections "$case/entities/detections" --reuse-reviews "$case/entities" \
      --device cpu --model gpt-6-luna --reasoning low --shot-workers 3
    mv "$case/entities" "$case/entities_failed_initial"
    mv "$case/entities_retry" "$case/entities"
  fi
  if [[ ! -d "$case/entities" ]]; then
    echo "first case has no usable entity directory" >&2; exit 1
  fi
  run_api "$ROOT/EECBench/scripts/run_vl_vv_detection.py" detect --case "$case" --device cpu --shot-workers 3
  run_api "$ROOT/EECBench/scripts/run_vl_vv_detection.py" match --case "$case"
fi
for ep in "${EPISODES[@]:1}"; do
  case="$OUT/$ep/case"
  if [[ ! -d "$case" ]]; then
    mkdir -p "$(dirname "$case")"
    "$BASE" "$ROOT/EECBench/scripts/run_vl_vv_detection.py" prepare \
      --manifest "$SRC/$ep/case/raw_manifest.json" \
      --contract "$SRC/$ep/case/contract.json" --case "$case"
  fi
  if [[ ! -f "$case/episode_entities.json" ]]; then
    run_api "$ROOT/EECBench/scripts/run_vl_vv_detection.py" detect --case "$case" --device cpu --shot-workers 3
    run_api "$ROOT/EECBench/scripts/run_vl_vv_detection.py" match --case "$case"
  fi
done
