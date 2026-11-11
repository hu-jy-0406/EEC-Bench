"""Negative-cosine-only within-shot review with concise evidence transport."""
import copy
from gs_consistency_contract import obj, arr, enum, S, I, WITNESS
from gs_temporal_contract import GATES, CHECK
from gs_shot_motion import classification_geometry

PROTOCOL = 'negative_cosine_only_v1'
SCHEMA = obj(witnesses=arr(WITNESS), checks=arr(obj(
    event_id=S, status=CHECK['properties']['status'], cause=CHECK['properties']['cause'],
    prompt_verdict=CHECK['properties']['prompt_verdict'],
    prompt_fact_references=arr(S), witness_ids=arr(I),
    unverified=arr(enum(*GATES)), reason=S, remaining_alternatives=S)))


def payload_for(graph, events, story):
    if any(e['kind']!='spatial' or e['cosine'] is None or e['cosine']>=0 for e in events):
        raise ValueError('Within spatial reviewer accepts negative cosine events only')
    result=dict(protocol=PROTOCOL, shot_id=graph['shot_id'],
                coordinate_system=copy.deepcopy(graph['coordinate_system']),
                cameras=copy.deepcopy(graph['cameras']), normal_story_prompt=copy.deepcopy(story),
                events=copy.deepcopy(events), entities=[])
    for e in graph['entities']:
        rows=[]
        for row in e['frame_evidence']:
            # Preserve every original observation and relevant reconstruction diagnostic.
            r={k:copy.deepcopy(v) for k,v in row.items()
               if k not in ('geometry','source_group','weight','selected','eligible')}
            r['geometry']=classification_geometry(row.get('geometry'));rows.append(r)
        result['entities'].append(dict(entity_id=e['entity_id'],name=e['name'],frame_evidence=rows))
    return result


def expand(raw, events):
    import jsonschema
    jsonschema.validate(raw,SCHEMA)
    if [r['event_id'] for r in raw['checks']] != [e['event_id'] for e in events]:
        raise ValueError('Spatial review coverage/order mismatch')
    checks=[]
    for row in raw['checks']:
        ids=row['witness_ids'];unknown=row['unverified']
        if len(ids)!=len(set(ids)) or any(i<0 or i>=len(raw['witnesses']) for i in ids):
            raise ValueError('Invalid witness reference')
        if len(unknown)!=len(set(unknown)):
            raise ValueError('Duplicate unverified gate')
        if not row['reason'].strip():raise ValueError('Missing visual/causal reason')
        checks.append(dict(event_id=row['event_id'],status=row['status'],cause=row['cause'],
            conflict_kind='position_change' if row['status']=='conflict' else 'none',
            prompt_verdict=row['prompt_verdict'],prompt_fact_references=row['prompt_fact_references'],
            prompt_explanation=row['reason'],reason=row['reason'],
            witnesses=[copy.deepcopy(raw['witnesses'][i]) for i in ids],
            remaining_alternatives=row['remaining_alternatives'],
            **{g:g not in unknown for g in GATES}))
    return dict(checks=checks,limitations='Negative-cosine candidates only; no presence evaluation')


def review(stage, sid, graph, events, story, images):
    checks=[]
    for offset in range(0,len(events),32):
        batch=events[offset:offset+32]
        raw=stage.call(f'within_{sid}_{offset//32:03d}','within_spatial_v1.txt',
                       payload_for(graph,batch,story),images,SCHEMA)
        checks.extend(expand(raw,batch)['checks'])
    return dict(checks=checks,limitations='All negative spatial proposals reviewed; no presence evaluation')
