#!/usr/bin/env python3
"""Consistency audit of the granularity pass (zero model calls): shots whose own text uses a place adjective that
names a wall or floor covering ("peach-walled", "wood-paneled", "carpeted"; ruling added 2026-11-11 after some
reviews had started) while no wall/paneling/carpet entity of the pass is listed in that shot. Prints candidates for
a manual or agent check."""
import json
import re
from pathlib import Path

import cleanup as C

HERE = Path(__file__).resolve().parent
RX = re.compile(r"\b([\w-]*-walled|walled|[\w-]*-paneled|paneled|panelled|carpeted)\b", re.I)
WALLISH = re.compile(r"wall|panel|carpet|rug", re.I)
rows = []
for j in C.manifest()['episodes']:
    eid = j['episode_id']
    c = C.read(HERE / 'episodes' / eid / 'contract_with_evidence.json')
    texts = {s['shot_id']: s['text'] for s in c['prompt']['shots']}
    ents = c['entity_descriptions']
    for s in c['shots']:
        words = sorted({m.group(0) for m in RX.finditer(texts.get(s['shot_id'], ''))})
        if not words:
            continue
        listed = [ents[str(k)]['name'] for k in s['presence'] if WALLISH.search(ents[str(k)]['name'])]
        if not listed:
            rows.append(dict(episode=eid, shot=s['shot_id'], words=words))
print(len(rows), 'shots with a wall/carpet adjective and no wall/carpet entity listed')
for r in rows:
    print(r['episode'], r['shot'], r['words'])
Path(HERE / 'g_20261111').mkdir(exist_ok=True)
(HERE / 'g_20261111' / 'audit_place_adjectives.json').write_text(json.dumps(rows, indent=1) + '\n')
