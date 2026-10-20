#!/usr/bin/env python3
"""Validate saved files independently of selection feature/flow functions."""
import collections
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
manifest = json.loads((HERE / 'selection_manifest.json').read_text())
audit = json.loads((HERE / 'audit.json').read_text())
source_bytes = Path(audit['source']).read_bytes()
source_rows = [json.loads(line) for line in source_bytes.splitlines()]
source_lines = {json.loads(line)['episode_id']: line for line in source_bytes.splitlines(keepends=True)}
loaded = {}
checks = {}
for name, expected_count in [('core_100', 100), ('priority_200', 200),
                              ('stage2_additional_100', 100), ('stage3_remaining_200', 200),
                              ('generation_queue_400', 400)]:
    raw = (HERE / (name + '.jsonl')).read_bytes()
    rows = [json.loads(line) for line in raw.splitlines()]
    loaded[name] = rows
    checks[name + '/count_unique'] = len(rows) == len({r['episode_id'] for r in rows}) == expected_count
    checks[name + '/unchanged_bytes'] = all(source_lines[json.loads(line)['episode_id']] == line for line in raw.splitlines(keepends=True))
    checks[name + '/recorded_hash'] = hashlib.sha256(raw).hexdigest() == manifest['files'][name]['sha256']
    counts = collections.Counter((r['source']['dataset'], r['shot_count'], r['target_duration_seconds']) for r in rows)
    checks[name + '/joint_distribution'] = counts == {
        (s, k, k * 5): expected_count * fraction // 20
        for s in ['muss', 'sf20k'] for k, fraction in [(4, 6), (6, 3), (8, 1)]}
    checks[name + '/ids_sidecar'] = (HERE / (name + '.ids.txt')).read_text().splitlines() == [r['episode_id'] for r in rows]
queue = loaded['generation_queue_400']
checks['nested_prefixes'] = queue[:100] == loaded['core_100'] and queue[:200] == loaded['priority_200']
checks['disjoint_incremental_stages'] = queue[100:200] == loaded['stage2_additional_100'] and queue[200:] == loaded['stage3_remaining_200']
checks['full_population'] = {r['episode_id'] for r in queue} == set(source_lines)
checks['original_source_hash'] = hashlib.sha256(source_bytes).hexdigest() == manifest['source_sha256']
checks['selector_script_hash'] = hashlib.sha256((HERE / 'select_priority.py').read_bytes()).hexdigest() == manifest['script_sha256']
checks['core_work_cap'] = max(collections.Counter(r['source_work_key'] for r in queue[:100]).values()) == 1
checks['priority_work_cap'] = max(collections.Counter(r['source_work_key'] for r in queue[:200]).values()) <= 2
for size, expected in [(100, (86, 12, 2)), (200, (173, 24, 3)), (400, (345, 48, 7))]:
    counts = collections.Counter(r['source_type'] for r in queue[:size])
    checks[f'styles_{size}'] = tuple(counts[k] for k in ['live_action_narrative', 'animation', 'documentary']) == expected
for start in range(0, 400, 20):
    counts = collections.Counter((r['source']['dataset'], r['shot_count']) for r in queue[start:start+20])
    checks[f'balanced_block_{start//20+1}'] = counts == {(s, k): q for s in ['muss', 'sf20k'] for k, q in [(4, 6), (6, 3), (8, 1)]}
ranking = [json.loads(line) for line in (HERE / 'ranking.jsonl').read_text().splitlines()]
checks['ranking_matches_queue'] = len(ranking) == 400 and all(
    r['generation_rank'] == i + 1 and r['episode_id'] == x['episode_id']
    and r['priority_stage'] == (1 if i < 100 else 2 if i < 200 else 3)
    and r['original_record_sha256'] == hashlib.sha256(source_lines[x['episode_id']]).hexdigest()
    for i, (r, x) in enumerate(zip(ranking, queue)))
checks['review_status_preserved'] = all(not r['human_review_complete'] for r in queue)
result = {'passed': all(checks.values()), 'checks_count': len(checks), 'checks': checks,
          'source_sha256': manifest['source_sha256'], 'generation_queue_sha256': manifest['files']['generation_queue_400']['sha256'],
          'model_calls': 0, 'tokens': 0, 'api_usd': 0}
(HERE / 'independent_validation.json').write_text(json.dumps(result, indent=2) + '\n')
assert result['passed'], [name for name, ok in checks.items() if not ok]
print(json.dumps({k: v for k, v in result.items() if k != 'checks'}, indent=2))
