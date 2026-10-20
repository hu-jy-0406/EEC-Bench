#!/usr/bin/env python3
"""Extract spatial relations with one fresh Codex subagent per completed shot."""
import argparse
import copy
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from itertools import combinations
import json
from pathlib import Path
import shutil
import socket
import tempfile
import time

import run_wedetect_shot_entities as entities

ROOT = entities.ROOT
PROMPT = ROOT / 'EECBench/prompts/shot_spatial_relations_v0.1.txt'
SCHEMA = ROOT / 'EECBench/schemas/shot_spatial_relations.v0.1.schema.json'
VERSION = 'spatial_v0.1'
PREDICATES = ('supported_by', 'inside', 'attached_to', 'touching', 'above', 'in_front_of')
STATES = ('present', 'absent', 'uncertain', 'not_observable')
REFERENCE = {p: 'intrinsic' for p in PREDICATES}
REFERENCE.update(above='gravity', in_front_of='camera')


def load_inputs(source, allow_running=False):
    """Require completed, hash-verified entity outputs; never re-run clustering."""
    state = entities.read(source / 'run.json')
    if state['status'] != 'success' and not (allow_running and state['status'] == 'running'):
        raise ValueError('Entity run must have completed successfully')
    manifest = entities.read(source / 'manifest.json')
    shots = copy.deepcopy(manifest['shots'])
    expected_hashes = {(s['shot_id'], f['frame_id']): f['sha256']
                       for s in shots for f in s['frames']}
    shots = entities.load_manifest(source / 'manifest.json')
    records = {r['shot_id']: r for r in state['shots']}
    inputs = []
    for shot in shots:
        sid = shot['shot_id']
        record = records.get(sid, {})
        directory = source / 'shots' / sid
        path = directory / 'entities.json'
        if record.get('status') != 'success' or entities.sha(path) != record.get('output_sha256'):
            raise ValueError('Incomplete or changed entity output: ' + sid)
        frozen = entities.read(path)
        raw = entities.read(directory / 'response.json')
        detector_input = entities.read(directory / 'input.json')
        if (detector_input['shot_id'] != sid or
                [f['frame_id'] for f in shot['frames']] !=
                [f['frame_id'] for f in detector_input['frames']]):
            raise ValueError('Frozen shot/frame coverage changed: ' + sid)
        validated = entities.validate_result(raw, detector_input)
        # Earlier final files have two redundant booleans and no box summary.
        # Require all semantic fields to match; materialize current summaries in
        # the downstream copy only, leaving original experimental files intact.
        keys = ('entity_id', 'name', 'candidate_ids', 'observations',
                'exist_frame_ids', 'visible_frame_ids')
        expected = [{k: e[k] for k in keys} for e in validated['entities']]
        observed = [{k: e[k] for k in keys} for e in frozen['entities']]
        if (expected != observed or frozen['shot_id'] != sid or
                frozen['rejected_detections'] != validated['rejected_detections']):
            raise ValueError('Entity response does not match frozen final output')
        frame_info = {f['frame_id']: f for f in detector_input['frames']}
        for frame in shot['frames']:
            info = frame_info[frame['frame_id']]
            if (frame['sha256'] != expected_hashes[(sid, frame['frame_id'])] or
                    frame['sha256'] != info['image_sha256'] or
                    frame['timestamp_sec'] != info['timestamp_sec']):
                raise ValueError('Frozen keyframe changed: ' + sid)
        inputs.append((shot, validated, make_payload(shot, validated, frame_info),
                       dict(entity_file=str(path), entity_sha256=entities.sha(path),
                            response_sha256=entities.sha(directory / 'response.json'),
                            input_sha256=entities.sha(directory / 'input.json'))))
    return inputs


