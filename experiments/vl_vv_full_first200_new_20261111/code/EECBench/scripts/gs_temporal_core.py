"""Per-frame proposal generation; no box fusion, fitting, or model calls."""
import copy
import itertools
import math


def cosine(a, b):
    if a is None or b is None:
        return None
    den = math.sqrt(sum(x*x for x in a) * sum(x*x for x in b))
    return max(-1., min(1., sum(x*y for x, y in zip(a, b))/den)) if den > 1e-10 else None


def center(row):
    # Deliberately ignore static-fusion selected/eligible/outlier flags.
    if not row.get('visible') or row.get('box_xyxy') is None:
        return None
    g = row.get('geometry')
    p = g.get('center_world') if g else None
    if p is None or len(p) != 3 or not all(math.isfinite(x) for x in p):
        return None
    return p


def vector(a, b):
    a, b = center(a), center(b)
    return [y-x for x, y in zip(a, b)] if a is not None and b is not None else None


def interval_state(entity, lo, hi):
    if 'motion_status' in entity:
        if entity['motion_status'] not in ('static', 'moving'):
            raise ValueError('Invalid binary motion classification')
        return 'reasonable_motion' if entity['motion_status'] == 'moving' else 'static'
    rows = entity['intervals'][lo:hi]
    if any(r['expected'] == 'unknown' for r in rows):
        return 'unknown'
    if any(r['expected'] == 'reasonable_motion' for r in rows):
        return 'reasonable_motion'
    return 'static'


def within_proposals(graph, expectation):
    fids = [c['frame_id'] for c in graph['cameras']]
    if len(fids) < 2 or fids != sorted(set(fids)):
        raise ValueError('Need chronological unique keyframes')
    expected = {e['entity_id']: e for e in expectation['entities']}
    if set(expected) != {e['entity_id'] for e in graph['entities']}:
        raise ValueError('Expectation population mismatch')
    evidence = {e['entity_id']: {r['frame_id']: r for r in e['frame_evidence']} for e in graph['entities']}
    if any(set(rows) != set(fids) for rows in evidence.values()):
        raise ValueError('Missing frame evidence rows; retain null observations explicitly')
    events, presence_units, spatial_units = [], [], []
    for e in graph['entities']:
        eid = e['entity_id']; exp = expected[eid]; ids = []
        if 'motion_status' in exp:
            static_frames = set(fids) if interval_state(exp, 0, len(fids)-1) == 'static' else set()
        else:
            static_frames = {fids[i+d] for i, r in enumerate(exp['intervals'])
                             if r['expected'] == 'static' for d in (0, 1)}
        for fid in fids:
            row = evidence[eid][fid]
            if fid in static_frames and (not row.get('visible') or row.get('box_xyxy') is None):
                event = dict(event_id=f'presence_{len(events):05d}', kind='presence',
                             entity_ids=[eid], target_frames=[dict(shot_id=graph['shot_id'], frame_id=fid)],
                             reason='missing_observation_in_expected_static_period')
                # Neighbouring observed keyframes are context, never substitute boxes.
                event['context_frame_ids'] = [f for f in fids if evidence[eid][f].get('visible')]
                events.append(event); ids.append(event['event_id'])
        unknown = any(r['expected'] == 'unknown' for r in exp.get('intervals', []))
        presence_units.append(dict(unit_id=eid, entity_ids=[eid], event_ids=ids,
                                   base_status='unknown' if unknown else 'compatible' if static_frames else 'exempt',
                                   reason='expected_static_visibility' if static_frames else
                                   'whole_shot_motion_exemption' if 'motion_status' in exp else 'no_expected_static_interval'))
    for a, b in itertools.combinations(graph['entities'], 2):
        ids = [a['entity_id'], b['entity_id']]; comparisons = []; event_ids = []
        for lo, hi in itertools.combinations(range(len(fids)), 2):
            states = [interval_state(expected[eid], lo, hi) for eid in ids]
            v = [vector(evidence[ids[0]][fids[i]], evidence[ids[1]][fids[i]]) for i in (lo, hi)]
            c = cosine(*v)
            scope = 'unknown' if 'unknown' in states else 'exempt' if 'reasonable_motion' in states else 'eligible'
            motion_reason = ('reasonable_motion_somewhere_in_shot' if any('motion_status' in expected[eid] for eid in ids)
                             else 'reasonable_motion_between_frames')
            row = dict(frame_ids=[fids[lo], fids[hi]], expected_states=states, eligibility=scope,
                       vectors=v, cosine=c, reason=motion_reason if scope == 'exempt' else
                       'uncertain_motion_expectation' if scope == 'unknown' else
                       'not_computable' if c is None else 'negative_candidate' if c < 0 else 'nonnegative_not_further_reviewed')
            if scope == 'eligible' and c is not None and c < 0:
                event = dict(event_id=f'spatial_{len(events):05d}', kind='spatial', entity_ids=ids,
                             target_frames=[dict(shot_id=graph['shot_id'], frame_id=fids[i]) for i in (lo, hi)],
                             vectors=v, cosine=c, reason='negative_cosine_in_expected_static_period')
                events.append(event); event_ids.append(event['event_id']); row['event_id'] = event['event_id']
            comparisons.append(row)
        spatial_units.append(dict(unit_id='pair_'+ids[0]+'__'+ids[1], entity_ids=ids,
                                  event_ids=event_ids, comparisons=comparisons,
                                  base_status='exempt' if all(r['eligibility']=='exempt' for r in comparisons) else 'unknown',
                                  reason='all_temporal_pairs_recorded; nonnegative_is_not_verified_compatible'))
    return dict(shot_id=graph['shot_id'], frame_ids=fids, events=events,
                presence_units=presence_units, spatial_units=spatial_units)


