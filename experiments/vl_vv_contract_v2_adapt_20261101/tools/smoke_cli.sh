#!/bin/bash
# Command-line wiring of the default chain on a real contract: prepare, then a from-registry dry run. No model, no GPU.
set -euo pipefail
E=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench
PY=/vast/users/guangyi.chen/anaconda3/bin/python3
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
EP=tSF778Mi9sA_s00021_n4_clean_v2
C=$($PY -c "import sys; sys.path.insert(0,'$E/scripts'); import episode_contract as c; print(c.resolve_v2_contract('$EP'))")
echo "resolved: $C"
$PY - "$C" "$T" <<'P'
import hashlib, json, sys
from pathlib import Path
contract, root = json.loads(Path(sys.argv[1]).read_text()), Path(sys.argv[2])
shots = []
for block in contract['shots']:
    frames = []
    for i in range(6):
        path = root / f'{block["shot_id"]}_{i}.jpg'; path.write_bytes(f'{block["shot_id"]}{i}'.encode())
        frames.append(dict(frame_id=i, timestamp_sec=i * .8, path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    shots.append(dict(shot_id=block['shot_id'], source_scope='shot', frames=frames))
(root / 'manifest.json').write_text(json.dumps(dict(episode_id=contract['episode_id'], shots=shots)))
P
$PY "$E/scripts/run_vl_vv_detection.py" prepare --manifest "$T/manifest.json" --contract "$C" --case "$T/case"
ls "$T/case"
$PY - "$T/case" <<'P'
import json, sys
from pathlib import Path
case = Path(sys.argv[1])
state = json.loads((case / 'run.json').read_text()); state['status'] = 'complete'
(case / 'run.json').write_text(json.dumps(state))
(case / 'episode_entities.json').write_text(json.dumps(dict(protocol='vl_vv_detection_v1', status='matched')))
registry = json.loads((case / 'prompt_registry.json').read_text())
print('registry', registry['source'], len(registry['entities']), 'contract_format', state['contract_format'])
P
$PY "$E/scripts/run_vl_vv_pipeline.py" --case "$T/case" --output "$T/run" --mode from-registry --dry-run | $PY -c "import json,sys; p=json.load(sys.stdin); print(p['discovery_protocol'],p['review_protocol'],p['scoring_protocol'],[s['name'] for s in p['stages']],'allow_v1',p['allow_v1_contract'])"
if $PY "$E/scripts/run_vl_vv_pipeline.py" --case "$T/case" --output "$T/run2" --mode from-registry --dry-run --discovery-protocol v4 >/dev/null 2>"$T/err"; then echo "older chain NOT refused"; exit 1; else tail -1 "$T/err"; fi
$PY "$E/experiments/vl_vv_multimodel_first200_20260926/prepare_case.py" --help | grep -A1 contract-format | head -3
echo SMOKE_OK
