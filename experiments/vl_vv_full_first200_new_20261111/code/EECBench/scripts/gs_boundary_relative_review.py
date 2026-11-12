"""Gravity-free boundary review: isolated image evidence, then relative geometry.

No prescribed physical axes, gravity, signed coordinate ordering or fitted plane
normal. Numeric negative cosines only propose candidates. Independent original
pixel witnesses, common support and corresponding external references remain
mandatory for a confirmed conflict. Presence and normal-story gates remain.
"""
from concurrent.futures import ThreadPoolExecutor
from gs_consistency_contract import obj,arr,enum,S,B,WITNESS
from gs_boundary_spatial_review import endpoint_graphs

LOCAL_ROW=obj(event_id=S,entity_ids=arr(S),evidence_status=enum('supported','unknown'),
              support_entity_id=S,reference_entity_ids=arr(S),support_verified=B,
              reference_verified=B,center_semantics_verified=B,
              relative_geometry_description=S,witnesses=arr(WITNESS),remaining_alternatives=S)
LOCAL=obj(shot_id=S,relations=arr(LOCAL_ROW),limitations=S)
GATES=('identity_supported','common_support_verified','reference_correspondence_verified',
       'center_semantics_verified','relative_change_verified','geometry_error_excluded',
       'viewpoint_only_explanation_excluded')
PROMPT=obj(verdict=enum('explains_change','does_not_explain_change','uncertain'),
           prompt_fact_references=arr(S),specified_motion=S,affected_entities=arr(S),
           causal_explanation_of_observed_relation_change=S)
VERIFY=obj(relations=arr(obj(event_id=S,verdict=enum('conflict','compatible','unknown'),
                            **{k:B for k in GATES},witnesses_a=arr(WITNESS),witnesses_b=arr(WITNESS),
                            prompt_motion_review=PROMPT,reason=S,remaining_alternatives=S)),limitations=S)


def endpoint_witnesses(rows,sid,target,images):
    import math
    index={f['frame_id']:f for f in images if f['shot_id']==sid}
    for w in rows:
        if w['shot_id']!=sid or w['frame_id'] not in index:raise ValueError('Foreign witness')
        W,H=index[w['frame_id']]['image_size'];b=w['region_xyxy']
        if len(b)!=4 or not all(math.isfinite(x) for x in b) or not (0<=b[0]<b[2]<=W and 0<=b[1]<b[3]<=H) or not w['observation'].strip():
            raise ValueError('Invalid original-pixel witness')
    fids={w['frame_id'] for w in rows}
    return target in fids and len(fids)>=2


def local_payloads(graphs,matching,proposals):
    gm={g['group_id']:g for g in matching['groups']}
    events=[e for e in proposals['events'] if e['kind']=='spatial']
    out=[]
    for side,(graph,key) in enumerate(zip(endpoint_graphs(graphs,proposals),('a_ids','b_ids'))):
        rows=[dict(event_id=e['event_id'],entity_ids=[gm[g][key][0] for g in e['endpoint_groups']]) for e in events]
        out.append(dict(graph=graph,target_frame_id=proposals['target_frames'][side]['frame_id'],
                        relations=rows,coordinate_convention='arbitrary fixed own-shot axes; no physical-up estimate'))
    return out


def validate_local(raw,payload,images):
    import jsonschema
    jsonschema.validate(raw,LOCAL)
    sid=payload['graph']['shot_id'];target=payload['target_frame_id']
    if raw['shot_id']!=sid:raise ValueError('Foreign shot')
    if [r['event_id'] for r in raw['relations']]!=[r['event_id'] for r in payload['relations']]:
        raise ValueError('Changed local event population')
    nodes={e['entity_id'] for e in payload['graph']['entities']}
    for row,event in zip(raw['relations'],payload['relations']):
        if row['entity_ids']!=event['entity_ids']:raise ValueError('Changed endpoint order')
        refs=row['reference_entity_ids']
        if len(refs)!=len(set(refs)) or not set(refs)<=nodes-set(row['entity_ids']):
            raise ValueError('Invalid independent reference')
        if row['support_entity_id'] and row['support_entity_id'] not in nodes-set(row['entity_ids']):
            raise ValueError('Invalid common support')
        # Invalid decisive evidence is downgraded at deterministic final gates;
        # invented witness indices/rectangles are rejected regardless of verdict.
        index={f['frame_id']:f for f in images if f['shot_id']==sid}
        for w in row['witnesses']:
            if w['shot_id']!=sid or w['frame_id'] not in index:raise ValueError('Foreign witness')
            W,H=index[w['frame_id']]['image_size'];box=w['region_xyxy']
            if len(box)!=4 or not (0<=box[0]<box[2]<=W and 0<=box[1]<box[3]<=H) or not w['observation'].strip():
                raise ValueError('Invalid local original-frame witness')
    return raw


