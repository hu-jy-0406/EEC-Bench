import os,sys,json,time,shutil,hashlib,subprocess
from pathlib import Path
H=Path(__file__).resolve().parent;E=H.parent;B=H.parents[1];ROOT=B.parent;OLD=E/'study2_full_fresh_20260918/study2';BASE=E/'study2_flow2_separate_ab_20260919/flow1';REPLAY=E/'study2_identity_frozen_replay_20260919'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def signature(m):return sorted((g['group_id'],g['identity'],tuple(g['a_ids']),tuple(g['b_ids'])) for g in m['groups'])
def main():
 out=H/'compact_round02';out.mkdir(exist_ok=False);start=time.time();manifest={}
 files=['inputs/shot1.json','inputs/shot3.json','selected/shot1_scene.json','selected/shot3_scene.json','narrative.json','registration/roma_geometry/registration.json']
 for rel in files:
  p=OLD/rel;manifest[str(p)]=sha(p);q=out/rel;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
 initial=H/'compact_round01/calls/matching/response.json';manifest[str(initial)]=sha(initial);shutil.copy2(initial,out/'matching.json')
 for p in [B/'scripts/run_gs_flow1_stage.py',B/'scripts/gs_flow1_evaluator.py',B/'scripts/gs_flow1_compact_transport.py',B/'scripts/gs_flow1_compact_payload.py',B/'scripts/review_aligned_entity_identities.py']:
  manifest[str(p)]=sha(p)
 # Original-frame bytes, not locally regenerated images.
 for s in ['shot1','shot3']:
  for im in read(out/'inputs'/f'{s}.json')['frames']:assert sha(Path(im['path']))==im['sha256'];manifest[im['path']]=im['sha256']
 save(out/'manifest.json',dict(sources=manifest,mode='production_entrypoint_chain',initial_matching_source=str(initial),canonical_baseline=str(OLD)))
 os.environ['MPLCONFIGDIR']=str(out/'matplotlib_cache')
 for stage in ['review_identity','presence']:
  print('START',stage,time.time(),flush=True)
  cmd=[sys.executable,str(B/'scripts/run_gs_flow1_stage.py'),str(out),stage,'--transport','compact']
  subprocess.run(cmd,cwd=ROOT,check=True)
  print('DONE',stage,time.time(),flush=True)
 # Confirm payload geometry remains the fixed baseline; only upstream judgment text differs.
 originalA=read(REPLAY/'calls/original/input.json');actualA=read(out/'calls/identity_review/input.json')
 for k in ['shots','frozen_transform','registration_quality','normal_story_prompt','all_initial_paired_group_diagnostics']:assert originalA[k]==actualA[k],k
 resultA=read(out/'identity_review.json');baselineA=read(REPLAY/'calls/original/response.json');aok=signature(resultA['matching'])==signature(baselineA['matching'])
 anchors=all(resultA['matching'][k]==baselineA['matching'][k] for k in ['structural_anchor_group_ids','local_origin_group_id','local_reference_group_id'])
 resultB=read(out/'presence.json');baselineB=read(BASE/'presence.json')
 def ps(x):return [(z['group_id'],z['partition'],z['status'],z['cause'],z['conflict_kind'],z['joint_presence_reasonable']) for z in x['groups']]
 unchanged=all(sha(Path(p))==h for p,h in manifest.items())
 save(out/'quality_gate.json',dict(identity_signature_equal=aok,anchors_equal=anchors,presence_equal=ps(resultB)==ps(baselineB),counts_equal=resultB['summary']==baselineB['summary'],source_hashes_unchanged=unchanged,geometry_frozen=True,production_entrypoint_exercised=True))
 save(out/'run.json',dict(seconds=time.time()-start,errors=[],sources_unchanged=unchanged))
 print('QUALITY',read(out/'quality_gate.json'),flush=True)
if __name__=='__main__':main()
