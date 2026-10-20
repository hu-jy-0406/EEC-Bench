"""Audit complete replay outputs and preserve all changes, including uncertainty."""
import json,sys,math,csv
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from run_gs_integrated import read,save,sha
from gs_entity_appearance_compact import cost
from gs_entity_displacement import within,boundary,aggregate
from gs_temporal_core import boundary_proposals
from gs_prompt_alignment import validate_contract
from gs_identity_review_minimal_input import build
from review_aligned_entity_identities import validate,FOCUSED_PROTOCOL
BASES=read(B/'experiments/gravity_free_pipeline_20260921/baselines.json')

def identity_sig(m):
 groups={g['group_id']:g for g in m['groups']}
 sig=lambda g:(tuple(g['a_ids']),tuple(g['b_ids']),g['identity'])
 return dict(population=sorted(sig(g) for g in m['groups']),confirmed=sorted(sig(g) for g in m['groups'] if g['identity']=='matched'),eligible=sorted(sig(g) for g in m['groups'] if g['anchor_eligible']),anchors=sorted(sig(groups[g]) for g in m['structural_anchor_group_ids']),references=[sig(groups[m[k]]) if m[k] else None for k in ['local_origin_group_id','local_reference_group_id']])

def units(result,matching,kind):
 gm={g['group_id']:tuple(sorted(g['a_ids']+g['b_ids'])) for g in matching['groups']}
 return {json.dumps(sorted(gm[g] for g in u['endpoint_groups'])) if kind=='spatial' else json.dumps(sorted(u['entity_ids'])):dict(status=u['status'],cosine=u.get('cosine')) for u in result[kind]['units']}

def changes(a,b):
 return [dict(key=k,before=a.get(k),after=b.get(k)) for k in sorted(set(a)|set(b)) if a.get(k)!=b.get(k)]

rows=[];usage=[];audits=[]
for study,base in BASES.items():
 old=Path(base);case=R/'runs'/study;p=case/'pairs/pair_000';op=old/'pairs/pair_000'
 state=read(case/'pipeline_runtime.json')
 if study=='study4':
  assert read(R/'study4_prompt_recovery_v2/runtime.json')['status']=='success'
  assert all(x['status']=='success' for x in read(R/'study4_recovery.json')['stages'])
 else:assert state['status']=='success'
 for source,h in read(case/'frozen_upstream.json')['hashes'].items():assert sha(source)==h
 canonical=read(p/'identity_review_payload.json');expected,images=build(canonical,read(p/'identity_review_images.json'))
 assert read(p/'calls/identity_review/input.json')==expected
 validate(read(p/'identity_review.json'),canonical,FOCUSED_PROTOCOL)
 for im in images:assert sha(im['path'])==im['sha256']
 reg=read(p/'registration/roma_geometry/registration.json');assert reg==read(op/'registration/roma_geometry/registration.json')
 om=read(op/'matching.json');nm=read(p/'matching.json');osig=identity_sig(om);nsig=identity_sig(nm)
 obr=read(op/'boundary/results.json');nbr=read(p/'boundary/results.json')
 graphs=[read(case/'selected'/f'{sid}_scene.json') for sid in ['shot1','shot3']];fit=reg['fits']['all_structures'];scope=read(p/'pair_scope.json')
 for sid in ['shot1','shot2','shot3']:
  assert read(case/'selected'/f'{sid}_scene.json')==read(old/'selected'/f'{sid}_scene.json')
  assert read(case/'within'/sid/'results.json')==read(old/'within'/sid/'results.json')
 displacement=read(case/'displacement/results.json')
 for sid in ['shot1','shot2','shot3']:assert within(read(case/'selected'/f'{sid}_scene.json'))==displacement['within_shots'][sid]
 before=boundary('pair_000',graphs,om,fit,scope,obr);after=boundary('pair_000',graphs,nm,fit,scope,nbr)
 assert after==displacement['boundaries']['pair_000']
 dist=lambda b:{json.dumps(sorted(r['entity_ids'])):{k:r[k] for k in ['distance','r_e','entity_score','status','reason']} for r in b['records']}
 save(case/'displacement/old_identity_recomputed.json',before)
 reference=R/'references/study4_corrected' if study=='study4' else case/'prompt_alignment_reference'
 alignment=R/'study4_prompt_recovery_v2/alignment' if study=='study4' else case/'prompt_alignment'
 contract=validate_contract(read(reference/'contract.json'));align=read(alignment/'results.json');assert align['status']=='success'
 assert [q['claim_id'] for q in contract['claims']]==[q['claim_id'] for q in align['checks']] or set(q['claim_id'] for q in contract['claims'])==set(q['claim_id'] for q in align['checks'])
 assert len(align['checks'])==len(contract['claims'])
 appearance=read(case/'appearance/report/results.json')['studies'][0]
 registry=read(case/'global_entities/global_entities.json');assert len(appearance['entities'])==len(registry['entities'])
 detail=dict(study=study,identity={k:dict(equal=osig[k]==nsig[k],before=osig[k],after=nsig[k]) for k in osig},presence_changes=changes(units(obr,om,'presence'),units(nbr,nm,'presence')),spatial_changes=changes(units(obr,om,'spatial'),units(nbr,nm,'spatial')),displacement_changes=changes(dist(before),dist(after)),frozen_sources_pass=True,canonical_validation_pass=True,full_original_frame_count=len(images),appearance_entities=len(appearance['entities']),alignment_claims=len(align['checks']))
 if (old/'prompt_alignment/results.json').exists():
  oa=read(old/'prompt_alignment/results.json');assert oa['contract_sha256']==align['contract_sha256']
  detail['alignment_changes']=changes({q['claim_id']:q['status'] for q in oa['checks']},{q['claim_id']:q['status'] for q in align['checks']})
 if (old/'prompt_binding/results.json').exists():
  ob=read(old/'prompt_binding/results.json');nb=read(case/'prompt_binding/results.json')
  detail['binding_top_level_keys']=list(nb)
 if (old/'appearance/report/results.json').exists():
  oa=read(old/'appearance/report/results.json')['studies'][0]
  detail['appearance_changes']=changes({e['global_entity_id']:e['attribute_scores'] for e in oa['entities']},{e['global_entity_id']:e['attribute_scores'] for e in appearance['entities']})
  app_audit=[]
  for e in appearance['entities']:
   eid=e['global_entity_id'];before_input=read(old/'appearance/canonical/entities'/eid/'input.json');after_input=read(case/'appearance/canonical/entities'/eid/'input.json')
   sig=lambda d:[(a['shot_id'],a['local_entity_id'],a['frame_id'],a['crop_sha256']) for a in d['appearances']]
   app_audit.append(dict(entity=eid,pixels_and_occurrences_equal=sig(before_input)==sig(after_input),dino_delta=e['dino_score']-next(x['dino_score'] for x in oa['entities'] if x['global_entity_id']==eid) if e['dino_score'] is not None else None))
  detail['appearance_input_audit']=app_audit
 save(case/'comparison.json',detail);audits.append(detail)
 summary=read(case/'summary.json')
 rows.append(dict(study=study,seconds=state['seconds'],including_reference_seconds=(read(R/'study4_prompt_recovery_v2/runtime.json')['started']+read(R/'study4_prompt_recovery_v2/runtime.json')['seconds']-read(R/'study4_status.json')['started']) if study=='study4' else read(R/f'{study}_status.json')['seconds'],calls=len(summary['calls']),tokens=summary['total_tokens'],usd=summary['standard_api_equivalent_usd'],presence_before=obr['presence']['summary'],presence_after=nbr['presence']['summary'],spatial_before=obr['spatial']['summary'],spatial_after=nbr['spatial']['summary'],displacement=displacement['episode'],appearance=appearance['all_entities'],alignment=align['dimensions']))
 for call in summary['calls']:usage.append(dict(study=study,**call))
