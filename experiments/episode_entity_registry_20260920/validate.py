"""CPU-only validation/export of frozen Study2; no model calls or GPU imports."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

BASE = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / 'scripts'))
from gs_episode_entities import export_registry

patterns = ['test_gs_episode_entities.py', 'test_gs_temporal.py',
            'test_wedetect_shot_entities.py', 'test_gs_integrated.py']
checks = []
for pattern in patterns:
    command = [sys.executable, '-m', 'unittest', 'discover', '-s', str(BASE / 'tests'), '-p', pattern, '-v']
    proc = subprocess.run(command, text=True, capture_output=True)
    (OUT / (pattern + '.log')).write_text(proc.stdout + proc.stderr)
    checks.append(dict(test=pattern, returncode=proc.returncode))
    print(pattern, proc.returncode, flush=True)
    if proc.returncode:
        print(proc.stdout + proc.stderr)
        raise SystemExit(proc.returncode)
source = BASE / 'experiments/temporal_v2_study234_revised_20260920/study2'
result = export_registry(source, OUT / 'study2')
lookup = result['local_to_global']
assert lookup['shot1/e2'] == lookup['shot3/e2']
assert lookup['shot1/e11'] != lookup['shot3/e13']
assert lookup['shot1/e18'] != lookup['shot3/e18']
rows = {e['global_entity_id']: e for e in result['entities']}
assert rows[lookup['shot1/e3']]['observed_shot_ids'] == ['shot1']
assert rows[lookup['shot1/e11']]['observed_shot_ids'] == ['shot1']
assert rows[lookup['shot3/e13']]['observed_shot_ids'] == ['shot3']
assert len([k for k in lookup if k.startswith('shot2/')]) == 6
assert result['counts'] == dict(local_entities=46, global_records=38, confirmed_links=8, unresolved_links=2)
for path, digest in result['source_hashes'].items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
validation = dict(status='passed', tests=checks, study2_counts=result['counts'],
                  source_hashes_unchanged=True, model_calls=0, gpu_work=False,
                  scope='Registry export on historical identities. New clustering prompt has not been model-evaluated.')
(OUT / 'validation.json').write_text(json.dumps(validation, indent=2) + '\n')
print(json.dumps(validation), flush=True)
