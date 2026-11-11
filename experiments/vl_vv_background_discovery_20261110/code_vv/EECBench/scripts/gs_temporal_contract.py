"""Explicit expected-motion and event contracts for temporal consistency v2."""
from gs_consistency_contract import obj, arr, enum, S, I, B, WITNESS

INTERVAL = obj(start_frame_id=I, end_frame_id=I,
               expected=enum('static', 'reasonable_motion', 'unknown'),
               observed=enum('stationary', 'changed', 'unknown'),
               basis=enum('prompt', 'natural_dynamic', 'continuity', 'uncertain'),
               prompt_fact_references=arr(S), causal_explanation=S, visual_evidence=S)
EXPECTATION = obj(shot_id=S, camera_assessment=S, entities=arr(obj(
    entity_id=S, observed_status=enum('static', 'moving', 'unknown'),
    intervals=arr(INTERVAL), uncertainty=S)), limitations=S)

GATES = ['identity_supported', 'location_correspondence_supported',
         'observable_region_supported', 'occlusion_excluded', 'detector_gap_excluded',
         'geometry_error_excluded', 'viewpoint_only_explanation_excluded',
         'center_semantics_verified', 'common_support_verified',
         'reference_correspondence_verified', 'independent_local_order_verified']
CHECK = obj(event_id=S, status=enum('compatible', 'conflict', 'exempt', 'unknown'),
            cause=enum('inconsistency', 'reasonable_motion', 'viewpoint', 'occlusion',
                       'detector_gap', 'geometry_error', 'none'),
            conflict_kind=enum('unexplained_missing', 'unexplained_added',
                               'required_absent_but_present', 'position_change', 'none'),
            prompt_verdict=enum('explains_change', 'does_not_explain_change', 'uncertain'),
            prompt_fact_references=arr(S), prompt_explanation=S,
            witnesses=arr(WITNESS), reason=S, remaining_alternatives=S,
            **{key: B for key in GATES})
REVIEW = obj(checks=arr(CHECK), limitations=S)
# Presence never consumes the six spatial-only gates. Keep legacy REVIEW intact.
PRESENCE_GATES = GATES[:5]
PRESENCE_CHECK = obj(**{k:v for k,v in CHECK['properties'].items() if k not in GATES[5:]})
PRESENCE_REVIEW = obj(checks=arr(PRESENCE_CHECK), limitations=S)
LOCAL = obj(shot_id=S, relations=arr(obj(event_id=S,
    order_cross_anchor_up=enum('negative','positive','unknown'),
    order_toward_reference=enum('negative','positive','unknown'),
    order_vertical=enum('negative','positive','unknown'),
    reference_direction_verified=B, common_support_verified=B,
    center_semantics_verified=B, geometry_error_excluded=B,
    witnesses=arr(WITNESS), reason=S)), limitations=S)


def validate_expectation(review, payload):
    import jsonschema
    jsonschema.validate(review, EXPECTATION)
    if review['shot_id'] != payload['shot_id']:
        raise ValueError('Foreign shot expectation')
    if [e['entity_id'] for e in review['entities']] != [e['entity_id'] for e in payload['entities']]:
        raise ValueError('Expected-motion inventory/order changed')
    fids = [f['frame_id'] for f in payload['frames']]
    intervals = list(zip(fids, fids[1:]))
    facts = {f['fact_id'] for f in payload['normal_story_prompt']['facts']}
    for entity in review['entities']:
        if [(r['start_frame_id'], r['end_frame_id']) for r in entity['intervals']] != intervals:
            raise ValueError('Expected-motion intervals must exactly cover consecutive keyframes')
        for row in entity['intervals']:
            if not set(row['prompt_fact_references']) <= facts:
                raise ValueError('Unknown prompt reference')
            if not row['causal_explanation'].strip() or not row['visual_evidence'].strip():
                raise ValueError('Missing causal or visual evidence')
            if row['expected'] == 'reasonable_motion':
                if row['basis'] not in ('prompt', 'natural_dynamic'):
                    raise ValueError('Observed displacement alone cannot justify motion')
                if row['basis'] == 'prompt' and not row['prompt_fact_references']:
                    raise ValueError('Prompt motion requires prompt references')
            if row['expected'] == 'unknown' and row['basis'] != 'uncertain':
                raise ValueError('Unknown expectation needs uncertain basis')
