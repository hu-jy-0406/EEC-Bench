"""Medium reasoning control with the same efficient witness transport."""
import sys,shutil,time
from pathlib import Path
H=Path(__file__).resolve().parent;B=H.parents[1];sys.path.insert(0,str(B/'scripts'))
import transport as efficient
import gs_flow1_evaluator as flow
import run_partial_scene_comparison as canonical
from run_isolated_shot_static_3d import owned_compute_job
from chain import signatures,C
owned_compute_job();out=H/'astra_medium_suffix_r4';out.mkdir(exist_ok=False)
for name in ['inputs','selected','registration']:(out/name).symlink_to(C/name,target_is_directory=True)
for name in ['narrative.json','matching_initial.json']:shutil.copy2(C/name,out/name)
shutil.copy2(C/'matching_initial.json',out/'matching.json')
flow.save(out/'provenance.json',dict(frozen_upstream=str(C),fresh_stages=['aligned_identity_review','presence','spatial'],model='gpt-6-astra',reasoning='medium',transport='lossless_witness_bank_v3'))
def routed(stage,prompt,payload,images,schema,args):
 args.model='gpt-6-astra';args.reasoning='medium';return efficient.call(stage,canonical.PROMPTS/prompt,payload,images,schema,args)
canonical.call=routed;e=flow.Eval(str(out));start=time.time();stages=[]
for label,name in [('aligned_identity_review','review_identity'),('presence','presence'),('spatial','spatial')]:
 t=time.time();print('START',label,flush=True);getattr(e,name)();stages.append(dict(stage=label,seconds=time.time()-t));flow.save(out/'timing.json',dict(seconds=time.time()-start,stages=stages));print('END',label,stages[-1]['seconds'],flush=True)
old,new=signatures(C),signatures(out);quality={k:old[k]==new[k] for k in old};flow.save(out/'quality.json',dict(comparison=quality,actual=new,baseline=old));print('QUALITY',quality,flush=True)
