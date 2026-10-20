"""Contracts for anchor-only registration followed by one joint identity/presence judgment."""
import copy,re
from contracts import MATCH,PRESENCE_ROW,GATES
from gs_consistency_contract import obj,arr,enum,S,B,WITNESS
ANCHOR=obj(anchor_id=S,a_id=S,b_id=S,identity_supported=B,reason=S,witnesses=arr(WITNESS))
ANCHORS=obj(anchors=arr(ANCHOR),local_origin_anchor_id=S,local_reference_anchor_id=S,selection_reason=S,limitations=S)
ANCHOR_AUDIT=obj(anchor_id=S,verdict=enum('retained','rejected','uncertain'),final_group_id=S,reason=S,witnesses=arr(WITNESS))
JOINT=obj(matching=MATCH,checks=arr(PRESENCE_ROW),anchor_audits=arr(ANCHOR_AUDIT),registration_caveats=S,limitations=S)

def witness_frames(ws,images):
 idx={(f['shot_id'],f['frame_id']):f for f in images};frames={s:set() for s in ['shot1','shot3']}
 for w in ws:
  key=(w['shot_id'],w['frame_id']);assert key in idx,'Unknown witness frame'
  W,H=idx[key]['image_size'];b=w['region_xyxy'];assert len(b)==4 and 0<=b[0]<b[2]<=W and 0<=b[1]<b[3]<=H,'Witness outside source image'
  assert w['observation'].strip(),'Empty visual witness';frames[w['shot_id']].add(w['frame_id'])
 return frames

def validate_anchors(result,payload):
 import jsonschema
 jsonschema.validate(result,ANCHORS)
 a=result['anchors'];assert len(a)>=2,'At least two identifiable structural anchors required'
 ids=[x['anchor_id'] for x in a];assert len(ids)==len(set(ids)) and all(re.fullmatch(r'a[0-9]+',i) for i in ids)
 # Integer mask labels must also be unique (a01 and a1 would collide).
 assert len({int(i[1:]) for i in ids})==len(ids)
 for side,shot in zip(['a','b'],payload['shots']):
  valid={e['entity_id'] for e in shot['entities']};chosen=[x[side+'_id'] for x in a];assert len(chosen)==len(set(chosen)) and set(chosen)<=valid
 for x in a:
  fs=witness_frames(x['witnesses'],payload['images']);assert x['identity_supported'] and x['reason'].strip() and all(fs.values()),'Anchor needs image-supported identity in both shots'
 refs=[result['local_origin_anchor_id'],result['local_reference_anchor_id']]
 assert len(set(refs))==2 and all(r in ids for r in refs),'Invalid local reference pair'
 return result

def normalize_presence(matching,checks,images,facts):
 """Keep existing evidence/Prompt gates, replacing only the two-review consensus."""
 assert [r['group_id'] for r in checks]==[g['group_id'] for g in matching['groups']],'Missing/reordered presence rows'
 out=[]
 for g,r in zip(matching['groups'],checks):
  partition='common_static' if g['identity']=='matched' else 'noncommon_static' if g['identity']=='unmatched' else 'unresolved'
  assert r['partition']==partition
  assert set(r['prompt_fact_references'])<=facts,'Unknown Prompt fact'
  fs=witness_frames(r['witnesses'],images);prompt=r['prompt_review_completed'] and bool(r['prompt_fact_references']) and bool(r['prompt_explanation'].strip());ok=True
  if r['status']=='conflict':
   ok=all(len(f)>=2 for f in fs.values()) and prompt and all(r[k] for k in GATES) and r['cause']=='inconsistency' and r['conflict_kind'] in (['required_absent_but_present'] if partition=='common_static' else ['unexplained_missing','unexplained_added'])
  elif r['status']=='compatible':ok=partition=='common_static' and r['joint_presence_reasonable'] and r['identity_supported'] and all(len(f)>=1 for f in fs.values()) and prompt
  elif r['status']=='exempt':ok=partition=='noncommon_static' and r['cause'] in ['viewpoint','motion'] and bool(r['witnesses']) and prompt
  status=r['status'] if ok and partition!='unresolved' else 'unknown'
  out.append(dict(group_id=g['group_id'],partition=partition,status=status,cause=r['cause'],conflict_kind=r['conflict_kind'] if status=='conflict' else 'none',joint_presence_reasonable=partition=='common_static' and status=='compatible',evidence_gates_pass=[bool(ok)],reason=[r['reason']],reviews=[copy.deepcopy(r)],judgment_count=1))
 return out

def validate_joint(result,payload):
 import jsonschema
 jsonschema.validate(result,JOINT);m=result['matching'];groups=m['groups'];gm={g['group_id']:g for g in groups};assert len(gm)==len(groups)
 for side,shot in zip(['a','b'],payload['shots']):
  assigned=[e for g in groups for e in g[side+'_ids']];expected={e['entity_id'] for e in shot['entities']}
  assert len(assigned)==len(set(assigned)) and set(assigned)==expected,'Static inventory duplicated/lost/added'
 for g in groups:
  assert g['a_ids'] or g['b_ids']
  if g['identity']=='matched':assert len(g['a_ids'])==len(g['b_ids'])==1
  if g['identity']=='unmatched':assert len(g['a_ids'])+len(g['b_ids'])==1
 anchors={x['anchor_id']:x for x in payload['registration_anchors']['anchors']};audits=result['anchor_audits']
 assert len(audits)==len(anchors) and {a['anchor_id'] for a in audits}==set(anchors)
 retained={}
 for a in audits:
  fs=witness_frames(a['witnesses'],payload['images']);assert all(fs.values()),'Anchor audit needs both original shots'
  old=anchors[a['anchor_id']]
  if a['verdict']=='retained':
   assert a['final_group_id'] in gm
   g=gm[a['final_group_id']];assert g['identity']=='matched' and g['a_ids']==[old['a_id']] and g['b_ids']==[old['b_id']]
   retained[a['anchor_id']]=g['group_id']
  else:assert not a['final_group_id'] or a['final_group_id'] in gm
 assert set(m['structural_anchor_group_ids'])<=set(retained.values())
 assert all(gm[g]['anchor_eligible'] for g in m['structural_anchor_group_ids'])
 for key in ['local_origin_group_id','local_reference_group_id']:assert not m[key] or m[key] in m['structural_anchor_group_ids']
 if m['local_origin_group_id'] and m['local_reference_group_id']:assert m['local_origin_group_id']!=m['local_reference_group_id']
 rows=normalize_presence(m,result['checks'],payload['images'],{f['fact_id'] for f in payload['normal_story_prompt']['facts']})
 return rows

def refit_requirement(anchors,anchor_audits,point_groups):
 removed=[r['anchor_id'] for r in anchor_audits if r['verdict']!='retained']
 counts={a:int(point_groups.get(str(int(a[1:])),0)) for a in removed}
 return dict(rejected_or_uncertain=removed,point_counts=counts,refit_required=any(n>0 for n in counts.values()))