def transform_geometry(geometry, fit):
    if geometry is None:
        return None
    g = copy.deepcopy(geometry); s, R, t = fit['scale'], fit['rotation'], fit['translation']
    def rotate(p):
        return [sum(R[i][j]*p[j] for j in range(3)) for i in range(3)]
    g['center_world'] = [s*x+y for x, y in zip(rotate(g['center_world']), t)]
    g['size_xyz'] = [s*x for x in g['size_xyz']]
    O = g['R_world_from_object']
    g['R_world_from_object'] = [[sum(R[i][k]*O[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    if 'corners_world' in g:
        g['corners_world'] = [[s*x+y for x, y in zip(rotate(p), t)] for p in g['corners_world']]
    return g


def boundary_proposals(graphs, matching, fit):
    if fit['status'] != 'numeric_candidate':
        raise ValueError('A completed frozen registration is required')
    frames = [graphs[0]['cameras'][-1]['frame_id'], graphs[1]['cameras'][0]['frame_id']]
    nodes = [{e['entity_id']: e for e in g['entities']} for g in graphs]
    for i, key in enumerate(('a_ids', 'b_ids')):
        population = [eid for g in matching['groups'] for eid in g[key]]
        if len(population) != len(set(population)) or set(population) != set(nodes[i]):
            raise ValueError('Boundary matching must preserve every entity, regardless of motion')
    endpoints = []
    for side, graph in enumerate(graphs):
        rows = {}
        for eid, entity in nodes[side].items():
            row = copy.deepcopy(next(r for r in entity['frame_evidence'] if r['frame_id'] == frames[side]))
            if not row.get('visible') or row.get('box_xyxy') is None:
                row['geometry'] = None
            elif side:
                row['geometry'] = transform_geometry(row.get('geometry'), fit)
            rows[eid] = row
        endpoints.append(rows)
    target = [dict(shot_id=g['shot_id'], frame_id=f) for g, f in zip(graphs, frames)]
    events = []; presence_units = []; spatial_units = []
    for group in matching['groups']:
        gid = group['group_id']; resolved = group['identity'] in ('matched', 'unmatched')
        event_ids = []
        if resolved:
            ev = dict(event_id='presence_'+gid, kind='presence', group_id=gid,
                      entity_ids=group['a_ids']+group['b_ids'], target_frames=target,
                      endpoint_observations=[[endpoints[i][eid] for eid in group[key]] for i, key in enumerate(('a_ids','b_ids'))],
                      reason='boundary_presence_all_motion_states')
            events.append(ev); event_ids.append(ev['event_id'])
        presence_units.append(dict(unit_id=gid, entity_ids=group['a_ids']+group['b_ids'], event_ids=event_ids,
                                   base_status='unknown', reason='boundary_presence' if resolved else 'unresolved_identity'))
    common = [g for g in matching['groups'] if g['identity'] == 'matched']
    for a, b in itertools.combinations(common, 2):
        gid = 'pair_'+a['group_id']+'_'+b['group_id']
        vectors = [vector(endpoints[i][a[key][0]], endpoints[i][b[key][0]]) for i,key in enumerate(('a_ids','b_ids'))]
        c = cosine(*vectors); event_ids = []
        if c is not None and c < 0:
            ev = dict(event_id='spatial_'+gid, kind='spatial', endpoint_groups=[a['group_id'], b['group_id']],
                      entity_ids=a['a_ids']+b['a_ids']+a['b_ids']+b['b_ids'], target_frames=target,
                      vectors=vectors, cosine=c, reason='negative_boundary_cosine')
            events.append(ev); event_ids.append(ev['event_id'])
        spatial_units.append(dict(unit_id=gid, endpoint_groups=[a['group_id'], b['group_id']],
                                  event_ids=event_ids, vectors=vectors, cosine=c, base_status='unknown',
                                  reason='not_computable' if c is None else 'negative_candidate' if c < 0 else 'nonnegative_not_further_reviewed'))
    return dict(target_frames=target, endpoint_observations=endpoints, events=events,
                presence_units=presence_units, spatial_units=spatial_units)


def score(rows, spatial=False):
    if spatial:
        total = len(rows)
        conflicts = sum(r['status'] == 'conflict' for r in rows)
        ratio = conflicts / total if total else None
        return dict(score=100*(1-ratio) if ratio is not None else None,
                    total_pairs=total, confirmed_conflict_pairs=conflicts,
                    anomaly_ratio=ratio,
                    no_conflict_pairs=sum(r['status'] in ('compatible','no_conflict') for r in rows),
                    unresolved_pairs=sum(r['status'] == 'unknown' for r in rows),
                    exempt_pairs=sum(r['status'] == 'exempt' for r in rows),
                    scoring_protocol='confirmed_anomaly_fraction_v1',
                    formula='100*(1-confirmed_conflict_pairs/total_pairs)')
    c,k,u,e = [sum(r['status']==s for r in rows) for s in ('compatible','conflict','unknown','exempt')]
    n = c+k+u
    return dict(score=100*(1-k/n) if n and c+k else None,
                coverage=(c+k)/n if n else None, N=n,C=c,K=k,U=u,E=e,
                identification_interval=[100*c/n,100*(c+u)/n] if n else None)


def aggregate(units, events, spatial=False):
    results = []
    for unit in units:
        checks = [events[eid] for eid in unit['event_ids']]
        states = [r['status'] for r in checks]
        status = 'conflict' if 'conflict' in states else 'unknown' if 'unknown' in states else None
        if status is None:
            status = ('exempt' if states and all(s=='exempt' for s in states) else
                      'compatible' if states and all(s in ('compatible','exempt') for s in states) else unit['base_status'])
            if spatial and any(r['eligibility']!='exempt' and r.get('event_id') not in events
                               for r in unit.get('comparisons', [])):
                status = 'unknown'
            if unit['base_status']=='unknown' and unit.get('reason')=='expected_static_visibility' and status!='conflict':
                status = 'unknown'
        if spatial and status == 'unknown':
            # No alarm is a normal result, not a failed positive certification.
            # Missing/uncertain comparisons retain their diagnostic unknown label.
            comparisons = unit.get('comparisons')
            if comparisons is None:
                if not checks and unit.get('cosine') is not None and unit['cosine'] >= 0:
                    status = 'no_conflict'
            elif not any(s == 'unknown' for s in states):
                active = [r for r in comparisons if r['eligibility'] != 'exempt']
                if active and all(r['eligibility'] == 'eligible' and
                                  ((r.get('event_id') in events and events[r['event_id']]['status'] in ('compatible','exempt')) or
                                   (r.get('cosine') is not None and r['cosine'] >= 0)) for r in active):
                    status = 'no_conflict'
        results.append(dict(unit, status=status))
    return dict(summary=score(results, spatial=spatial), units=results)
