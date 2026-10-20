"""Frozen-input flow2 A then B, compared to flow1 with the same B implementation."""
import os,sys,json,copy,time,hashlib,shutil,traceback,importlib.util,socket
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
H=Path(__file__).resolve().parent;B=H.parents[1];E=B/'experiments'
OLD=E/'study2_full_fresh_20260918/study2';REPLAY=E/'study2_identity_frozen_replay_20260919';NEW=E/'study2_anchor_joint_fresh_20260918'
sys.path[:0]=[str(H),str(B/'scripts'),str(NEW)]
import run_partial_scene_comparison as transport
import identity_contract
from run_isolated_shot_static_3d import owned_compute_job
spec=importlib.util.spec_from_file_location('original_evaluator',OLD.parent/'evaluate.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def main():
 job=owned_compute_job();start=time.time();manifest={}
 assert not (H/'flow1').exists() and not (H/'flow2').exists(),'Do not reuse or rerun calls silently'
 def source(p):manifest[str(p)]=sha(p);return read(p)
 a1=source(REPLAY/'calls/original/response.json');p1=source(REPLAY/'calls/original/input.json');p2=source(REPLAY/'calls/joint/input.json');images2=source(REPLAY/'prepared/joint_images.json')
 p2=copy.deepcopy(p2);p2['stage']='post_alignment_identity_only_v1';p2.pop('auxiliary_full_motion_inventories')
 assert p1['shots']==p2['shots'] and p1['frozen_transform']==p2['frozen_transform'] and p1['normal_story_prompt']==p2['normal_story_prompt'] and p1['registration_quality']==p2['registration_quality']
 for im in images2:assert sha(Path(im['path']))==im['sha256'];manifest[im['path']]=im['sha256']
 for f in ['run.py','identity_contract.py','prompts/identity.txt']:
  p=H/f;manifest[str(p)]=sha(p)
 for p in [OLD.parent/'evaluate.py',OLD.parent/'contracts.py',B/'scripts/run_partial_scene_comparison.py',B/'scripts/run_wedetect_shot_entities.py']:
  manifest[str(p)]=sha(p)
 prompt=OLD.parent/'prompts/presence.txt';manifest[str(prompt)]=sha(prompt);shutil.copy2(prompt,H/'prompts/presence.txt');transport.PROMPTS=H/'prompts'
 req=source(REPLAY/'calls/original/request.json');disabled=next(x for x in req['command'] if x.startswith('skills.config='))
 for name in ['flow1','flow2']:
  d=H/name;d.mkdir()
  for rel in ['inputs/shot1.json','inputs/shot3.json','selected/shot1_scene.json','selected/shot3_scene.json','narrative.json']:
   src=OLD/rel;source(src);dst=d/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
 save(H/'flow1/identity_review.json',a1);save(H/'flow1/matching.json',a1['matching']);save(H/'flow1/identity_review_payload.json',p1)
 save(H/'flow2/identity_review_payload.json',p2)
 save(H/'flow2/identity_images.json',images2)
 manifest.update({str(REPLAY/'calls/original/status.json'):sha(REPLAY/'calls/original/status.json')})
 save(H/'frozen_manifest.json',dict(sources=manifest,baseline=str(OLD),flow1_identity_source=str(REPLAY/'calls/original'),shared_shots=True,shared_transform=True,shared_prompt_story=True,shared_presence_code=str(OLD.parent/'evaluate.py'),shared_presence_prompt_sha256=sha(prompt),new_calls_planned=5,model='gpt-6-astra',reasoning='medium',allocation=job,host=socket.gethostname(),scope='Frozen post-registration comparison; no detector/anchor inference/registration/spatial rerun. Flow1 A reused latest controlled replay; both flow B stages fresh identical dual-judgment implementation.'))
 def presence(name):
  begin=time.time();print('START B',name,begin,flush=True)
  ev=base.Eval(str(H/name));ev.args.disabled_skills=disabled
  ev.presence()
  save(H/name/'B_timing.json',dict(started=begin,ended=time.time(),seconds=time.time()-begin))
  print('DONE B',name,time.time(),flush=True)
 def flow2():
  args=SimpleNamespace(out=H/'flow2/calls',model='gpt-6-astra',reasoning='medium',codex_bin='/vast/users/guangyi.chen/.local/bin/codex',timeout=1800,disabled_skills=disabled)
  print('START A flow2',time.time(),flush=True)
  result=transport.call('identity','identity.txt',p2,images2,identity_contract.SCHEMA,args)
  identity_contract.validate(result,p2)
  save(H/'flow2/identity_validation.json',dict(passed=True))
  save(H/'flow2/identity_review.json',result);save(H/'flow2/matching.json',result['matching'])
  # Do not silently carry an invalid reference frame into stage B.
  assert all(a['verdict']=='retained' for a in result['anchor_audits']),'Anchor rejected: frozen geometry requires separate review before B'
  print('DONE A flow2',time.time(),flush=True);presence('flow2')
 errors=[]
 with ThreadPoolExecutor(max_workers=2) as pool:
  futures=[pool.submit(presence,'flow1'),pool.submit(flow2)]
  for f in futures:
   try:f.result()
   except Exception as exc:errors.append(repr(exc));traceback.print_exc()
 unchanged=all(sha(Path(p))==h for p,h in manifest.items())
 save(H/'run.json',dict(started=start,ended=time.time(),seconds=time.time()-start,errors=errors,sources_unchanged=unchanged,allocation=job))
 assert unchanged
 if errors:raise RuntimeError(str(errors))
 # The B input evidence must be identical except each method's identity output.
 q1=read(H/'flow1/calls/presence_1/input.json');q2=read(H/'flow2/calls/presence_1/input.json')
 for k in ['graphs','auxiliary_full_motion_inventories','normal_story_prompt','images']:assert q1[k]==q2[k],k
 for k in ['frozen_transform','registration_quality','shots']:assert q1['post_alignment_evidence'][k]==q2['post_alignment_evidence'][k],k
 for name in ['flow1','flow2']:assert read(H/name/'calls/presence_1/input.json')==read(H/name/'calls/presence_2/input.json')
 save(H/'audit.json',dict(passed=True,frozen_inputs_equal=True,B_code_and_prompt_equal=True,independent_B_calls_equal_input=True,source_hashes_unchanged=True,new_calls=5))
 print('ALL COMPLETE',flush=True)
if __name__=='__main__':main()
