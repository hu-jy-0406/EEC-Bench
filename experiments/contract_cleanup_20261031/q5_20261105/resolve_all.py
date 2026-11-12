#!/usr/bin/env python3
"""Record the main session's Q5 rulings (rulings.json) for every episode that is ready.

An episode whose rulings are all keep_q5 is resolved without a contract change; one with adopt_review items
needs episodes/<id>/q5_ops_corrected.json (written by a correction agent and passing check), with which
q5_pass.py resolve re-applies the pass. Episodes already resolved are skipped. Prints one line per episode.
Usage: resolve_all.py
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLEANUP = HERE.parent
rulings = json.loads((HERE / 'rulings.json').read_text())
(HERE / 'resolutions').mkdir(exist_ok=True)
for eid, row in rulings.items():
    folder = CLEANUP / 'episodes' / eid
    q = json.loads((folder / 'status.json').read_text()).get('q5', {})
    if q.get('stage') == 'resolved':
        continue
    adopt = any(x['decision'] == 'adopt_review' for x in row['items'])
    corrected = folder / 'q5_ops_corrected.json'
    if adopt and not corrected.is_file():
        print(eid, 'waiting for corrected ops')
        continue
    res = HERE / 'resolutions' / f'{eid}.json'
    res.write_text(json.dumps(dict(episode_id=eid, producer='main_session_opus', instructions=row['instructions'],
                                   items=row['items']), ensure_ascii=False, indent=1))
    cmd = ['nice', '-n', '19', sys.executable, 'q5_pass.py', 'resolve', '--', eid, str(res)] + ([str(corrected)] if adopt else [])
    out = subprocess.run(cmd, cwd=CLEANUP, capture_output=True, text=True)
    print(eid, (out.stdout.strip().splitlines() or [''])[-1][:80], out.stderr.strip()[-300:])
