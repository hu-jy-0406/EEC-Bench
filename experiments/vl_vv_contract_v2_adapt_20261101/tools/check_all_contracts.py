#!/usr/bin/env python3
"""Run every current contract through the evaluator's v2 read path (no model, no video)."""
import collections
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
E = HERE.parents[1]
sys.path.insert(0, str(E / 'scripts'))
import episode_contract as contract_io  # noqa: E402
import gs_prompt_binding as binding  # noqa: E402
import run_vl_vv_detection as frontend  # noqa: E402
import run_vl_vv_issue_discovery as discovery  # noqa: E402
import vl_vv_branch_common as common  # noqa: E402

QUEUE = E / 'experiments/source_video_priority_20260921/generation_queue_400.ids.txt'
TASKS = E / 'experiments/vl_vv_multimodel_first200_20260926'


def counts(contract):
    row = collections.Counter(entities=len(contract['entity_descriptions']), cross_shot=len(contract['cross_shot']))
    row['episodes_with_style'] += any(block['shot_description']['style'] for block in contract['shots'])
    for block in contract['shots']:
        row['shots'] += 1
        row['presence'] += len(block['presence'])
        row['absent'] += len(block['absent'])
        row['camera_view'] += block['shot_description']['camera_view'] is not None
        row['camera_movement'] += block['shot_description']['camera_movement'] is not None
        row['style'] += block['shot_description']['style'] is not None
        for dim in contract_io.SHOT_REQUIREMENTS:
            row[dim] += len(block[dim])
    return row


def main():
    ids = [x.strip() for x in QUEUE.read_text().splitlines() if x.strip()]
    totals = {'cleaned_1_200': collections.Counter(), 'all_400_current': collections.Counter()}
    rows_per_episode, kinds, problems = [], collections.Counter(), []
    sources = collections.Counter()
    for index, eid in enumerate(ids):
        path = contract_io.resolve_v2_contract(eid)
        sources['cleaned' if 'contract_cleanup' in str(path) else 'v2_rewrite'] += 1
        try:
            contract, prompt = contract_io.split_v2(contract_io.read(path))
            shots = [dict(shot_id=block['shot_id'], frames=[dict(frame_id=i) for i in range(6)]) for block in contract['shots']]
            shot_ids = [s['shot_id'] for s in shots]
            contract_io.validate_v2(contract, prompt, shot_ids)
            memory = dict(contract, prompt=prompt)
            registry = frontend.normalize_contract(memory, shots)
            narrative = dict(facts=[dict(fact_id=sid, shot_id=sid, text='; '.join(
                e['name'] for e in registry['entities'] if next(x for x in e['schedule'] if x['shot_id'] == sid)['expectation'] == 'required')
                or '(no scheduled entities)') for sid in shot_ids])
            binding.validate_registry(registry, shots, narrative)
            ledger = dict(prompt_bound=[dict(global_entity_id=f'pb{i:04d}', prompt_entity_id=e['prompt_entity_id'], name=e['name'])
                                        for i, e in enumerate(registry['entities'], 1)], prompt_unbound=[])
            manifest = dict(shots=shots)
            template = common.contract_template(memory, ledger, manifest, common.cut_boundaries(manifest))
            common.text_sources(memory, common.cut_boundaries(manifest))
            discovery.required_continuity_subjects(memory, ledger, manifest)
            common.required_shot_characters(memory, ledger, manifest)
            common.place_entity_ids(memory, ledger)
            contract_io.shot_settings(memory)
            frontend.match_v2_payload(shots, registry, [], memory, *frontend.match_v2_tags(registry, []))
            placed = [item['item_id'] for row in template for item in row['items']
                      if item['kind'] == 'requirement' and item['predicate'] not in ('present', 'absent')]
            want = [item['id'] for block in contract['shots'] for dim in contract_io.SHOT_REQUIREMENTS for item in block[dim]]
            want += [item['id'] for item in contract['cross_shot']]
            assert sorted(placed) == sorted(want), 'requirements lost or duplicated'
            empty = [row['row_id'] for row in template if not row['items']]
            assert not empty, empty
            rows_per_episode.append(len(template))
            kinds.update(row['kind'] for row in template)
            totals['all_400_current'].update(counts(contract))
            if index < 200:
                totals['cleaned_1_200'].update(counts(contract))
            if contract.get('unresolved'):
                sources['with_unresolved_field'] += 1
        except Exception as exc:  # report every failing episode, not only the first
            problems.append(f'{eid}: {exc!r}')
    task_shots = collections.Counter()
    for task_file in sorted((TASKS / 'batch').glob('*.json*')):
        text = task_file.read_text()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = [json.loads(line) for line in text.splitlines() if line.strip()]
        for task in (data if isinstance(data, list) else data.get('tasks', [])):
            if not isinstance(task, dict) or 'shots' not in task:
                continue
            contract = contract_io.read(contract_io.resolve_v2_contract(task['episode_id']))
            same = [s['shot_id'] for s in task['shots']] == [b['shot_id'] for b in contract['shots']]
            task_shots['shot_ids_match' if same else 'shot_ids_differ'] += 1
    result = dict(episodes=len(ids), sources=dict(sources), problems=problems, totals={k: dict(v) for k, v in totals.items()},
                  template_rows=dict(by_kind=dict(kinds), mean_per_episode=statistics.mean(rows_per_episode),
                                     max_per_episode=max(rows_per_episode)), first200_task_shot_ids=dict(task_shots))
    (HERE / 'contract_read_check.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
