"""Camera values that still refer to another shot after the moves, by kind, for the owner."""
import json
import re
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parents[1] / 'scripts'))
import episode_contract as contract_io  # noqa: E402
QUEUE = HERE.parents[1] / 'experiments/source_video_priority_20260921/generation_queue_400.ids.txt'
GROUPS = (('names_a_shot', re.compile(r'\bShot ?\d|\b(previous|preceding|next|prior) shots?\b', re.I)),
          ('refers_to_an_earlier_view', re.compile(r'\b(earlier|established|as before|than before|return|returns|returning|preserved|repeating|'
                                                   r'again|same [\w-]* ?[\w-]* ?(view|composition|framing)|another view)\b', re.I)),
          ('reverse_or_opposite_view', re.compile(r'\b(reverse|opposing|opposite side|other side)\b', re.I)))
rows = []
for eid in [x.strip() for x in QUEUE.read_text().splitlines() if x.strip()]:
    path = contract_io.resolve_v2_contract(eid)
    contract = contract_io.model_facing(contract_io.read(path))
    for block in contract['shots']:
        for field in ('camera_view', 'camera_movement'):
            text = block['shot_description'][field]
            for name, pattern in GROUPS if text else ():
                if pattern.search(text):
                    rows.append(dict(kind=name, episode_id=eid, contract='cleaned' if 'contract_cleanup' in str(path) else 'v2_rewrite',
                                     shot_id=block['shot_id'], field=field, value=text))
                    break
(HERE / 'camera_remaining.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
import collections
print(collections.Counter((r['kind'], r['contract']) for r in rows))
for r in rows:
    if r['kind'] != 'reverse_or_opposite_view':
        print(r['kind'][:8], r['contract'][:7], r['episode_id'][:22], r['shot_id'], r['field'][7:], '|', r['value'][:120])