def make_payload(shot, frozen, frame_info):
    frames = [dict(frame_id=f['frame_id'], timestamp_sec=f['timestamp_sec'],
                   image_size=frame_info[f['frame_id']]['image_size'],
                   attachment_index=i + 1, image_sha256=f['sha256'])
              for i, f in enumerate(shot['frames'])]
    nodes = [dict(entity_id=e['entity_id'], name=e['name'],
                  observations=[{k: r[k] for k in ('frame_id', 'exist', 'visible', 'box_xyxy')}
                                for r in e['observations']]) for e in frozen['entities']]
    candidates, unobservable = [], []
    for i, (a, b) in enumerate(combinations(nodes, 2), 1):
        pair = dict(pair_id=f'p{i:04d}', entity_ids=[a['entity_id'], b['entity_id']],
                    jointly_visible_frame_ids=[x['frame_id'] for x, y in
                        zip(a['observations'], b['observations']) if x['visible'] and y['visible']])
        (candidates if pair['jointly_visible_frame_ids'] else unobservable).append(pair)
    return dict(protocol_version=VERSION, shot_id=shot['shot_id'], frames=frames,
                entities=nodes, pair_candidates=candidates, unobservable_pairs=unobservable)


def validate_result(result, payload):
    import jsonschema
    jsonschema.validate(result, entities.read(SCHEMA))
    if result['shot_id'] != payload['shot_id']:
        raise ValueError('Wrong shot ID')
    frame_ids = [f['frame_id'] for f in payload['frames']]
    nodes = {e['entity_id']: e for e in payload['entities']}
    ranks = {eid: i for i, eid in enumerate(nodes)}
    pairs = {frozenset(p['entity_ids']): p for p in payload['pair_candidates']}
    reviewed = result['pair_reviews']
    if [r['pair_id'] for r in reviewed] != [p['pair_id'] for p in payload['pair_candidates']]:
        raise ValueError('Must review every eligible pair exactly once in input order')
    if any(not r['reason'].strip() for r in reviewed):
        raise ValueError('Empty pair review reason')
    seen, found, present = set(), set(), {}
    for relation in result['relations']:
        a, b, predicate = relation['subject_id'], relation['object_id'], relation['predicate']
        key = (a, predicate, b)
        pair = pairs.get(frozenset((a, b)))
        if a == b or a not in nodes or b not in nodes or pair is None:
            raise ValueError('Unknown, self or never jointly visible endpoints')
        if key in seen:
            raise ValueError('Duplicate relation')
        seen.add(key)
        if predicate == 'touching' and ranks[a] > ranks[b]:
            raise ValueError('Symmetric touching must use input entity order')
        rows = relation['observations']
        if [r['frame_id'] for r in rows] != frame_ids:
            raise ValueError('Relation must cover every keyframe in input order')
        positives = set()
        joint = set(pair['jointly_visible_frame_ids'])
        for row in rows:
            if not row['reason'].strip():
                raise ValueError('Empty observation reason')
            if (row['status'] == 'not_observable') != (row['frame_id'] not in joint):
                raise ValueError('Relation observability disagrees with frozen visibility')
            if row['status'] == 'present':
                positives.add(row['frame_id'])
        if not positives:
            raise ValueError('Relation requires positive evidence in at least one frame')
        if predicate != 'touching' and positives & present.get((b, predicate, a), set()):
            raise ValueError('Opposite directed predicates conflict in the same frame')
        present[key] = positives
        found.add(pair['pair_id'])
    for review in reviewed:
        if (review['assessment'] == 'relations_found') != (review['pair_id'] in found):
            raise ValueError('Pair review disagrees with emitted relations')
    final = copy.deepcopy(result)
    final['protocol_version'] = VERSION
    pair_index = {p['pair_id']: p for p in payload['pair_candidates']}
    for review in final['pair_reviews']:
        review.update(copy.deepcopy(pair_index[review['pair_id']]))
    final['relations'].sort(key=lambda r: (ranks[r['subject_id']],
                                          PREDICATES.index(r['predicate']), ranks[r['object_id']]))
    for i, relation in enumerate(final['relations'], 1):
        relation.update(relation_id=f'r{i:04d}', reference_frame=REFERENCE[relation['predicate']])
        for status in STATES:
            relation[status + '_frame_ids'] = [r['frame_id'] for r in relation['observations']
                                               if r['status'] == status]
    final['unobservable_pairs'] = copy.deepcopy(payload['unobservable_pairs'])
    final['coverage'] = dict(total_pairs=len(pairs) + len(payload['unobservable_pairs']),
                             reviewed_pairs=len(reviewed), pairs_with_relations=len(found),
                             no_joint_visibility_pairs=len(payload['unobservable_pairs']))
    return final


