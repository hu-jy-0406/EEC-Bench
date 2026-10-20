import sys,copy,json
from pathlib import Path
H=Path(__file__).resolve().parent;sys.path.insert(0,str(H.parents[1]/'scripts'))
from review_aligned_entity_identities import validate,read,save
from run_isolated_shot_static_3d import owned_compute_job
owned_compute_job();p=read(H/'study2/identity_review_payload.json');m=copy.deepcopy(p['initial_matching'])
def single(g):return dict(group_id=g['group_id'],cause='none',evidence_status='unknown',counterpart_visibility='uncertain',reason='synthetic contract test',prompt_fact_references=[],witnesses=[])
r=dict(matching=m,initial_group_reviews=[dict(initial_group_id=g['group_id'],action='keep',result_group_ids=[g['group_id']],geometry_interpretation='test',visual_identity_evidence='test',same_instance_motion_alternative='test',witnesses=[]) for g in m['groups']],noncommon_checks=[single(g) for g in m['groups'] if g['identity']=='unmatched'],registration_caveats='test',limitations='synthetic only')
validate(r,p);checks=['large_displacement_does_not_automatically_split']
g=next(g for g in m['groups'] if g['group_id']=='g16');a=copy.deepcopy(g);b=copy.deepcopy(g);a.update(group_id='g16a',b_ids=[],identity='unmatched',anchor_eligible=False);b.update(group_id='g16b',a_ids=[],identity='unmatched',anchor_eligible=False)
r['matching']['groups']=[x for x in m['groups'] if x['group_id']!='g16']+[a,b];r['matching']['structural_anchor_group_ids'].remove('g16');rv=next(x for x in r['initial_group_reviews'] if x['initial_group_id']=='g16');rv.update(action='split',result_group_ids=['g16a','g16b'])
for shot,eid in [(p['shots'][0],a['a_ids'][0]),(p['shots'][1],b['b_ids'][0])]:
 e=next(e for e in shot['entities'] if e['entity_id']==eid);obs=next(o for o in e['observations'] if o['visible'] and o['box_xyxy']);rv['witnesses'].append(dict(shot_id=shot['shot_id'],frame_id=obs['frame_id'],region_xyxy=obs['box_xyxy'],observation='synthetic valid witness'))
r['noncommon_checks'] +=[single(a),single(b)];validate(r,p);checks.append('split_conserves_two_instances_and_removes_anchor')
def reject(name,edit):
 q=copy.deepcopy(r);edit(q)
 try:validate(q,p)
 except (AssertionError,KeyError):checks.append(name)
 else:raise AssertionError('Failed to reject '+name)
reject('duplicate_entity_rejected',lambda q:q['matching']['groups'][-1]['b_ids'].append(b['b_ids'][0]))
reject('dropped_entity_rejected',lambda q:q['matching']['groups'].pop())
reject('split_without_two_shot_witnesses_rejected',lambda q:next(x for x in q['initial_group_reviews'] if x['initial_group_id']=='g16')['witnesses'].pop())
reject('removed_anchor_cannot_survive',lambda q:q['matching']['structural_anchor_group_ids'].append('g16'))
reject('outside_frame_witness_rejected',lambda q:next(x for x in q['initial_group_reviews'] if x['initial_group_id']=='g16')['witnesses'][0].update(region_xyxy=[0,0,9999,9999]))
save(H/'contract_tests.json',dict(passed=True,checks=checks));print('PASSED',checks)
