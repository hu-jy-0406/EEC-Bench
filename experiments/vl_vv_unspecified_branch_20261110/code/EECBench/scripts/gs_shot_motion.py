"""Whole-shot binary expected motion; no temporal expansion or observed classifier."""
import copy
from gs_consistency_contract import obj, arr, enum, S, I

PROTOCOL = 'shot_binary_v1'
SCHEMA = obj(shot_id=S, entities=arr(obj(
    entity_id=S, motion_status=enum('static', 'moving'),
    basis=enum('prompt', 'natural_dynamic', 'no_supported_motion'),
    prompt_fact_references=arr(S), witness_frame_ids=arr(I), reason=S)))


def validate(review, payload):
    import jsonschema
    jsonschema.validate(review, SCHEMA)
    if review['shot_id'] != payload['shot_id']:
        raise ValueError('Foreign shot classification')
    if [e['entity_id'] for e in review['entities']] != [e['entity_id'] for e in payload['entities']]:
        raise ValueError('Binary motion inventory/order changed')
    facts = {f['fact_id'] for f in payload['normal_story_prompt']['facts']}
    fids = {f['frame_id'] for f in payload['frames']}
    for e in review['entities']:
        if not e['reason'].strip():
            raise ValueError('Missing motion classification reason')
        if not set(e['prompt_fact_references']) <= facts:
            raise ValueError('Foreign prompt fact')
        if not set(e['witness_frame_ids']) <= fids or len(e['witness_frame_ids']) > 2:
            raise ValueError('Invalid binary motion witnesses')
        if e['motion_status'] == 'moving':
            if e['basis'] not in ('prompt', 'natural_dynamic'):
                raise ValueError('Displacement alone cannot authorize motion')
            if e['basis'] == 'prompt' and not e['prompt_fact_references']:
                raise ValueError('Prompt motion requires a fact reference')
            if e['basis'] == 'natural_dynamic' and not e['witness_frame_ids']:
                raise ValueError('Natural motion requires original-frame evidence')
        elif e['basis'] != 'no_supported_motion':
            raise ValueError('Static means no supported legitimate motion')


def classification_geometry(g):
    if not g:
        return None
    result = {k: copy.deepcopy(g[k]) for k in ('center_world', 'size_xyz', 'R_world_from_object')}
    if 'corners_world' in g:
        from gs_flow1_compact_payload import obb_corners
        actual = g['corners_world']
        try:
            expected = obb_corners(g)
            derived = (len(actual) == 8 and all(len(row) == 3 for row in actual)
                       and all(abs(x-y) <= 1e-9 for a,b in zip(actual,expected) for x,y in zip(a,b)))
        except (TypeError, ValueError, KeyError, IndexError):
            derived = False
        if not derived:
            result['corners_world'] = copy.deepcopy(actual)
    return result


def classification_payload(full):
    """Keep defining camera/OBB numbers and every observation; omit fusion diagnostics.

    The caller preserves full canonical evidence separately. Geometry is solely
    corroborating for this classification; no scoring geometry is reconstructed.
    """
    result = {k: copy.deepcopy(full[k]) for k in ('shot_id', 'frames', 'normal_story_prompt')}
    result['motion_classification_protocol'] = PROTOCOL
    result['observation_semantics'] = 'Null/missing retained boxes are unknown observations, never proof of absence. Static means no supported motion exemption, not observed stability.'
    result['cameras'] = [{k: copy.deepcopy(c[k]) for k in
                          ('frame_id', 'image_size', 'K', 'R_world_from_camera', 'position_world', 'translation_world_from_camera') if k in c}
                         for c in full['cameras']]
    result['entities'] = []
    for e in full['entities']:
        rows = []
        for row in e['frame_evidence']:
            g = row.get('geometry')
            rows.append(dict(frame_id=row['frame_id'], visible=row['visible'],
                             box_xyxy=copy.deepcopy(row['box_xyxy']),
                             geometry=classification_geometry(g)))
        result['entities'].append(dict(entity_id=e['entity_id'], name=e['name'], frame_evidence=rows))
    return result


def node_fields(verdict):
    return dict(motion_status=verdict['motion_status'], motion_classification_protocol=PROTOCOL,
                motion_status_role='whole-shot expected reasonable motion; static is not observed anchor stability',
                motion_evidence={k: copy.deepcopy(verdict[k]) for k in
                                 ('basis', 'prompt_fact_references', 'witness_frame_ids', 'reason')})
