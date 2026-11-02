#!/bin/bash
# Keep copies of every source and contract file before the v2 adaptation changes them.
set -euo pipefail
E=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench
X=$E/experiments/vl_vv_contract_v2_adapt_20261101
B=$X/source_before
[ -e "$B" ] && { echo "source_before already exists"; exit 1; }
mkdir -p "$B"
cd "$E"
FILES="scripts/vl_vv_branch_common.py scripts/run_vl_vv_detection.py scripts/run_vl_vv_branch_detection.py scripts/run_vl_vv_branch_review.py
scripts/run_vl_vv_pipeline.py scripts/run_vl_vv_issue_discovery.py scripts/run_vl_vv_issue_review.py scripts/build_vl_vv_branch_schemas.py
prompts/vl_vv_issue_discovery_v5_vl.txt prompts/vl_vv_issue_discovery_v5_vv.txt prompts/vl_vv_issue_review_v6_vl.txt prompts/vl_vv_issue_review_v6_vv.txt
prompts/vl_vv_branch_definitions_v1.txt configs/vl-vv-branch-v1.json
schemas/vl-vv-issue-discovery-v5-vl.schema.json schemas/vl-vv-issue-discovery-v5-vv.schema.json schemas/vl-vv-issue-review-v6-vl.schema.json
schemas/vl-vv-issue-review-v6-vv.schema.json schemas/vl-vv-branch-records-v1.schema.json
docs/episode-contract-v2-format.md docs/vl-vv-branch-pipeline-v1.md docs/vl-vv-detection-agent-v1.md docs/open-questions.md
experiments/vl_vv_multimodel_first200_20260926/prepare_case.py experiments/vl_vv_multimodel_first200_20260926/run_batch.py
experiments/episode_contracts_v2_20261029/rewrite.py experiments/episode_contracts_v2_20261029/rules_v2.txt experiments/episode_contracts_v2_20261029/audit_v2.txt experiments/episode_contracts_v2_20261029/README.md
experiments/contract_cleanup_20261031/cleanup.py experiments/contract_cleanup_20261031/direction_pass.py experiments/contract_cleanup_20261031/rules_cleanup.txt experiments/contract_cleanup_20261031/rules_review.txt
experiments/contract_cleanup_20261031/manifest.json experiments/contract_cleanup_20261031/README.md"
for f in $FILES; do mkdir -p "$B/$(dirname "$f")"; cp -p "$f" "$B/$f"; done
cp -p tests/test_vl_vv_*.py "$B/" 2>/dev/null || true
mkdir -p "$B/tests"; mv "$B"/test_vl_vv_*.py "$B/tests/"
V=experiments/episode_contracts_v2_20261029
C=experiments/contract_cleanup_20261031
LIST=$X/source_before/contract_data_files.txt
{
  find $V/deliverables -type f
  find $V/episodes -type f \( -name contract.json -o -name contract_with_evidence.json -o -name review.md -o -name final_decisions.json -o -name status.json -o -name meta.json \)
  find $C/deliverables -type f
  find $C/episodes -type f \( -name contract.json -o -name contract_with_evidence.json -o -name review.md -o -name final_ops.json -o -name cleanup_log.json -o -name status.json \)
} | sort > "$LIST"
wc -l "$LIST"
tar -czf "$B/contract_data_before.tar.gz" -T "$LIST"
xargs -a "$LIST" -d '\n' sha256sum > "$B/contract_data_files.sha256"
( cd "$B" && find . -type f ! -name SHA256SUMS ! -name contract_data_before.tar.gz -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS; sha256sum contract_data_before.tar.gz >> SHA256SUMS )
du -sh "$B"; wc -l "$B/SHA256SUMS" "$B/contract_data_files.sha256"