def review(item, args, directory):
    shot, frozen, payload, provenance = item
    directory.mkdir(parents=True)
    entities.dump(directory / 'input.json', payload)
    entities.dump(directory / 'entities.json', frozen)
    entities.dump(directory / 'source.json', provenance)
    prompt = PROMPT.read_text() + '\n<shot>\n' + json.dumps(payload, ensure_ascii=False) + '\n</shot>\n'
    (directory / 'prompt.txt').write_text(prompt)
    shutil.copy2(SCHEMA, directory / 'output.schema.json')
    if args.prepare_only:
        return dict(shot_id=shot['shot_id'], status='prepared', calls=0)
    if not payload['pair_candidates']:
        raw = dict(shot_id=shot['shot_id'], pair_reviews=[], relations=[])
        entities.dump(directory / 'response.json', raw)
        usage, calls = [], 0
    else:
        with tempfile.TemporaryDirectory(prefix='eec-spatial-') as tmp:
            work = Path(tmp)
            command = [args.codex_bin, '--ask-for-approval', 'never', 'exec',
                       '--ignore-user-config', '-c', entities.disabled_skills_config(),
                       '--ephemeral', '--skip-git-repo-check', '--sandbox', 'read-only',
                       '--color', 'never', '--json', '--model', args.model,
                       '-c', f'model_reasoning_effort="{args.reasoning}"',
                       '-c', 'project_doc_max_bytes=0', '-c', 'web_search="disabled"',
                       '--output-schema', str(directory / 'output.schema.json'),
                       '--output-last-message', str(directory / 'response.json'), '--cd', str(work)]
            for feature in ('shell_tool', 'unified_exec', 'view_image', 'apps', 'plugins', 'hooks',
                            'multi_agent', 'memories', 'skill_search', 'browser_use', 'computer_use',
                            'code_mode', 'code_mode_only', 'workspace_dependencies'):
                command.extend(['--disable', feature])
            for index, frame in enumerate(shot['frames']):
                image = work / f"image_{index + 1}{Path(frame['path']).suffix}"
                shutil.copy2(frame['path'], image)
                if entities.sha(image) != frame['sha256']:
                    raise ValueError('Keyframe changed before spatial review')
                command.extend(['--image', str(image)])
            command.append('-')
            entities.dump(directory / 'request.json', dict(command=command, model=args.model,
                reasoning=args.reasoning, prompt_sha256=entities.sha(directory / 'prompt.txt'),
                schema_sha256=entities.sha(directory / 'output.schema.json'), **provenance))
            entities.run_process(command, prompt, work, directory / 'events.jsonl',
                                 directory / 'stderr.log', args.timeout)
        usage, calls = entities.audit_events(directory / 'events.jsonl'), 1
        raw = entities.read(directory / 'response.json')
    final = validate_result(raw, payload)
    final['source'] = provenance
    entities.dump(directory / 'relations.json', final)
    entities.dump(directory / 'graph.json', dict(shot_id=shot['shot_id'],
        protocol_version=VERSION, entities=frozen['entities'], relations=final['relations'],
        pair_reviews=final['pair_reviews'], unobservable_pairs=final['unobservable_pairs'],
        source=provenance))
    return dict(shot_id=shot['shot_id'], status='success', calls=calls, usage=usage,
                relation_count=len(final['relations']), coverage=final['coverage'],
                graph_sha256=entities.sha(directory / 'graph.json'),
                output_sha256=entities.sha(directory / 'relations.json'))


