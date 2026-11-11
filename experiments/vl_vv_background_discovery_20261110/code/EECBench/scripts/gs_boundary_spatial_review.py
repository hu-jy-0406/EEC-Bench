"""Original Flow1 prompts/schemas with endpoint targets and all-keyframe evidence."""
import copy
import hashlib
import json
from pathlib import Path
from gs_relation_contract import SHOT_SCHEMA
from gs_flow1_contract import VERIFY
from gs_spatial_relations import basis
from run_gs_spatial_consistency import validate_single
from score_gs_spatial_consistency import VERIFY_GATES, validate_witnesses

AXES = ('cross_anchor_up', 'toward_reference', 'vertical')
PROMPTS = Path(__file__).resolve().parents[1] / 'prompts/gs_flow1'
SCOPE = '''

BOUNDARY TARGET SCOPE (user-requested adaptation; original evidence rules above remain):
Judge the supplied Shot1 final-frame and Shot3 first-frame states, identified by
target_frame_id/target_frames. Entity.geometry is unchanged target-frame geometry,
not a fused box. All original keyframes, cameras and frame_evidence are supplied.
Actively use other keyframes to establish body extent, center order, occlusion,
support and the physical reference, provided they support the target-frame state.
Retain >=2 distinct-frame witnesses per shot, including the target frame. Do not
replace target boxes, coordinates or numeric cosines with another frame or fusion.
All reviewed motion classes remain eligible; the old phrase 'static scene graphs'
does not authorize a static-only filter or blanket motion exemption.
Keep the original first-minus-second local sign convention and per-axis reliability:
uncertain vertical order does not invalidate supported horizontal order. Numeric
cosine uses second-minus-first in BOTH shots; reversing both preserves cosine.
'''


def restored_prompt(case, name):
    source = PROMPTS / name
    text = source.read_text() + SCOPE
    dest = Path(case) / 'boundary/restored_prompts' / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.read_text() != text:
        raise ValueError('Refuse changed spatial prompt within an existing run')
    dest.write_text(text)
    dest.with_suffix('.provenance.json').write_text(json.dumps(dict(
        original_prompt=str(source), original_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        adaptation='endpoint_state_all_keyframe_evidence_v1',
        full_sha256=hashlib.sha256(text.encode()).hexdigest()), indent=2)+'\n')
    return str(dest.resolve())


def endpoint_graphs(graphs, proposals):
    result = copy.deepcopy(graphs)
    for graph, target in zip(result, proposals['target_frames']):
        for entity in graph['entities']:
            row = next(r for r in entity['frame_evidence'] if r['frame_id'] == target['frame_id'])
            entity['geometry'] = copy.deepcopy(row.get('geometry')) if row.get('visible') and row.get('box_xyxy') is not None else None
        graph['geometry_role'] = 'exact_target_frame; all frame_evidence retained as context'
        graph['target_frame_id'] = target['frame_id']
    return result


def build_local_payloads(graphs, matching, proposals, image_lists):
    graphs = endpoint_graphs(graphs, proposals)
    groups = {g['group_id']:g for g in matching['groups']}
    refs = [matching.get('local_origin_group_id'), matching.get('local_reference_group_id')]
    refs_ok = len(set(refs)) == 2 and all(g in groups and groups[g]['identity'] == 'matched' for g in refs)
    events = [e for e in proposals['events'] if e['kind'] == 'spatial']
    eligible = [e for e in events if refs_ok and not set(refs) & set(e['endpoint_groups'])]
    payloads = []
    for side, (graph, images) in enumerate(zip(graphs, image_lists)):
        key = ('a_ids','b_ids')[side]
        nodes = {e['entity_id']:e for e in graph['entities']}
        ids = [groups[g][key][0] for g in refs] if refs_ok else []
        references = []
        if ids and all(nodes[e]['geometry'] is not None for e in ids):
            try:
                rotation, length = basis(*(nodes[e]['geometry']['center_world'] for e in ids), [0,0,1])
            except ValueError:
                pass
            else:
                references = [dict(origin_anchor_id=ids[0], reference_anchor_id=ids[1],
                                   basis_world=rotation.tolist(), up_world=[0,0,1], anchor_baseline=length)]
        targets = sorted({groups[g][key][0] for e in eligible for g in e['endpoint_groups']}) if references else []
        payloads.append(dict(graph=graph, target_frame_id=proposals['target_frames'][side]['frame_id'],
                             references=references, target_entity_ids=targets,
                             images=[dict(attachment_index=i+1,shot_id=f['shot_id'],frame_id=f['frame_id'],
                                          image_size=f['image_size']) for i,f in enumerate(images)]))
    return payloads


