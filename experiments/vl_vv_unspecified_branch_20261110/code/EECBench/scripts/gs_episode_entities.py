"""Episode registry from frozen shot inventories and final reviewed identities.

Only confirmed one-to-one edges join records. Omitted shots are unknown, not
absent. This deterministic export does not perform inference or change scores.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path


def build_registry(shots, inventories, scope, pairs):
    shot_ids = [s['shot_id'] for s in shots]
    if not shot_ids or len(set(shot_ids)) != len(shot_ids):
        raise ValueError('Require unique nonempty shot inventory')
    scene_by_shot = {}
    for scene, ids in scope['scenes'].items():
        for sid in ids:
            if sid in scene_by_shot:
                raise ValueError('Shot belongs to multiple scenes')
            scene_by_shot[sid] = scene
    if set(scene_by_shot) != set(shot_ids) or set(inventories) != set(shot_ids):
        raise ValueError('Scene/inventory coverage differs from manifest')
    nodes = {}
    for shot in shots:
        sid = shot['shot_id']
        inventory = inventories[sid]
        if inventory['shot_id'] != sid:
            raise ValueError('Wrong shot inventory')
        frame_ids = [f['frame_id'] for f in shot['frames']]
        for entity in inventory['entities']:
            eid = entity['entity_id']
            key = sid + '/' + eid
            if not eid or '/' in eid or key in nodes:
                raise ValueError('Invalid or duplicate local entity ID')
            obs = entity['observations']
            if [o['frame_id'] for o in obs] != frame_ids:
                raise ValueError('Observation frames differ from supplied shot frames')
            observed = [o['frame_id'] for o in obs if o['exist'] is True and o['box_xyxy'] is not None]
            if not observed:
                raise ValueError('Entity has no confirmed detector observation')
            nodes[key] = dict(shot_id=sid, local_entity_id=eid, name=entity['name'],
                              observed_frame_ids=observed, observations=copy.deepcopy(obs))
    parent = {key: key for key in nodes}
    def root(key):
        while parent[key] != key:
            key = parent[key]
        return key
    confirmed, unresolved, unilateral = [], [], []
    expected_pairs = {p['pair_id']: p for p in scope['cross_shot_pairs']}
    if len(expected_pairs) != len(scope['cross_shot_pairs']):
        raise ValueError('Duplicate pair IDs')
    if len(pairs) != len(expected_pairs) or {p['pair_id'] for p in pairs} != set(expected_pairs):
        raise ValueError('Missing or duplicate final identity pairs')
    for pair in pairs:
        pid = pair['pair_id']
        expected = expected_pairs[pid]
        ids = expected['shot_ids']
        aliases = pair['pair_scope']['aliases']
        if (len(ids) != 2 or len(set(ids)) != 2 or
                pair['pair_scope']['original_shot_ids'] != ids or
                aliases != dict(zip(ids, ('shot1', 'shot3')))):
            raise ValueError('Pair alias/order mismatch')
        if any(scene_by_shot[sid] != expected['scene_id'] for sid in ids):
            raise ValueError('Cross-scene identity edge is not supported')
        seen, group_ids = set(), set()
        for group in pair['matching']['groups']:
            gid = group['group_id']
            if gid in group_ids:
                raise ValueError('Duplicate identity group')
            group_ids.add(gid)
            sides = []
            for sid, field in zip(ids, ('a_ids', 'b_ids')):
                restored = []
                prefix = aliases[sid] + '/'
                for eid in group[field]:
                    if not eid.startswith(prefix):
                        raise ValueError('Entity ID uses wrong pair-local alias')
                    key = sid + '/' + eid[len(prefix):]
                    if key not in nodes or key in seen:
                        raise ValueError('Unknown or multiply assigned identity member')
                    seen.add(key)
                    restored.append(key)
                sides.append(restored)
            members = sides[0] + sides[1]
            if not members:
                raise ValueError('Empty identity group')
            status = group['identity']
            record = dict(pair_id=pid, group_id=gid, identity=status, members=members,
                          evidence=group.get('identity_evidence', ''))
            if status == 'matched':
                if [len(s) for s in sides] != [1, 1]:
                    raise ValueError('Confirmed match must be one-to-one')
                a, b = map(root, members)
                if a != b:
                    merged = [nodes[k]['shot_id'] for k in nodes if root(k) in (a, b)]
                    if len(merged) != len(set(merged)):
                        raise ValueError('Confirmed chain would merge distinct entities in one shot')
                    parent[b] = a
                confirmed.append(record)
            elif status == 'unmatched':
                if len(members) != 1:
                    raise ValueError('Unmatched group must be unilateral')
                unilateral.append(record)
            elif status in ('ambiguous', 'scope_mismatch'):
                unresolved.append(record)
            else:
                raise ValueError('Unknown identity status: ' + status)
        expected_members = {k for k, n in nodes.items() if n['shot_id'] in ids}
        if seen != expected_members:
            raise ValueError('Final matching does not conserve both shot inventories')
    components = {}
    for key in nodes:
        components.setdefault(root(key), []).append(key)
    entities, mapping = [], {}
    for i, members in enumerate(components.values(), 1):
        global_id = f'ge{i:04d}'
        mapping.update({k: global_id for k in members})
        appearances = [nodes[k] for k in members]
        entities.append(dict(global_entity_id=global_id, name=appearances[0]['name'],
                             scene_id=scene_by_shot[appearances[0]['shot_id']],
                             observed_shot_ids=[a['shot_id'] for a in appearances],
                             appearances=appearances))
    for record in confirmed + unresolved + unilateral:
        record['global_entity_ids'] = list(dict.fromkeys(mapping[k] for k in record['members']))
    for record in unresolved:
        if len(record['global_entity_ids']) != len(record['members']):
            raise ValueError('Confirmed chain contradicts unresolved identity group')
    return dict(schema_version='episode_entities_v1',
                policy='merge_final_confirmed_matches_only',
                occurrence_semantics='Positive shot-local detector observations only; omitted shots are unknown, not absent.',
                identity_scope='Episode inventory; confirmed chains within scenes only. Separate records may still be the same unresolved physical entity.',
                shot_order=shot_ids, entities=entities, local_to_global=mapping,
                confirmed_identity_links=confirmed, unresolved_identity_links=unresolved,
                unmatched_records=unilateral,
                counts=dict(local_entities=len(nodes), global_records=len(entities),
                            confirmed_links=len(confirmed), unresolved_links=len(unresolved)),
                appearance_score_computed=False)


def export_registry(case, output):
    case, output = Path(case).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError('Use a new registry output directory')
    sources = {}
    def read(relative):
        path = case / relative
        raw = path.read_bytes()
        sources[str(path)] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)
    shots = read('raw_manifest.json')['shots']
    scope = read('identity_scope.json')
    from gs_shot_prompt_recovery import active_entities_root
    entity_root=active_entities_root(case).relative_to(case)
    inventories = {s['shot_id']: read(str(entity_root / 'shots' / s['shot_id'] / 'entities.json')) for s in shots}
    pairs = []
    for p in scope['cross_shot_pairs']:
        pid = p['pair_id']
        prefix = f'pairs/{pid}/'
        review = read(prefix + 'identity_review.json')
        matching = read(prefix + 'matching.json')
        audit = read(prefix + 'identity_review_audit.json')
        if not audit.get('passed') or matching != review['matching']:
            raise ValueError('Require audited final reviewed matching, not initial identities')
        pairs.append(dict(pair_id=pid, pair_scope=read(prefix + 'pair_scope.json'), matching=matching))
    result = build_registry(shots, inventories, scope, pairs)
    for entity in result['entities']:
        for row in entity['appearances']:
            folder = case / entity_root / 'shots' / row['shot_id']
            row['source_entities_file'] = str(folder / 'entities.json')
            candidate_path = folder / 'input.json'
            if not candidate_path.is_file():
                raise FileNotFoundError(candidate_path)
            row['source_candidates_file'] = str(candidate_path)
    # Preserve original candidate evidence, including member boxes of collections.
    for s in shots:
        read(str(entity_root / 'shots' / s['shot_id'] / 'input.json'))
    sources[str(Path(__file__).resolve())] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result.update(source_case=str(case), source_hashes=sources)
    for source, digest in sources.items():
        if hashlib.sha256(Path(source).read_bytes()).hexdigest() != digest:
            raise ValueError('Source changed during export: ' + source)
    output.mkdir(parents=True)
    (output / 'global_entities.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', ' ')
    lines = ['# Episode global entity table', '',
             'Confirmed occurrences only. An omitted shot is unknown, not a negative presence judgment.',
             'Separate records linked by ambiguous/scope_mismatch evidence are not proven distinct physical entities.', '',
             '| Global ID | Name (first observation) | Scene | Confirmed shot-local occurrences |',
             '|---|---|---|---|']
    for e in result['entities']:
        occurrences = '; '.join(f"{a['shot_id']}/{a['local_entity_id']} ({a['name']})" for a in e['appearances'])
        lines.append('| ' + ' | '.join(map(cell, [e['global_entity_id'], e['name'], e['scene_id'], occurrences])) + ' |')
    lines += ['', '## Unresolved associations (not merged)', '']
    for r in result['unresolved_identity_links']:
        lines.append(f"- {r['pair_id']}/{r['group_id']}: {r['identity']} — {', '.join(r['members'])}. {r['evidence']}")
    (output / 'global_entities.md').write_text('\n'.join(lines) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export_registry(args.case, args.output)['counts']))


if __name__ == '__main__':
    main()
