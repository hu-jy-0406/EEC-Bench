"""Witness gates and isolated local observations for temporal v2."""
from gs_temporal_contract import REVIEW, LOCAL, PRESENCE_REVIEW


def witness_keys(witnesses, images):
    index = {(f['shot_id'],f['frame_id']): f for f in images}
    keys = set()
    for w in witnesses:
        key = (w['shot_id'],w['frame_id'])
        if key not in index:
            raise ValueError('Foreign witness frame')
        W,H = index[key]['image_size']; b = w['region_xyxy']
        if len(b)!=4 or not (0<=b[0]<b[2]<=W and 0<=b[1]<b[3]<=H) or not w['observation'].strip():
            raise ValueError('Invalid original-pixel witness')
        keys.add(key)
    return keys


def validate_checks(raw, proposals, images, story, boundary=False, local_support=None, presence_only_schema=False):
    import jsonschema
    if presence_only_schema and any(e['kind']!='presence' for e in proposals['events']):
        raise ValueError('Presence schema cannot validate spatial events')
    jsonschema.validate(raw, PRESENCE_REVIEW if presence_only_schema else REVIEW)
    if [r['event_id'] for r in raw['checks']] != [r['event_id'] for r in proposals['events']]:
        raise ValueError('Event coverage/order mismatch')
    facts = {f['fact_id'] for f in story['facts']}; result = {}
    for event, check in zip(proposals['events'],raw['checks']):
        if not set(check['prompt_fact_references']) <= facts:
            raise ValueError('Unknown prompt fact')
        targets = {(t['shot_id'],t['frame_id']) for t in event['target_frames']}
        keys = witness_keys(check['witnesses'],images)
        witness_ok = targets <= keys
        if not boundary and event['kind']=='presence':
            sid = event['target_frames'][0]['shot_id']
            witness_ok &= any((sid,f) in keys for f in event.get('context_frame_ids',[]))
        prompt_ok = bool(check['prompt_fact_references']) and bool(check['prompt_explanation'].strip())
        visual = all(check[k] for k in ('identity_supported','location_correspondence_supported',
                                      'observable_region_supported','occlusion_excluded','detector_gap_excluded'))
        if event['kind']=='spatial':
            visual &= all(check[k] for k in ('geometry_error_excluded','viewpoint_only_explanation_excluded',
                         'center_semantics_verified','common_support_verified',
                         'reference_correspondence_verified','independent_local_order_verified'))
            if boundary:
                visual &= bool((local_support or {}).get(event['event_id'],{}).get('opposite_supported'))
        status = check['status']; why = 'accepted'
        if check['prompt_verdict']=='uncertain':
            status,why = 'unknown','uncertain_prompt_cause'
        elif status=='conflict':
            kinds = ['position_change'] if event['kind']=='spatial' else ['unexplained_missing','unexplained_added','required_absent_but_present']
            if not (witness_ok and prompt_ok and visual and check['prompt_verdict']=='does_not_explain_change'
                    and check['cause']=='inconsistency' and check['conflict_kind'] in kinds):
                status,why = 'unknown','failed_conflict_evidence_gate'
        elif status=='compatible':
            if not (witness_ok and prompt_ok and check['identity_supported'] and check['observable_region_supported']
                    and check['conflict_kind']=='none'):
                status,why = 'unknown','failed_compatibility_evidence_gate'
        elif status=='exempt':
            cause_ok = check['cause'] in ('viewpoint','occlusion') or (
                check['cause']=='reasonable_motion' and check['prompt_verdict']=='explains_change')
            if not (witness_ok and prompt_ok and cause_ok and check['identity_supported'] and check['conflict_kind']=='none'):
                status,why = 'unknown','failed_exemption_evidence_gate'
        result[event['event_id']] = dict(event, status=status, gate_reason=why,
                                         target_witness_gate=witness_ok, prompt_gate=prompt_ok,
                                         visual_gate=bool(visual), review=check)
    if boundary:
        presence={event['group_id']:result[event['event_id']]['status']
                  for event in proposals['events'] if event['kind']=='presence' and 'group_id' in event}
        for event in proposals['events']:
            if event['kind']=='spatial' and result[event['event_id']]['status']=='conflict':
                if not all(presence.get(g)=='compatible' for g in event.get('endpoint_groups',[])):
                    result[event['event_id']].update(status='unknown',gate_reason='boundary_joint_presence_not_supported')
    return result


def local_payloads(graphs, matching, proposals):
    groups = {g['group_id']:g for g in matching['groups']}
    refs = [matching.get('local_origin_group_id'),matching.get('local_reference_group_id')]
    good_refs = len(set(refs))==2 and all(r in groups and groups[r]['identity']=='matched' for r in refs)
    events = [e for e in proposals['events'] if e['kind']=='spatial']
    eligible = [e for e in events if good_refs and not set(refs)&set(e['endpoint_groups'])]
    payloads = []
    for side, graph in enumerate(graphs):
        key = ('a_ids','b_ids')[side]; target = proposals['target_frames'][side]
        reference_ids = [groups[r][key][0] for r in refs] if good_refs else []
        target_nodes = proposals['endpoint_observations'][side]
        refs_present = all(target_nodes[eid].get('geometry') is not None and target_nodes[eid].get('visible') for eid in reference_ids)
        requests = [dict(event_id=e['event_id'], entity_ids=[groups[g][key][0] for g in e['endpoint_groups']])
                    for e in eligible] if refs_present else []
        # Own-shot geometry only: transformed endpoints are for numeric comparison,
        # never leak the cross-shot transform into the independent observer.
        own_rows = {e['entity_id']:next(r for r in e['frame_evidence'] if r['frame_id']==target['frame_id'])
                    for e in graph['entities']}
        payloads.append(dict(shot_id=graph['shot_id'], target_frame_id=target['frame_id'],
                             graph=graph, endpoint_observations=own_rows,
                             reference_entity_ids=reference_ids, up_world=[0,0,1], relations=requests))
    return payloads


def local_gate(raws, payloads, image_lists):
    import jsonschema
    maps=[]
    for raw,payload,images in zip(raws,payloads,image_lists):
        jsonschema.validate(raw,LOCAL)
        if raw['shot_id']!=payload['shot_id'] or [r['event_id'] for r in raw['relations']] != [r['event_id'] for r in payload['relations']]:
            raise ValueError('Isolated local observation coverage mismatch')
        checked={}
        for r in raw['relations']:
            target=(payload['shot_id'],payload['target_frame_id'])
            witness=target in witness_keys(r['witnesses'],images)
            supported=witness and all(r[k] for k in ('reference_direction_verified','common_support_verified',
                                                    'center_semantics_verified','geometry_error_excluded'))
            checked[r['event_id']]=dict(row=r,supported=supported)
        maps.append(checked)
    result={}
    for eid in set(maps[0])&set(maps[1]):
        rows=[m[eid] for m in maps]
        axes=[axis for axis in ('order_cross_anchor_up','order_toward_reference','order_vertical')
              if {r['row'][axis] for r in rows}=={'negative','positive'}]
        result[eid]=dict(opposite_supported=bool(axes) and all(r['supported'] for r in rows),
                         opposite_axes=axes,observations=[r['row'] for r in rows])
    return result
