"""Build corrected ops and a resolution file for one episode, then run `cleanup.py resolve`.

Usage: python3 resolve_helper.py SPEC_JSON
SPEC: {"episode_id": ..., "rulings": [{"ref": "O1", "decision": "adopt_review"|"keep_cleanup", "basis": ...}],
       "drop_ops": [indices of final ops to undo], "add_ops": [ops to append],
       "identity_replace": {"<1-based row>": row or null}, "identity_add": [rows]}
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = json.loads(Path(sys.argv[1]).read_text())
eid = spec['episode_id']
folder = HERE / 'episodes' / eid
ops = json.loads((folder / 'final_ops.json').read_text())
drop = set(spec.get('drop_ops', []))
remap = {}
kept = []
for i, op in enumerate(ops['ops']):
    if i not in drop:
        remap[i] = len(kept)
        kept.append(op)
for n in ops['notes']:
    old = n.get('ops', [])
    n['ops'] = [remap[i] for i in old if i in remap]
    if old and not n['ops'] and n['resolution'] in ('removed', 'narrowed'):
        n['resolution'] = 'kept_sole_reading'
        n['basis'] += ' [Main-session ruling: the change was undone after independent review.]'
ops['ops'] = kept + spec.get('add_ops', [])
rows = ops['identity']
for k, row in sorted(spec.get('identity_replace', {}).items(), key=lambda x: -int(x[0])):
    if row is None:
        rows.pop(int(k) - 1)
    else:
        rows[int(k) - 1] = row
rows += spec.get('identity_add', [])
(folder / 'ops_resolved.json').write_text(json.dumps(ops, ensure_ascii=False, indent=1))
(folder / 'resolution_input.json').write_text(json.dumps(dict(episode_id=eid, items=spec['rulings']), ensure_ascii=False, indent=1))
changed = any(r['decision'] == 'adopt_review' for r in spec['rulings'])
cmd = ['python3', '-I', str(HERE / 'cleanup.py'), 'check', eid, str(folder / 'ops_resolved.json')]
if subprocess.run(cmd).returncode:
    sys.exit('check failed')
cmd = ['python3', '-I', str(HERE / 'cleanup.py'), 'resolve', eid, str(folder / 'resolution_input.json')]
if changed:
    cmd.append(str(folder / 'ops_resolved.json'))
sys.exit(subprocess.run(cmd).returncode)
