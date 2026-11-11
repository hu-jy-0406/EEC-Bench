"""Deterministic entity displacement scores; no inference or registration fitting."""
import argparse
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import statistics

from gs_temporal_core import boundary_proposals, center

PROTOCOL = 'entity_displacement_median_rms_v1'
FORMULA = 'r_e=d_e/median_scope(d); S_e=100/max(1,r_e); S=100-sqrt(mean((100-S_e)^2))'


def aggregate(records):
    valid = [r for r in records if r.get('r_e') is not None]
    deficits = [1 - 1 / max(1., r['r_e']) for r in valid]
    return dict(score=100 * (1 - math.sqrt(statistics.mean(x*x for x in deficits))) if valid else None,
                total_records=len(records), scored_records=len(valid),
                unscored_records=len(records)-len(valid), weighting='equal_entity_observation_records')


def normalize(records):
    """One median per scope, never an episode-wide distance denominator."""
    distances = [r['distance'] for r in records if r['status'] == 'measured']
    baseline = statistics.median(distances) if distances else None
    # Relative machine precision guard preserves coordinate-scale invariance.
    floor = 32 * math.ulp(max(distances)) if distances else None
    usable = baseline is not None and baseline > floor
    for row in records:
        row.update(baseline_median=baseline, r_e=None, entity_score=None)
        if row['status'] != 'measured':
            continue
        if not usable:
            row.update(status='unscored', reason='zero_or_numerically_degenerate_median')
            continue
        ratio = row['distance'] / baseline
        if not math.isfinite(ratio):
            row.update(status='unscored', reason='nonfinite_ratio')
            continue
        row.update(status='scored', reason=None, r_e=ratio,
                   entity_score=100 / max(1., ratio))
    return dict(baseline_median=baseline, baseline_entity_count=len(distances),
                baseline_status='valid' if usable else 'unavailable' if baseline is None else 'degenerate',
                numerical_floor=floor, summary=aggregate(records), records=records)


def within(graph):
    sid = graph['shot_id']; records = []
    for entity in graph['entities']:
        observations = []
        missing = []
        seen = set()
        for row in entity['frame_evidence']:
            fid = row['frame_id']
            if fid in seen:
                raise ValueError('Duplicate entity frame observation')
            seen.add(fid)
            point = center(row)
            if point is None:
                missing.append(fid)
            else:
                observations.append(dict(frame_id=fid, center=point))
        record = dict(record_id=f'within/{sid}/{entity["entity_id"]}', scope_kind='within',
                      scope_id=sid, entity_ids=[entity['entity_id']], name=entity['name'],
                      motion_status=entity.get('motion_status'), status='unscored', reason=None,
                      distance=None, max_distance=None, max_frame_pair=None,
                      n=len(observations), m=len(entity['frame_evidence']),
                      observations=observations, missing_frame_ids=missing, pairs=[])
        if entity.get('motion_status') != 'static':
            record.update(status='excluded', reason='not_whole_shot_static')
        elif len(observations) < 2:
            record['reason'] = 'fewer_than_two_valid_observations'
        else:
            pairs = [dict(frame_ids=[a['frame_id'], b['frame_id']], distance=math.dist(a['center'], b['center']))
                     for a, b in itertools.combinations(observations, 2)]
            maximum = max(pairs, key=lambda p: p['distance'])
            record.update(status='measured', distance=statistics.mean(p['distance'] for p in pairs),
                          max_distance=maximum['distance'], max_frame_pair=maximum['frame_ids'], pairs=pairs)
        records.append(record)
    return dict(shot_id=sid, frame_ids=[c['frame_id'] for c in graph['cameras']], **normalize(records))


def boundary(pair_id, graphs, matching, fit, pair_scope, reviewed):
    aliases = pair_scope['aliases']; shot_ids = pair_scope['original_shot_ids']
    if aliases != dict(zip(shot_ids, ('shot1', 'shot3'))) or len(shot_ids) != 2:
        raise ValueError('Invalid pair-local aliases')
    inverse = {v: k for k, v in aliases.items()}
    def restore(eid):
        sid, local = eid.split('/', 1)
        return inverse[sid] + '/' + local
    proposals = boundary_proposals(graphs, matching, fit)
    nodes = [{e['entity_id']: e for e in g['entities']} for g in graphs]
    # Reuse ONLY already accepted entity-specific legitimate-motion judgments.
    # Viewpoint/occlusion or pair-wide explanations cannot exempt an entity here.
    exemptions = {e['group_id']: e['event_id'] for e in reviewed.get('events', [])
                  if e.get('kind') == 'presence' and e.get('group_id')
                  and e.get('status') == 'exempt' and e.get('gate_reason') == 'accepted'
                  and e.get('prompt_gate') is True
                  and e.get('review', {}).get('cause') == 'reasonable_motion'
                  and e['review'].get('prompt_verdict') == 'explains_change'}
    records = []
    for group in matching['groups']:
        sides = [group['a_ids'], group['b_ids']]
        ids = sum(sides, [])
        row = dict(record_id=f'boundary/{pair_id}/{group["group_id"]}', scope_kind='boundary',
                   scope_id=pair_id, group_id=group['group_id'], entity_ids=[restore(e) for e in ids],
                   pair_local_entity_ids=ids, identity=group['identity'], status='excluded',
                   reason=None, distance=None, observations=[])
        if group['identity'] != 'matched' or list(map(len, sides)) != [1, 1]:
            row['reason'] = 'not_confirmed_one_to_one'
        else:
            entities = [nodes[i][sides[i][0]] for i in range(2)]
            row['name'] = [e['name'] for e in entities]
            row['motion_status'] = [e.get('motion_status') for e in entities]
            points = [center(proposals['endpoint_observations'][i][sides[i][0]]) for i in range(2)]
            row['observations'] = [dict(shot_id=shot_ids[i], frame_id=proposals['target_frames'][i]['frame_id'],
                                        center_aligned=points[i]) for i in range(2)]
            if any(e.get('motion_status') != 'static' for e in entities):
                row['reason'] = 'not_static_in_both_shots'
            elif group['group_id'] in exemptions:
                row.update(reason='existing_prompt_authorized_motion', exemption_event=exemptions[group['group_id']])
            elif any(p is None for p in points):
                row.update(status='unscored', reason='missing_exact_endpoint')
            else:
                row.update(status='measured', distance=math.dist(*points))
        records.append(row)
    return dict(pair_id=pair_id, shot_ids=shot_ids,
                coordinate_system=f'{shot_ids[0]} model units; not calibrated meters',
                **normalize(records))