compiler=[]
for study in ['study2','study4']:
 p=R/'reference_compilation'/study/'calls/compiler/status.json';d=read(p);u=d.get('usage',d.get('known_usage',[]));u=[u] if isinstance(u,dict) else u
 compiler.append(dict(study=study,call=str(p.parent),status=d['status'],seconds=d.get('seconds'),total_tokens=sum(x.get('input_tokens',0)+x.get('output_tokens',0) for x in u),standard_api_equivalent_usd=cost(u),usage=u))
recovery_calls=[]
for folder in [R/'study4_prompt_corrected/binding',R/'study4_prompt_recovery_v2/binding',R/'study4_prompt_recovery_v2/alignment']:
 for p in folder.glob('calls/*/status.json'):
  d=read(p);u=d.get('usage',d.get('known_usage',[]));u=[u] if isinstance(u,dict) else u
  recovery_calls.append(dict(study='study4',call=str(p.parent),status=d['status'],seconds=d.get('seconds'),total_tokens=sum(x.get('input_tokens',0)+x.get('output_tokens',0) for x in u),standard_api_equivalent_usd=cost(u),usage=u))
allcalls=usage+compiler+recovery_calls
save(R/'comparison.json',dict(studies=rows,audits=audits))
save(R/'usage.json',dict(calls=allcalls,model_calls=len(allcalls),tokens=sum(c['total_tokens'] for c in allcalls),standard_api_equivalent_usd=sum(c['standard_api_equivalent_usd'] for c in allcalls),pricing='Recorded Astra standard API equivalent USD/M uncached input10, cache-read1, output50; cache subset; not billed',reference_compilation=compiler,recovery_calls=recovery_calls,validation_failures=[str(R/'runs/study4/prompt_binding'),str(R/'study4_prompt_corrected/binding')]))
print(json.dumps(rows,ensure_ascii=False,indent=2))
