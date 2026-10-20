import copy,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from gs_consistency_contract import obj,arr,enum,S,N,I,B,GROUP,WITNESS
from gs_relation_contract import VERIFY_SCHEMA
MATCH=obj(groups=arr(GROUP),scene_correspondence=S,limitations=S,structural_anchor_group_ids=arr(S),local_origin_group_id=S,local_reference_group_id=S,reference_selection_reason=S)
GATES=['identity_supported','location_correspondence_supported','observable_region_supported','occlusion_excluded','detector_gap_excluded','prompt_review_completed']
PRESENCE_ROW=obj(group_id=S,partition=enum('common_static','noncommon_static','unresolved'),cause=enum('viewpoint','motion','inconsistency','none'),status=enum('compatible','conflict','exempt','unknown'),conflict_kind=enum('unexplained_missing','unexplained_added','required_absent_but_present','none'),joint_presence_reasonable=B,prompt_fact_references=arr(S),prompt_explanation=S,witnesses=arr(WITNESS),reason=S,**{k:B for k in GATES})
PRESENCE=obj(checks=arr(PRESENCE_ROW),limitations=S)
VERIFY=copy.deepcopy(VERIFY_SCHEMA)
fields=dict(prompt_fact_references=arr(S),specified_motion=S,affected_entities=arr(S),causal_explanation_of_observed_relation_change=S,verdict=enum('explains_change','does_not_explain_change','uncertain'))
VERIFY['properties']['relations']['items']['properties']['prompt_motion_review']=obj(**fields)
VERIFY['properties']['relations']['items']['required'].append('prompt_motion_review')
