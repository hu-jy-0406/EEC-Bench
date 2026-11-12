#!/usr/bin/env python3
"""Execute a prepared Flow1 stage with configured, audited transport."""
import argparse,json,time,hashlib
from pathlib import Path
import gs_flow1_evaluator as flow
import run_partial_scene_comparison as transport
import gs_flow1_compact_transport as compact
import gs_efficient_transport as efficient
from gs_runtime_profile import profile as runtime_profile, names as runtime_names, IDENTITY_REVIEW_INPUTS, resolve_identity_review_input
from run_isolated_shot_static_3d import owned_compute_job
B=Path(__file__).resolve().parents[1]
COMPACT_STAGES={'matching','identity_review','presence_1'}
def stage_runtime(case, name=None, identity_review_input=None):
 saved=Path(case)/'runtime_profile.json'
 runtime=json.loads(saved.read_text()) if name is None and saved.is_file() else runtime_profile(name)
 runtime['identity_review_input']=resolve_identity_review_input(runtime,identity_review_input)
 return runtime

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('case',type=Path);p.add_argument('stage',choices=['match','review_identity','presence','spatial']);p.add_argument('--transport',choices=['configured','canonical','compact','efficient'],default='configured');p.add_argument('--runtime-profile',choices=runtime_names());p.add_argument('--identity-review-input',choices=IDENTITY_REVIEW_INPUTS);a=p.parse_args();runtime=stage_runtime(a.case,a.runtime_profile,a.identity_review_input)
 if a.identity_review_input is not None and a.stage!='review_identity':p.error('--identity-review-input applies only to review_identity')
 identity_input=resolve_identity_review_input(runtime,a.identity_review_input)
 efficient_stages=set(runtime.get('efficient_call_stages',['matching','identity_review','presence_1','observe_shot1','observe_shot3','verify_relations'])) if runtime['transport']=='efficient' else set()
 allocation=owned_compute_job();case=a.case.resolve();config=json.loads((B/'configs/gs-consistency-two-scores.v1.json').read_text())
 profile=config.get('model_transport',{})
 enabled=set(profile.get('compact_call_stages',[])) if a.transport=='configured' else COMPACT_STAGES if a.transport=='compact' else set()
 assert enabled<=COMPACT_STAGES,'Unvalidated stage selected for compact transport'
 stages={'match':['matching'],'review_identity':['identity_review'],'presence':['presence_1'],'spatial':['observe_shot1','observe_shot3','verify_relations']}[a.stage]
 for stage in stages:
  if (case/'calls'/stage).exists():raise FileExistsError(f'Existing {stage} call: preserve it and use a fresh case directory for a changed run.')
 for name in ['inputs/shot1.json','inputs/shot3.json','selected/shot1_scene.json','selected/shot3_scene.json','narrative.json']:
  if not (case/name).is_file():raise FileNotFoundError(case/name)
 if a.stage in ['review_identity','spatial'] and not (case/'registration/roma_geometry/registration.json').is_file():raise FileNotFoundError('A saved frozen registration is required')
 original=transport.call
 def routed(stage,prompt_name,payload,images,schema,args):
  if a.transport=='efficient' or (a.transport=='configured' and stage in efficient_stages):return efficient.call(stage,transport.PROMPTS/prompt_name,payload,images,schema,args)
  if stage in enabled:
   prompt_path=(transport.PROMPTS/prompt_name).resolve()
   return compact.call(stage,str(prompt_path),payload,images,schema,args)
  return original(stage,prompt_name,payload,images,schema,args)
 transport.call=routed
 started=time.time();state=dict(stage=a.stage,allocation=allocation,transport=a.transport,compact_call_stages=sorted(enabled),efficient_call_stages=sorted(efficient_stages),started=started,model=runtime['model'],reasoning=runtime['reasoning'],runtime_profile=runtime['name'],identity_review_input=identity_input if a.stage=='review_identity' else None,status='running')
 status_path=case/f'flow1_stage_{a.stage}.json';status_path.write_text(json.dumps(state,indent=2)+'\n')
 try:
  e=flow.Eval(str(case));e.args.model=runtime['model'];e.args.reasoning=runtime['reasoning'];e.args.identity_review_protocol=runtime.get('identity_review_protocol');e.args.identity_review_input=identity_input;getattr(e,a.stage)();state['status']='success'
 except BaseException as exc:state.update(status='failed',error=repr(exc));raise
 finally:
  state.update(ended=time.time(),seconds=time.time()-started);status_path.write_text(json.dumps(state,indent=2)+'\n');transport.call=original
if __name__=='__main__':main()