def endpoint_witnesses(rows, sid, target, images):
    return validate_witnesses(rows,sid,images) and target in {r['frame_id'] for r in rows}


def local_evidence(events, matching, observations, proposals, images):
    groups = {g['group_id']:g for g in matching['groups']}
    refs = [matching.get('local_origin_group_id'),matching.get('local_reference_group_id')]
    result = {}
    for event in events:
        local = []
        eligible = len(set(refs)) == 2 and all(g in groups for g in refs) and not set(refs) & set(event['endpoint_groups'])
        for side, raw in enumerate(observations):
            found = {}
            if eligible:
                key = ('a_ids','b_ids')[side]
                ids = [groups[g][key][0] for g in event['endpoint_groups']]
                anchors = [groups[g][key][0] for g in refs]
                for row in raw['relations']:
                    if [row['subject_id'],row['object_id']] == sorted(ids) and [row['origin_anchor_id'],row['reference_anchor_id']] == anchors:
                        row = copy.deepcopy(row)
                        # Preserve the original row, IDs, witnesses and prose together.
                        # Negating only its order used to contradict its subject/object
                        # and reason. Put derived arithmetic in a separate explicit row.
                        canonical_order = row['order'] if ids == sorted(ids) else {
                            'positive':'negative','negative':'positive','unknown':'unknown'}[row['order']]
                        row['canonical_relation'] = dict(subject_id=ids[0], object_id=ids[1],
                            order=canonical_order, center_subtraction='canonical subject center minus canonical object center',
                            derived_from_original_by='identity' if ids == sorted(ids) else 'swap endpoints and negate order')
                        found[row['axis']] = row
            local.append(found)
        axes = {}
        for axis in AXES:
            passed, orders = [], []
            for side, rows in enumerate(local):
                row = rows.get(axis)
                if row is None:
                    passed.append(False); orders.append(0); continue
                target = proposals['target_frames'][side]
                order = {'positive':1,'negative':-1,'unknown':0}[row['canonical_relation']['order']]
                orders.append(order)
                passed.append(bool(endpoint_witnesses(row['evidence'],target['shot_id'],target['frame_id'],images)
                                   and row['reference_direction_verified'] and row['common_support_verified']
                                   and row['center_order_supported'] and not row['geometry_error_can_reverse'] and order))
            axes[axis] = dict(per_shot_evidence_pass=passed,orders=orders,
                              opposite_supported=all(passed) and orders[0]*orders[1] == -1)
        result[event['event_id']] = dict(
            common_support_eligible=eligible and all(set(r) == set(AXES) for r in local),
            opposite_supported=any(r['opposite_supported'] for r in axes.values()),
            local_axis_evidence=axes, observations=local)
    return result


