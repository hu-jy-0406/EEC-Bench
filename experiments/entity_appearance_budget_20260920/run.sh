#!/usr/bin/env bash
set -euo pipefail
cd /vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench
export CUDA_VISIBLE_DEVICES= HIP_VISIBLE_DEVICES= ROCR_VISIBLE_DEVICES= OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
hostname
uptime
ps -eo user,pid,pcpu,pmem,comm --sort=-pcpu | head -n 12 || true
PY=/vast/users/guangyi.chen/anaconda3/bin/python
SCRIPT=EECBench/scripts/gs_entity_appearance_budget.py
OUT=EECBench/experiments/entity_appearance_budget_20260920
mkdir -p "$OUT/source_snapshot"
cp "$SCRIPT" EECBench/prompts/appearance/entity_budget_v5.txt EECBench/tests/test_gs_entity_appearance_budget.py "$OUT/source_snapshot/"
"$PY" "$SCRIPT" prepare --source EECBench/experiments/entity_appearance_minimal_20260920/study2 --out "$OUT/study2"
"$PY" "$SCRIPT" prepare --source EECBench/experiments/entity_appearance_minimal_20260920/study3 --out "$OUT/study3"
"$PY" "$SCRIPT" score --runs "$OUT/study2" "$OUT/study3" --workers 3
"$PY" "$SCRIPT" report --runs "$OUT/study2" "$OUT/study3" --out "$OUT/results.json"
