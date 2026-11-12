#!/usr/bin/env python3
"""List episodes of the granularity pass that are reviewed with open disagreements and not yet given to a resolution
agent (g_resolve_assigned.json); --assign N marks the first N as assigned and prints them."""
import json
import sys
from pathlib import Path

import cleanup as C

HERE = Path(__file__).resolve().parent
ASSIGNED = HERE / 'g_resolve_assigned.json'
assigned = json.loads(ASSIGNED.read_text()) if ASSIGNED.is_file() else {}
rows = []
for j in C.manifest()['episodes']:
    st = C.read(HERE / 'episodes' / j['episode_id'] / 'status.json').get('g') or {}
    if st.get('stage') == 'reviewed' and st.get('disagreements') and j['episode_id'] not in assigned:
        rows.append((j['episode_id'], len(st['disagreements'])))
if len(sys.argv) > 2 and sys.argv[1] == '--assign':
    take = rows[:int(sys.argv[2])]
    for eid, _ in take:
        assigned[eid] = sys.argv[3] if len(sys.argv) > 3 else 'agent'
    ASSIGNED.write_text(json.dumps(assigned, indent=1) + '\n')
    print(' '.join(eid for eid, _ in take))
else:
    print(len(rows), 'open, unassigned;', sum(n for _, n in rows), 'refs')
    for eid, n in rows:
        print(eid, n)
