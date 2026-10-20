"""Frozen-model comparisons; optional chained compact A-review -> dual B."""
import os,sys,json,copy,time,hashlib,shutil,traceback,importlib.util,argparse
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
H=Path(__file__).resolve().parent;E=H.parent;B=H.parents[1];OLD=E/'study2_full_fresh_20260918/study2';REPLAY=E/'study2_identity_frozen_replay_20260919';AB=E/'study2_flow2_separate_ab_20260919/flow1'
sys.path[:0]=[str(H),str(B/'scripts'),str(OLD.parent),str(E/'study2_anchor_joint_fresh_20260918')]
import run_partial_scene_comparison as transport
import compact_transport as compact
import review_aligned_entity_identities as identity
from compact_payload import pack,unpack,equivalent
from run_isolated_shot_static_3d import owned_compute_job
spec=importlib.util.spec_from_file_location('original_evaluator',OLD.parent/'evaluate.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def signature(m):return sorted((g['group_id'],g['identity'],tuple(g['a_ids']),tuple(g['b_ids'])) for g in m['groups'])
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--name',required=True);parser.add_argument('--mode',choices=['isolated','chain'],required=True);parser.add_argument('--test-initial',action='store_true');parser.add_argument('--initial-result');a=parser.parse_args();job=owned_compute_job();start=time.time();out=H/a.name;out.mkdir(exist_ok=False)
 manifest={}
 def src(p):manifest[str(p)]=sha(p);return read(p)
 for rel in ['inputs/shot1.json','inputs/shot3.json','selected/shot1_scene.json','selected/shot3_scene.json','narrative.json']:
  p=OLD/rel;src(p);q=out/rel;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
 pA=src(REPLAY/'calls/original/input.json');images=src(OLD/'identity_review_images.json');baselineA=src(REPLAY/'calls/original/response.json')
 if a.initial_result:
  candidate=src(Path(a.initial_result));original=pA['initial_matching'];assert signature(candidate)==signature(original)
  for k in ['structural_anchor_group_ids','local_origin_group_id','local_reference_group_id']:assert candidate[k]==original[k]
  pA['initial_matching']=candidate
 save(out/'identity_review_payload.json',pA);save(out/'identity_review.json',baselineA);save(out/'matching.json',baselineA['matching'])
 for im in images:assert sha(Path(im['path']))==im['sha256'];manifest[im['path']]=im['sha256']
 prompts=H/'prompts';prompts.mkdir(exist_ok=True)
 for name,path in [('identity.txt',REPLAY/'calls/original/prompt.txt'),('presence.txt',AB/'calls/presence_1/prompt.txt'),('matching.txt',OLD/'calls/matching/prompt.txt')]:
  manifest[str(path)]=sha(path);intro=path.read_text().split('\nINPUT_JSON:\n',1)[0]
  target=prompts/name
  if target.exists():assert target.read_text()==intro
  else:target.write_text(intro)
 compact.PROMPTS=prompts;transport.call=compact.call
 request=src(REPLAY/'calls/original/request.json');disabled=next(s for s in request['command'] if s.startswith('skills.config='))
 args=SimpleNamespace(out=out/'calls',model='gpt-6-astra',reasoning='medium',codex_bin='/vast/users/guangyi.chen/.local/bin/codex',timeout=1800,disabled_skills=disabled)
 for p in [H/'compact_payload.py',H/'compact_transport.py',H/'run_trial.py',OLD.parent/'evaluate.py',B/'scripts/review_aligned_entity_identities.py']:manifest[str(p)]=sha(p)
 errors=[]
 def doA():
  print('START A',a.name,time.time(),flush=True)
  r=compact.call('identity_review','identity.txt',pA,images,identity.SCHEMA,args);identity.validate(r,pA)
  save(out/'candidate_identity_review.json',r);save(out/'A_audit.json',dict(passed=True,identity_signature_equal=signature(r['matching'])==signature(baselineA['matching'])))
  print('DONE A',a.name,time.time(),flush=True);return r
 def doB():
  print('START B',a.name,time.time(),flush=True);begin=time.time();ev=base.Eval(str(out));ev.args.disabled_skills=disabled;ev.presence();save(out/'B_timing.json',dict(seconds=time.time()-begin));print('DONE B',a.name,time.time(),flush=True)
 def doInitial():
  p=src(OLD/'calls/matching/input.json');schema=src(OLD/'calls/matching/output.schema.json');r=compact.call('matching','matching.txt',p,images[:12],schema,args)
  initial=pA['initial_matching'];ok=signature(r)==signature(initial) and all(r[k]==initial[k] for k in ['structural_anchor_group_ids','local_origin_group_id','local_reference_group_id'])
  save(out/'initial_audit.json',dict(exact_group_and_anchor_signature_equal=ok));print('INITIAL SAME',ok,flush=True)
 if a.mode=='isolated':
  with ThreadPoolExecutor(max_workers=3) as pool:
   futures=[pool.submit(doA),pool.submit(doB)]
   if a.test_initial:futures.append(pool.submit(doInitial))
   for f in futures:
    try:f.result()
    except Exception as exc:errors.append(repr(exc));traceback.print_exc()
 else:
  try:
   r=doA();save(out/'identity_review.json',r);save(out/'matching.json',r['matching']);doB()
  except Exception as exc:errors.append(repr(exc));traceback.print_exc()
 # All canonical evidence is saved alongside compact wire data; replay the codec audit.
 codecs=[]
 for d in sorted((out/'calls').iterdir()):
  if (d/'wire_input.json').exists():
   raw=read(d/'input.json');wire=read(d/'wire_input.json');equivalent(raw,unpack(wire));codecs.append(dict(stage=d.name,**wire['derived_geometry']))
 unchanged=all(sha(Path(p))==h for p,h in manifest.items())
 save(out/'manifest.json',dict(sources=manifest,allocation=job,mode=a.mode,model=args.model,reasoning=args.reasoning,codecs=codecs))
 save(out/'run.json',dict(started=start,seconds=time.time()-start,errors=errors,sources_unchanged=unchanged))
 assert unchanged
 if errors:raise RuntimeError(str(errors))
 baselineP=src(AB/'presence.json');r=read(out/'presence.json')
 def ps(x):return [(z['group_id'],z['partition'],z['status'],z['cause'],z['conflict_kind'],z['joint_presence_reasonable']) for z in x['groups']]
 save(out/'quality_gate.json',dict(identity_signature_equal=read(out/'A_audit.json')['identity_signature_equal'],presence_equal=ps(r)==ps(baselineP),counts_equal=r['summary']==baselineP['summary'],identity_contract_passed=True,presence_contract_passed=True,geometry_equivalence_passed=True,original_images_unchanged=True))
 print('QUALITY',read(out/'quality_gate.json'),flush=True)
if __name__=='__main__':main()
