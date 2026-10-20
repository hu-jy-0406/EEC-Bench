import jsonschema
from contracts import MATCH
from gs_consistency_contract import obj,arr,S,WITNESS
from anchor_joint_contract import ANCHOR_AUDIT,witness_frames
REVIEW=obj(group_id=S,geometry_interpretation=S,visual_identity_evidence=S,same_instance_motion_alternative=S,witnesses=arr(WITNESS))
SCHEMA=obj(matching=MATCH,identity_reviews=arr(REVIEW),anchor_audits=arr(ANCHOR_AUDIT),registration_caveats=S,limitations=S)
def validate(result,payload):
 jsonschema.validate(result,SCHEMA);m=result['matching'];groups=m['groups'];gm={g['group_id']:g for g in groups};assert len(gm)==len(groups)
 for side,shot in zip(['a','b'],payload['shots']):
  assigned=[eid for g in groups for eid in g[side+'_ids']];expected={e['entity_id'] for e in shot['entities']}
  assert len(assigned)==len(set(assigned)) and set(assigned)==expected,'Static inventory duplicated/lost/added'
 for g in groups:
  assert g['a_ids'] or g['b_ids']
  if g['identity']=='matched':assert len(g['a_ids'])==len(g['b_ids'])==1
  if g['identity']=='unmatched':assert len(g['a_ids'])+len(g['b_ids'])==1
 audits=result['identity_reviews'];assert len(audits)==len(gm) and {r['group_id'] for r in audits}==set(gm)
 for r in audits:
  fs=witness_frames(r['witnesses'],payload['images']);g=gm[r['group_id']]
  assert r['visual_identity_evidence'].strip()
  if g['identity']=='matched':assert all(fs.values()),'Matched group needs both shots'
  if g['identity']=='unmatched':
   own=(g['a_ids']+g['b_ids'])[0].split('/')[0];assert fs[own],'Single-sided group needs own-shot pixels'
 anchors={a['anchor_id']:a for a in payload['registration_anchors']['anchors']};aa=result['anchor_audits'];assert len(aa)==len(anchors) and {a['anchor_id'] for a in aa}==set(anchors)
 retained={}
 for a in aa:
  fs=witness_frames(a['witnesses'],payload['images']);assert all(fs.values())
  old=anchors[a['anchor_id']]
  if a['verdict']=='retained':
   g=gm[a['final_group_id']];assert g['identity']=='matched' and g['a_ids']==[old['a_id']] and g['b_ids']==[old['b_id']];retained[a['anchor_id']]=g['group_id']
  else:assert not a['final_group_id'] or a['final_group_id'] in gm
 assert set(m['structural_anchor_group_ids'])<=set(retained.values())
 assert all(gm[g]['anchor_eligible'] for g in m['structural_anchor_group_ids'])
 for k in ['local_origin_group_id','local_reference_group_id']:assert not m[k] or m[k] in m['structural_anchor_group_ids']
 if m['local_origin_group_id'] and m['local_reference_group_id']:assert m['local_origin_group_id']!=m['local_reference_group_id']
 return result