def run(source, out, args, allow_running=False):
    if not args.prepare_only:
        job = entities.safe_compute()
    else:
        job = None
    inputs = load_inputs(source, allow_running=allow_running)
    import jsonschema
    jsonschema.Draft202012Validator.check_schema(entities.read(SCHEMA))
    out.mkdir(parents=True, exist_ok=False)
    shutil.copy2(source / 'run.json', out / 'source_run.snapshot.json')
    entities.dump(out / 'manifest.json', dict(shots=[i[0] for i in inputs]))
    snapshot = out / 'code_snapshot'
    snapshot.mkdir()
    for path in (Path(__file__), Path(entities.__file__), PROMPT, SCHEMA):
        shutil.copy2(path, snapshot / path.name)
    state = dict(status='running', protocol_version=VERSION, source_run=str(source),
                 source_run_snapshot='source_run.snapshot.json',
                 source_run_snapshot_sha256=entities.sha(out / 'source_run.snapshot.json'),
                 started=time.time(), host=socket.gethostname(), allocation=job,
                 model=args.model, reasoning=args.reasoning, shot_workers=args.shot_workers,
                 shots=[], active_shots=[])
    entities.dump(out / 'run.json', state)
    records, failures = {}, []
    pending = iter(inputs)

    def task(item):
        directory = out / 'shots' / item[0]['shot_id']
        started = time.time()
        try:
            record = review(item, args, directory)
        except Exception as exc:
            record = dict(shot_id=item[0]['shot_id'], status='failed', error=str(exc),
                          attempted_calls=int((directory / 'request.json').exists()),
                          usage=[], usage_complete=False)
            # Preserve any completed paid call's usage even if validation failed.
            event_path = directory / 'events.jsonl'
            if event_path.exists():
                for line in event_path.read_text().splitlines():
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if event.get('type') == 'turn.completed' and event.get('usage') is not None:
                        record['usage'].append(event['usage'])
                try:
                    entities.audit_events(event_path)
                    record['usage_complete'] = True
                except (ValueError, json.JSONDecodeError) as audit_error:
                    record['audit_error'] = str(audit_error)
        record.update(started=started, finished=time.time())
        entities.dump(directory / 'status.json', record)
        return record

    with ThreadPoolExecutor(max_workers=args.shot_workers) as pool:
        active = {}
        def fill():
            while len(active) < args.shot_workers and not failures:
                item = next(pending, None)
                if item is None:
                    break
                active[pool.submit(task, item)] = item[0]['shot_id']
        fill()
        while active:
            state['active_shots'] = list(active.values())
            entities.dump(out / 'run.json', state)
            completed, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in completed:
                sid = active.pop(future)
                record = future.result()
                records[sid] = record
                if record['status'] == 'failed':
                    failures.append(sid)
            state['shots'] = [records[i[0]['shot_id']] for i in inputs if i[0]['shot_id'] in records]
            fill()
    state.update(status='failed' if failures else ('prepared' if args.prepare_only else 'success'),
                 active_shots=[], finished=time.time())
    entities.dump(out / 'run.json', state)
    if failures:
        raise RuntimeError('Spatial reviews failed: ' + ', '.join(failures))
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--entity-run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--shot-workers', type=int, default=3)
    parser.add_argument('--model', default='gpt-6-astra')
    parser.add_argument('--reasoning', choices=['low', 'medium', 'high', 'xhigh', 'max', 'ultra'], default='medium')
    parser.add_argument('--codex-bin', default='codex')
    parser.add_argument('--timeout', type=int, default=1200)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    if args.shot_workers < 1:
        parser.error('--shot-workers must be positive')
    print(json.dumps(run(args.entity_run.resolve(), args.output.resolve(), args), ensure_ascii=False))


if __name__ == '__main__':
    main()
