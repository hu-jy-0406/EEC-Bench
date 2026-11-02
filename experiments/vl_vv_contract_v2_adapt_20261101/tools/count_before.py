"""Requirement counts of the cleaned 200 in the backup (before this task) and now."""
import collections, json, tarfile
from pathlib import Path
HERE = Path(__file__).resolve().parents[1]
E = HERE.parents[1]
REL = 'experiments/contract_cleanup_20261031/deliverables/contracts_1_200.jsonl'
def count(lines):
    c = collections.Counter()
    for line in lines:
        k = json.loads(line)
        c['contracts'] += 1; c['entities'] += len(k['entity_descriptions']); c['cross_shot'] += len(k['cross_shot'])
        for s in k['shots']:
            c['presence'] += len(s['presence']); c['absent'] += len(s['absent'])
            c['camera_view'] += s['shot_description']['camera_view'] is not None
            c['camera_movement'] += s['shot_description']['camera_movement'] is not None
            for d in ('appearance', 'spatial', 'motion'):
                c[d] += len(s[d])
    return dict(sorted(c.items()))
with tarfile.open(HERE / 'source_before/contract_data_before.tar.gz') as t:
    print('before', count(t.extractfile(REL).read().decode().splitlines()))
print('now   ', count((E / REL).read_text().splitlines()))
