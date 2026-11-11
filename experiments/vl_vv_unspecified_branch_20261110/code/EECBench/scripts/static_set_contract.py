"""Static-set-only cross-shot scoring contracts, v1.3."""
from gs_consistency_contract import obj, arr, enum, S, B, WITNESS

VERSION = 'gs-static-set-v1.3'
POLICY_ROW = obj(group_id=S, presence=enum('persist', 'change_allowed', 'unknown'),
                 layout=enum('stable', 'change_allowed', 'unknown'),
                 prompt_fact_ids=arr(S), allowed_change_scope=S, reason=S)
POLICY_SCHEMA = obj(groups=arr(POLICY_ROW), limitations=S)
PRESENCE_GATES = ['identity', 'mapping', 'observable', 'occlusion_excluded',
                  'detector_miss_excluded', 'alternative_mapping_excluded',
                  'motion_excluded', 'story_excluded']
RELATION_GATES = ['identity', 'mapping', 'observable', 'geometry_error_excluded',
                  'viewpoint_excluded', 'reference_stable', 'story_excluded']
PRESENCE_ROW = obj(group_id=S,
    category=enum('motion_transition', 'viewpoint', 'story', 'inconsistent', 'detection_gap', 'unknown'),
    counterpart_id=dict(type=['string', 'null']), anchor_group_ids=arr(S),
    evidence=arr(WITNESS), gates=obj(**{k:B for k in PRESENCE_GATES}), reason=S)
PRESENCE_SCHEMA = obj(checks=arr(PRESENCE_ROW), limitations=S)
RELATION_ROW = obj(pair_id=S, verdict=enum('compatible', 'conflict', 'allowed_change', 'unknown'),
    predicate=enum('order_reversal', 'support_change', 'relative_placement', 'none'),
    numeric_relation_ids=arr(S), anchor_group_ids=arr(S), evidence=arr(WITNESS),
    gates=obj(**{k:B for k in RELATION_GATES}), reason=S)
RELATION_SCHEMA = obj(checks=arr(RELATION_ROW), limitations=S)
