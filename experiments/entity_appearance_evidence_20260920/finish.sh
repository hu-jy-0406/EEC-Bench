#!/usr/bin/env bash
set -euo pipefail
cd /vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench
export CUDA_VISIBLE_DEVICES= HIP_VISIBLE_DEVICES= ROCR_VISIBLE_DEVICES= OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
PY=/vast/users/guangyi.chen/anaconda3/bin/python
OUT=EECBench/experiments/entity_appearance_evidence_20260920
"$PY" "$OUT/reconcile_evidence.py"
"$PY" -m unittest discover -s EECBench/tests -p 'test_gs_entity_appearance*.py'
cp EECBench/tests/test_gs_entity_appearance_evidence.py "$OUT/source_snapshot/test_gs_entity_appearance_evidence_final.py"
"$PY" EECBench/scripts/gs_entity_appearance_evidence.py score --runs "$OUT/study2" "$OUT/study3" --workers 1
"$PY" EECBench/scripts/gs_entity_appearance_evidence.py report --runs "$OUT/study2" "$OUT/study3" --out "$OUT/results.json"
"$PY" "$OUT/audit_report.py"
