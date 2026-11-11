"""Versioned contracts for graph-first, witness-gated cross-shot consistency."""
VERSION='gs-consistency-v1.1'
def obj(**p):return dict(type='object',properties=p,required=list(p),additionalProperties=False)
def arr(t):return dict(type='array',items=t)
def enum(*x):return dict(type='string',enum=list(x))
S=dict(type='string');N=dict(type='number');I=dict(type='integer');B=dict(type='boolean')
GROUP=obj(group_id=S,a_ids=arr(S),b_ids=arr(S),identity=enum('matched','unmatched','ambiguous','scope_mismatch'),
          anchor_eligible=B,identity_evidence=S,anchor_reason=S)
MATCH_SCHEMA=obj(groups=arr(GROUP),scene_correspondence=S,limitations=S)
WITNESS=obj(shot_id=S,frame_id=I,region_xyxy=arr(N),observation=S)
CHECK=obj(group_id=S,verdict=enum('compatible','complement','conflict','unknown'),
    mechanism=enum('presence','layout','shape','none'),mapping_basis=enum('global_consensus','local_visual','none'),
    anchor_group_ids=arr(S),identity_supported=B,mapping_supported=B,visibility_supported=B,
    geometry_uncertainty_excluded=B,occlusion_excluded=B,detector_miss_excluded=B,
    alternative_mappings_excluded=B,affected_location=S,
    gs_evidence=S,visual_evidence=arr(WITNESS),counterfactual_test=S,alternative_explanations=S,reason=S)
CHECK_SCHEMA=obj(checks=arr(CHECK),limitations=S)