def finalize(events, raw, support, proposals, images, story, presence):
    import jsonschema
    jsonschema.validate(raw,VERIFY)
    eligible = [e['event_id'] for e in events if support[e['event_id']]['common_support_eligible']]
    if [r['relation_id'] for r in raw['relations']] != eligible:
        raise ValueError('Spatial verifier changed candidate coverage/order')
    verified = {r['relation_id']:r for r in raw['relations']}
    facts = {r['fact_id'] for r in story['facts']}
    output = {}
    for event in events:
        eid = event['event_id']; v = verified.get(eid)
        if v is None:
            output[eid] = dict(event,status='unknown',gate_reason='no_verified_common_support_or_reference',
                               local_axis_evidence=support[eid]['local_axis_evidence'],
                               review=dict(cause='none', reason='No independently verified common support/reference.',
                                           prompt_explanation='No final spatial review; evidence remains unknown.',
                                           source='deterministic_eligibility_gate'))
            continue
        pr = v['prompt_motion_review']
        if not set(pr['prompt_fact_references']) <= facts:
            raise ValueError('Unknown spatial prompt fact')
        prompt_ok = bool(pr['prompt_fact_references']) and all(pr[k].strip() for k in ['specified_motion','causal_explanation_of_observed_relation_change'])
        witnesses_ok = all(endpoint_witnesses(v['witnesses_'+side],target['shot_id'],target['frame_id'],images)
                           for side,target in zip(['a','b'],proposals['target_frames']))
        visual = v['verdict'] == 'conflict' and all(v[k] for k in VERIFY_GATES) and witnesses_ok and support[eid]['opposite_supported']
        status, reason = 'unknown','failed_visual_or_prompt_motion_gate'
        if prompt_ok and pr['verdict'] == 'explains_change' and witnesses_ok:
            status, reason = 'exempt','prompt_motion_explains_specific_relation_change'
        elif prompt_ok and pr['verdict'] == 'does_not_explain_change' and visual:
            status, reason = 'conflict','negative_cosine_and_independent_local_opposite_order_and_visual_gates_and_prompt_motion_excluded'
            if not all(presence.get(g) == 'compatible' for g in event['endpoint_groups']):
                status, reason = 'unknown','boundary_joint_presence_not_supported'
        output[eid] = dict(event,status=status,gate_reason=reason,verification=v,
                           review=dict(cause='inconsistency' if status=='conflict' else 'reasonable_motion' if status=='exempt' else 'none',
                                       reason=v['reason'],prompt_explanation=pr['causal_explanation_of_observed_relation_change'],
                                       source='original_flow1_verification_summary'),
                           target_witness_gate=witnesses_ok,prompt_gate=prompt_ok,visual_gate=bool(visual),
                           local_axis_evidence=support[eid]['local_axis_evidence'])
    return output


def collect_spatial(stage, graphs, matching, proposals, registration, image_lists):
    """Independent visual calls; joint-presence gating waits at finalization."""
    events = [e for e in proposals['events'] if e['kind'] == 'spatial']
    if not events:
        return None
    payloads = build_local_payloads(graphs,matching,proposals,image_lists)
    local_prompt = restored_prompt(stage.case,'gs_relation_shot_v1.txt')
    def observe(item):
        payload, images = item
        if payload['target_entity_ids']:
            raw = stage.call('boundary_local_'+payload['graph']['shot_id'],
                             local_prompt,payload,images,SHOT_SCHEMA)
            return validate_single(raw,payload)
        return dict(shot_id=payload['graph']['shot_id'],placements=[],relations=[],limitations='no independent reference')
    if getattr(stage, 'runtime', {}).get('temporal_parallel_local_spatial', False):
        # Each context still receives only its own shot; final review waits for both.
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as pool:
            observations = list(pool.map(observe, zip(payloads,image_lists)))
    else:
        observations = [observe(item) for item in zip(payloads,image_lists)]
    images = sum(image_lists,[])
    support = local_evidence(events,matching,observations,proposals,images)
    (stage.case/'boundary/local_support.json').write_text(json.dumps(support,ensure_ascii=False,indent=2)+'\n')
    relations = [dict(event,relation_id=event['event_id'],anchor_groups=[matching['local_origin_group_id'],matching['local_reference_group_id']],
                      local_observations=support[event['event_id']]['observations'],
                      local_axis_evidence=support[event['event_id']]['local_axis_evidence'])
                 for event in events if support[event['event_id']]['common_support_eligible']]
    verified = dict(relations=[],limitations='no eligible negative proposal')
    if relations:
        fit = registration['fits']['all_structures']
        payload = dict(graphs=endpoint_graphs(graphs,proposals),matching=matching,relations=relations,
                       target_frames=proposals['target_frames'],normal_story_prompt=stage.story,
                       proposed_transform_shot3_scene_to_shot1_scene={k:fit[k] for k in ['scale','rotation','translation']},
                       registration_diagnostics=registration,
                       numerical_interface='negative endpoint cosine; first-minus-second local order; all keyframes available as evidence')
        verified = stage.call('boundary_spatial_verify',restored_prompt(stage.case,'verify_cosine.txt'),payload,images,VERIFY)
    return dict(events=events,raw=verified,support=support)


def finish_spatial(stage, collected, proposals, image_lists, presence):
    if collected is None:
        return {}
    return finalize(**collected,proposals=proposals,images=sum(image_lists,[]),story=stage.story,presence=presence)


def review_spatial(stage, graphs, matching, proposals, registration, image_lists, presence):
    collected=collect_spatial(stage,graphs,matching,proposals,registration,image_lists)
    return finish_spatial(stage,collected,proposals,image_lists,presence)
