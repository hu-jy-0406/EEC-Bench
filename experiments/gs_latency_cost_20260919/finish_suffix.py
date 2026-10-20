"""Resume after a broken stdout connection, using completed calls verbatim."""
import sys,time
from pathlib import Path
H=Path(__file__).resolve().parent;B=H.parents[1];sys.path.insert(0,str(B/'scripts'))
import transport as efficient
import gs_flow1_evaluator as flow
import run_partial_scene_comparison as canonical
from run_isolated_shot_static_3d import owned_compute_job
from chain import signatures,C
owned_compute_job();out=H/'astra_low_suffix_r3'
assert flow.read(out/'calls/presence_1/status.json')['status']=='success'
def routed(stage,prompt,payload,images,schema,args):
 args.model='gpt-6-astra';args.reasoning='low';return efficient.call(stage,canonical.PROMPTS/prompt,payload,images,schema,args)
canonical.call=routed;e=flow.Eval(str(out));t=time.time();e.spatial();timing=flow.read(out/'timing.json');timing['stages'] += [dict(stage='presence',seconds=flow.read(out/'calls/presence_1/status.json')['seconds'],timing_scope='completed API call; orchestration stdout interrupted after score saved'),dict(stage='spatial',seconds=time.time()-t)];timing['active_stage_seconds']=sum(s['seconds'] for s in timing['stages']);timing['interruption']='SSH stdout closed after B saved; no model call repeated';flow.save(out/'timing.json',timing)
old,new=signatures(C),signatures(out);quality={k:old[k]==new[k] for k in old};flow.save(out/'quality.json',dict(comparison=quality,actual=new,baseline=old));print('QUALITY',quality,flush=True)
