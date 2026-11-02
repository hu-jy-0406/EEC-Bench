#!/bin/bash
# Back up every contract file before camera_moves_third.json is applied.
set -euo pipefail
E=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench
X=$E/experiments/vl_vv_contract_v2_adapt_20261101
B=$X/source_before_third
[ -e "$B" ] && { echo "source_before_third already exists"; exit 1; }
mkdir -p "$B"
cd "$E"
V=experiments/episode_contracts_v2_20261029
C=experiments/contract_cleanup_20261031
LIST=$B/contract_data_files.txt
{
  find $V/deliverables -type f
  find $V/episodes -type f \( -name contract.json -o -name contract_with_evidence.json -o -name claim_accounting.json -o -name review.md -o -name final_decisions.json -o -name status.json -o -name meta.json \)
  find $C/deliverables -type f
  find $C/episodes -type f \( -name contract.json -o -name contract_with_evidence.json -o -name review.md -o -name final_ops.json -o -name cleanup_log.json -o -name status.json \)
  echo $C/manifest.json
} | sort > "$LIST"
wc -l "$LIST"
tar -czf "$B/contract_data_before.tar.gz" -T "$LIST"
( cd "$B" && sha256sum contract_data_before.tar.gz contract_data_files.txt > SHA256SUMS )
du -sh "$B"
