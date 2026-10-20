"""Production candidate: unchanged upstream judgments, only efficient spatial transport."""
import sys,shutil,time
from pathlib import Path
H=Path(__file__).resolve().parent;B=H.parents[1];sys.path.insert(0,str(B/'scripts'))
import gs_efficient_transport as efficient
import gs_flow1_evaluator as flow
import run_partial_scene_comparison as canonical
from run_isolated_shot_static_3d import owned_compute_job
from chain import signatures,C
owned_compute_job();out=H/'safe_spatial_medium';out.mkdir(exist_ok=False)
for name in ['inputs','selected','registration']:(out/name).symlink_to(C/name,target_is_directory=True)
for name in ['narrative.json','matching.json','presence.json']:shutil.copy2(C/name,out/name)
flow.save(out/'provenance.json',dict(frozen_upstream=str(C),fresh_stages=['spatial'],model='gpt-6-astra',reasoning='medium',transport='lossless_witness_bank_v3',score_and_evidence_gates='unchanged'))
def routed(stage,prompt,payload,images,schema,args):
 args.model='gpt-6-astra';args.reasoning='medium';return efficient.call(stage,canonical.PROMPTS/prompt,payload,images,schema,args)
canonical.call=routed;e=flow.Eval(str(out));t=time.time();e.spatial();flow.save(out/'timing.json',dict(stages=[dict(stage='spatial',seconds=time.time()-t)]))
old,new=signatures(C),signatures(out);quality={k:old[k]==new[k] for k in old};flow.save(out/'quality.json',dict(comparison=quality,actual=new,baseline=old));print('QUALITY',quality,flush=True)
