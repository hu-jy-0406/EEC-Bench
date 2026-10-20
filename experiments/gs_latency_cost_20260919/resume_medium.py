"""Recover a completed response after a serialization-only check, without another call."""
import copy,sys,time,shutil
from pathlib import Path
H=Path(__file__).resolve().parent;B=H.parents[1];sys.path.insert(0,str(B/'scripts'))
import transport as efficient
import gs_flow1_evaluator as flow
import run_partial_scene_comparison as canonical
import run_wedetect_shot_entities as io
from partial_scene_contract import schema_validate
from review_aligned_entity_identities import validate
from run_isolated_shot_static_3d import owned_compute_job
from chain import signatures,C
owned_compute_job();out=H/'astra_medium_suffix_r4';d=out/'calls/identity_review';old=flow.read(d/'status.json');assert old['error']=="AssertionError('Unused witness records')"
shutil.copy2(d/'status.json',d/'status_before_decoder_recovery.json')
raw=flow.read(d/'wire_response.json');schema_validate(raw,flow.read(d/'wire.schema.json'));response=efficient.decode(raw,flow.read(d/'wire_canonical.schema.json'));bank=response.pop('witness_bank');images=flow.read(out/'identity_review_images.json');used=set()
for r in response['initial_group_reviews']+response['noncommon_checks']:
 refs=r['witnesses'];ws=[]
 for k in refs:
  assert type(k)==int and 0<=k<len(bank);used.add(k);w=bank[k];f=images[w['i']-1];assert f['frame_id']>=0;ws.append(dict(shot_id=f['shot_id'],frame_id=f['frame_id'],region_xyxy=w['b'],observation=w['o']))
 r['witnesses']=ws
payload=flow.read(d/'input.json');m=response['matching'];initial={g['group_id']:g for g in payload['initial_matching']['groups']};keep=m.pop('unchanged_group_ids');revised=m.pop('revised_groups');order=m.pop('group_order');assert not set(keep)&{g['group_id'] for g in revised};groups={k:copy.deepcopy(initial[k]) for k in keep};groups.update({g['group_id']:g for g in revised});assert len(order)==len(set(order)) and set(order)==set(groups);m['groups']=[groups[k] for k in order]
schema_validate(response,flow.read(d/'output.schema.json'));validate(response,payload);usage=io.audit_events(d/'events.jsonl');flow.save(d/'response.json',response);flow.save(d/'status.json',dict(old,status='success',usage=usage,decoder_recovery='Unused bank entries retained in wire record; every referenced witness and all canonical gates validated.',unused_witness_indices=sorted(set(range(len(bank)))-used)))
def routed(stage,prompt,payload,images,schema,args):
 args.model='gpt-6-astra';args.reasoning='medium';return efficient.call(stage,canonical.PROMPTS/prompt,payload,images,schema,args)
canonical.call=routed;e=flow.Eval(str(out));e.review_identity();stages=[dict(stage='aligned_identity_review',seconds=old['seconds'],timing_scope='Actual completed API call; decoder recovery offline')]
for label,name in [('presence','presence'),('spatial','spatial')]:
 t=time.time();print('START',label,flush=True);getattr(e,name)();stages.append(dict(stage=label,seconds=time.time()-t));flow.save(out/'timing.json',dict(stages=stages,active_stage_seconds=sum(s['seconds'] for s in stages),decoder_recovery_without_api_retry=True));print('END',label,stages[-1]['seconds'],flush=True)
old,new=signatures(C),signatures(out);quality={k:old[k]==new[k] for k in old};flow.save(out/'quality.json',dict(comparison=quality,actual=new,baseline=old));print('QUALITY',quality,flush=True)
