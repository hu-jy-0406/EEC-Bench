"""Spatial relation observations, independently grounded per shot."""
from gs_consistency_contract import obj,arr,enum,S,N,I,B
NULLSTR=dict(anyOf=[S,dict(type='null')])
BOX=arr(N)
W=obj(frame_id=I,subject_region_xyxy=BOX,object_region_xyxy=BOX,reference_region_xyxy=BOX,observation=S)
PLACEMENT=obj(entity_id=S,support_entity_id=NULLSTR,support_verified=B,frame_ids=arr(I),reason=S)
REL=obj(subject_id=S,object_id=S,origin_anchor_id=S,reference_anchor_id=S,axis=enum('cross_anchor_up','toward_reference','vertical'),
    order=enum('negative','positive','unknown'),reference_direction_verified=B,common_support_verified=B,
    center_order_supported=B,geometry_error_can_reverse=B,evidence=arr(W),reason=S,uncertainty=S)
SHOT_SCHEMA=obj(shot_id=S,placements=arr(PLACEMENT),relations=arr(REL),limitations=S)
VERIFY=obj(relation_id=S,verdict=enum('conflict','compatible','unknown'),identity_supported=B,anchors_supported=B,
    common_support_verified=B,reference_correspondence_verified=B,center_semantics_verified=B,
    geometry_error_excluded=B,viewpoint_only_explanation_excluded=B,
    witnesses_a=arr(W),witnesses_b=arr(W),reason=S,remaining_alternatives=S)
VERIFY_SCHEMA=obj(relations=arr(VERIFY),limitations=S)
