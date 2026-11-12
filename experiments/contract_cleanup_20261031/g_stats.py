#!/usr/bin/env python3
"""Before/after numbers of the granularity pass (contracts 1-200): entities by label and origin, presence entries,
requirements, and the compiled requirement lists (V-L checking rows). Zero model calls. Writes g_20261111/stats.json."""
import collections
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMP = HERE.parents[0] / 'compiled_requirements_20261105'


def load(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]


def summary(rows):
    s = collections.Counter()
    for c in rows:
        ents = c['entity_descriptions']
        s['episodes'] += 1
        s['entities'] += len(ents)
        for e in ents.values():
            s[f"label_{e['label']}"] += 1
            if e.get('origin') == 'granularity_pass_20261111':
                s['new_entities'] += 1
                s[f"new_{(e.get('cleanup') or {}).get('added', '?')}"] += 1
        for sh in c['shots']:
            s['presence_entries'] += len(sh['presence'])
            s['absent_entries'] += len(sh['absent'])
            for d in ('appearance', 'spatial', 'motion'):
                s['requirements'] += len(sh[d])
        s['cross_shot'] += len(c['cross_shot'])
    return dict(s)


def compiled(root, ids):
    s = collections.Counter()
    for eid in ids:
        r = json.loads((root / eid / 'requirements.json').read_text())
        for k, v in r.items():
            if isinstance(v, list):
                s[f'list_{k}'] += len(v)
    return dict(s)


before = load(HERE / 'g_20261111/deliverables_before/contracts_1_200_with_evidence.jsonl')
after = load(HERE / 'deliverables/contracts_1_200_with_evidence.jsonl')
ids = [c['episode_id'] for c in after]
out = dict(before=summary(before), after=summary(after),
           compiled_before=compiled(HERE / 'g_20261111/compiled_before', ids), compiled_after=compiled(COMP / 'compiled', ids))
(HERE / 'g_20261111/stats.json').write_text(json.dumps(out, indent=1) + '\n')
print(json.dumps(out, indent=1))