def evaluate(case):
    case = Path(case).resolve(); sources = {}
    def read(relative):
        path = case / relative; raw = path.read_bytes()
        sources[str(path)] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)
    manifest = read('raw_manifest.json'); scope = read('identity_scope.json')
    shots = {}
    for item in manifest['shots']:
        sid = item['shot_id']; graph = read(f'selected/{sid}_scene.json')
        if graph['shot_id'] != sid or [c['frame_id'] for c in graph['cameras']] != [f['frame_id'] for f in item['frames']]:
            raise ValueError('Graph does not match original shot/frame scope')
        shots[sid] = within(graph)
    boundaries = {}
    for pair in scope['cross_shot_pairs']:
        pid = pair['pair_id']; root = f'pairs/{pid}/'
        ps = read(root+'pair_scope.json')
        if ps['original_shot_ids'] != pair['shot_ids'] or any(s not in scope['scenes'][pair['scene_id']] for s in pair['shot_ids']):
            raise ValueError('Pair scope differs from same-scene chronology')
        graphs = [read(root+f'selected/{sid}_scene.json') for sid in ('shot1', 'shot3')]
        matching = read(root+'matching.json')
        registration = read(root+'registration/roma_geometry/registration.json')
        reviewed = read(root+'boundary/results.json')
        if reviewed['status'] != 'success':
            raise ValueError('Boundary review not complete')
        boundaries[pid] = boundary(pid, graphs, matching, registration['fits']['all_structures'], ps, reviewed)
    own = [r for shot in shots.values() for r in shot['records']]
    cross = [r for pair in boundaries.values() for r in pair['records']]
    return dict(protocol=PROTOCOL, formula=FORMULA, status='success', source_case=str(case),
                units='Raw distances in scope-local model units; r_e dimensionless',
                within_shots=shots, boundaries=boundaries,
                episode=dict(within=aggregate(own), cross=aggregate(cross), all=aggregate(own+cross)),
                records=own+cross, source_hashes=sources,
                scoring_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                model_calls=0, total_tokens=0, api_usd=0,
                limitations=['Ratios are relative deviations, not calibrated noise significance.',
                             'Detection/geometry error can reduce scores; widespread drift can raise the median.',
                             'Small normalization populations are weak references; counts are retained.',
                             'No new between-shot motion inference; only existing accepted entity motion exemptions reused.'])


def write(result, out):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    (out/'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    fields = ['record_id', 'scope_kind', 'scope_id', 'entity_ids', 'name', 'status', 'reason',
              'distance', 'max_distance', 'baseline_median', 'r_e', 'entity_score', 'n', 'm', 'max_frame_pair']
    with (out/'entities.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore'); writer.writeheader()
        for row in result['records']:
            writer.writerow({k:json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k,v in row.items()})
    lines = ['# Entity displacement position consistency', '', FORMULA, '',
             'Each scope computes its own median; episode scores pool valid entity records, not scope scores.', '',
             '| Scope | Score | Scored / total records |', '|---|---:|---:|']
    summaries = [(f'within/{s}', r['summary']) for s,r in result['within_shots'].items()]
    summaries += [(f'boundary/{s}', r['summary']) for s,r in result['boundaries'].items()]
    summaries += [('episode/'+s, r) for s,r in result['episode'].items()]
    for name, row in summaries:
        score = 'null' if row['score'] is None else f'{row["score"]:.6f}'
        lines.append(f'| {name} | {score} | {row["scored_records"]} / {row["total_records"]} |')
    lines += ['', 'JSON/CSV preserve round-trip float precision of raw ratios and distances. Missing/excluded records remain explicit.',
              '0 new model calls; 0 tokens; USD 0 API. Frozen-input replay is not a new full pipeline run.', '']
    lines += result['limitations']
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=Path, required=True)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    result = evaluate(args.case)
    write(result, args.out or args.case/'displacement')
    print(json.dumps(result['episode'], ensure_ascii=False))


if __name__ == '__main__':
    main()
