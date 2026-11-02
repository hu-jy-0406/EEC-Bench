"""Assign the next independent-review batches (episodes cleaned, with review items, not yet assigned).

Usage: python3 next_review.py [N_BATCHES] [SIZE] [--allow-partial]
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 1
size = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 6
partial = '--allow-partial' in sys.argv
state_p = HERE / 'review_state.json'
st = json.loads(state_p.read_text())
ready = []
for j in json.loads((HERE / 'manifest.json').read_text())['episodes']:
    p = HERE / 'episodes' / j['episode_id'] / 'status.json'
    if p.exists():
        s = json.loads(p.read_text())
        if s['stage'] == 'cleaned' and s.get('review_items', 0) > 0 and j['episode_id'] not in st['assigned']:
            ready.append(j['episode_id'])
out = []
for _ in range(n):
    if len(ready) < size and not (partial and ready):
        break
    b, ready = ready[:size], ready[size:]
    st['assigned'] += b
    st['batches'].append(b)
    out.append(b)
state_p.write_text(json.dumps(st, indent=1))
for b in out:
    print('\n'.join(b))
    print('---')
print(f'remaining ready: {len(ready)}')
