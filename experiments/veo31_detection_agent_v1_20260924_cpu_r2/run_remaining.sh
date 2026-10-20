#!/usr/bin/env bash
set -euo pipefail
ROOT=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench
BASE=/vast/users/guangyi.chen/anaconda3/bin/python
OUT="$ROOT/EECBench/experiments/veo31_detection_agent_v1_20260924_cpu_r2"
SRC="$ROOT/EECBench/experiments/veo31_detection_agent_v1_20260924_r3"
LOAD="$ROOT/EECBench/scripts/openai_api_env.sh"
for ep in 8iDEmCxXz-A_s00025_n6_clean_v2 9ugYT3Xc59s_s00093_n4_clean_v2 Wl6COOA3V6Y_s00022_n4_clean_v2; do
  case="$OUT/$ep/case"
  start=$(date +%s)
  mkdir -p "$(dirname "$case")"
  "$BASE" "$ROOT/EECBench/scripts/run_vl_vv_detection.py" prepare --manifest "$SRC/$ep/case/raw_manifest.json" --contract "$SRC/$ep/case/contract.json" --case "$case"
  "$LOAD" "$BASE" "$ROOT/EECBench/scripts/run_vl_vv_detection.py" detect --case "$case" --device cpu --shot-workers 3
  "$LOAD" "$BASE" "$ROOT/EECBench/scripts/run_vl_vv_detection.py" match --case "$case"
  end=$(date +%s)
  "$BASE" - "$case/execution.json" "$start" "$end" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]); start=float(sys.argv[2]); end=float(sys.argv[3])
p.write_text(json.dumps({'status':'success','started_unix':start,'finished_unix':end,'elapsed_seconds':end-start},indent=2)+'\n')
PY
done