def support_for(events,matching,observations,proposals,images):
    # Only confirmed one-to-one identities can establish cross-shot landmarks.
    maps=[{g[key][0]:g['group_id'] for g in matching['groups'] if g['identity']=='matched'}
          for key in ('a_ids','b_ids')]
    result={}
    tables=[{r['event_id']:r for r in o['relations']} for o in observations]
    for event in events:
        rows=[table[event['event_id']] for table in tables]
        ready=[];supports=[];references=[]
        for i,row in enumerate(rows):
            target=proposals['target_frames'][i]
            ready.append(row['evidence_status']=='supported' and row['support_verified'] and row['reference_verified']
                         and row['center_semantics_verified'] and bool(row['relative_geometry_description'].strip())
                         and endpoint_witnesses(row['witnesses'],target['shot_id'],target['frame_id'],images))
            supports.append(maps[i].get(row['support_entity_id']))
            references.append({maps[i][e] for e in row['reference_entity_ids'] if e in maps[i]})
        common=sorted(references[0]&references[1]-set(event['endpoint_groups']))
        eligible=all(ready) and supports[0] is not None and supports[0]==supports[1] and bool(common)
        result[event['event_id']]=dict(eligible=bool(eligible),local_evidence_pass=ready,
             common_support_group=supports[0] if supports[0]==supports[1] else None,
             shared_reference_groups=common,observations=rows)
    return result


def collect_spatial(stage,graphs,matching,proposals,registration,image_lists):
    events=[e for e in proposals['events'] if e['kind']=='spatial']
    if not events:return None
    payloads=local_payloads(graphs,matching,proposals)
    def observe(item):
        payload,images=item
        raw=stage.call('boundary_local_'+payload['graph']['shot_id'],'relative_geometry_shot_v1.txt',payload,images,LOCAL)
        return validate_local(raw,payload,images)
    with ThreadPoolExecutor(max_workers=2) as pool:
        observations=list(pool.map(observe,zip(payloads,image_lists)))
    images=sum(image_lists,[]);support=support_for(events,matching,observations,proposals,images)
    from run_gs_temporal_stage import save
    save(stage.case/'boundary/relative_local_support.json',support)
    relations=[dict(event,local_evidence=support[event['event_id']]) for event in events]
    # All proposals remain visible; the final judge cannot override failed local
    # evidence gates. No target-count assumptions or expected anomalies supplied.
    payload=dict(graphs=endpoint_graphs(graphs,proposals),matching=matching,relations=relations,
                 target_frames=proposals['target_frames'],normal_story_prompt=stage.story,
                 frozen_transform=registration['fits']['all_structures'],
                 coordinate_convention='arbitrary scene coordinates; full proper SO(3) registration; no gravity',
                 numeric_role='negative cosine is a candidate only, not independent visual proof')
    raw=stage.call('boundary_spatial_verify','relative_geometry_verify_v1.txt',payload,images,VERIFY)
    return dict(events=events,raw=raw,support=support)


def finish_spatial(stage,collected,proposals,image_lists,presence):
    if collected is None:return {}
    import jsonschema
    raw=collected['raw'];jsonschema.validate(raw,VERIFY)
    if [r['event_id'] for r in raw['relations']]!=[e['event_id'] for e in collected['events']]:
        raise ValueError('Changed relative review event population')
    images=sum(image_lists,[]);facts={f['fact_id'] for f in stage.story['facts']};output={}
    for event,v in zip(collected['events'],raw['relations']):
        pr=v['prompt_motion_review'];local=collected['support'][event['event_id']]
        if not set(pr['prompt_fact_references'])<=facts:raise ValueError('Foreign prompt fact')
        if not set(pr['affected_entities'])<=set(event['entity_ids']):raise ValueError('Foreign affected endpoint')
        prompt_ok=bool(pr['prompt_fact_references']) and bool(pr['specified_motion'].strip()) and bool(pr['causal_explanation_of_observed_relation_change'].strip())
        witness_ok=all(endpoint_witnesses(v['witnesses_'+side],target['shot_id'],target['frame_id'],images)
                       for side,target in zip(('a','b'),proposals['target_frames']))
        visual=local['eligible'] and witness_ok and all(v[k] for k in GATES)
        status,reason='unknown','insufficient_relative_geometry_or_causal_evidence'
        if prompt_ok and witness_ok and pr['verdict']=='explains_change':
            status,reason='exempt','normal_story_explains_specific_relative_change'
        elif prompt_ok and pr['verdict']=='does_not_explain_change' and v['verdict']=='conflict' and visual:
            if all(presence.get(g)=='compatible' for g in event['endpoint_groups']):
                status,reason='conflict','independent_relative_geometry_and_original_pixels_exclude_viewpoint_geometry_and_prompt_motion'
            else:reason='boundary_joint_presence_not_supported'
        output[event['event_id']]=dict(event,status=status,gate_reason=reason,verification=v,
           target_witness_gate=witness_ok,prompt_gate=prompt_ok,visual_gate=bool(visual),relative_evidence=local,
           review=dict(cause='inconsistency' if status=='conflict' else 'reasonable_motion' if status=='exempt' else 'none',
                       reason=v['reason'],prompt_explanation=pr['causal_explanation_of_observed_relation_change'],source='relative_geometry_v1'))
    return output


def review_spatial(stage,graphs,matching,proposals,registration,image_lists,presence):
    return finish_spatial(stage,collect_spatial(stage,graphs,matching,proposals,registration,image_lists),proposals,image_lists,presence)
