"""Frozen per-stage comparisons; previous verdicts never enter model inputs."""
import argparse,copy,json,sys,time
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
H=Path(__file__).resolve().parent;B=H.parents[1];sys.path.insert(0,str(B/'scripts'))
import transport as efficient
import run_wedetect_shot_entities as io
from run_isolated_shot_static_3d import owned_compute_job,SCHEMA as MOTION,validate_review
from review_aligned_entity_identities import SCHEMA as IDENTITY,validate as validate_identity
from gs_flow1_contract import MATCH,PRESENCE,VERIFY
from gs_relation_contract import SHOT_SCHEMA
from run_gs_spatial_consistency import validate_single
C=B/'experiments/study2_integrated_full_fresh_20260919/study2'
def read(p):return json.loads(p.read_text())
def run(stage,out,model,reasoning):
 source=C/'calls'/stage;payload=read(source/'input.json');schema=read(source/'output.schema.json')
 if stage=='identity_review':images=read(C/'identity_review_images.json');prompt=B/'prompts/gs_aligned_identity_review_v1.txt'
 else:
  shots=['shot1','shot3'] if stage in ['matching','presence_1','verify_relations'] else [stage.split('_',1)[1]]
  images=[dict(f,shot_id=s) for s in shots for f in read(C/'inputs'/f'{s}.json')['frames']]
  prompt=B/'prompts/gs_flow1'/('shot_motion_isolated_v0.2.txt' if stage.startswith('motion_') else 'gs_relation_shot_v1.txt' if stage.startswith('observe_') else {'matching':'match.txt','presence_1':'presence.txt','verify_relations':'verify_cosine.txt'}[stage])
 args=SimpleNamespace(out=out,model=model,reasoning=reasoning,codex_bin='/vast/users/guangyi.chen/.local/bin/codex',timeout=1800,disabled_skills=io.disabled_skills_config())
 result=efficient.call(stage,prompt,payload,images,schema,args);old=read(source/'response.json')
 if stage=='identity_review':
  validate_identity(result,payload)
  sig=lambda r:sorted((tuple(g['a_ids']),tuple(g['b_ids']),g['identity'],g['anchor_eligible']) for g in r['matching']['groups'])
  quality=dict(identity_equal=sig(result)==sig(old),anchors_equal=all(result['matching'][k]==old['matching'][k] for k in ['structural_anchor_group_ids','local_origin_group_id','local_reference_group_id']))
 elif stage.startswith('motion_'):
  validate_review(result,payload);quality=dict(labels_equal=[(e['entity_id'],e['status']) for e in result['entities']]==[(e['entity_id'],e['status']) for e in old['entities']])
 elif stage=='presence_1':
  keys=['group_id','partition','status','cause','conflict_kind','joint_presence_reasonable'];sig=lambda r:[{k:x[k] for k in keys} for x in r['checks']];quality=dict(classifications_equal=sig(result)==sig(old),differences=[dict(old=a,new=b) for a,b in zip(sig(old),sig(result)) if a!=b])
 elif stage.startswith('observe_'):
  validate_single(result,payload);quality=dict(validated=True)
 elif stage=='matching':
  sig=lambda r:sorted((tuple(g['a_ids']),tuple(g['b_ids']),g['identity']) for g in r['groups']);quality=dict(identity_equal=sig(result)==sig(old),anchors_equal=all(result[k]==old[k] for k in ['structural_anchor_group_ids','local_origin_group_id','local_reference_group_id']))
 else:quality=dict(verdicts_equal=[(r['relation_id'],r['verdict'],r['prompt_motion_review']['verdict']) for r in result['relations']]==[(r['relation_id'],r['verdict'],r['prompt_motion_review']['verdict']) for r in old['relations']])
 io.dump(out/stage/'quality.json',quality);print(stage,quality,flush=True);return quality
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--model',default='gpt-6-astra');p.add_argument('--reasoning',default='low');p.add_argument('--stages',nargs='+',default=['identity_review','presence_1','observe_shot1','observe_shot3','verify_relations','motion_shot1','motion_shot3','matching']);a=p.parse_args();owned_compute_job();out=H/a.name;out.mkdir(exist_ok=False);start=time.time()
 with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(lambda s:run(s,out,a.model,a.reasoning),a.stages))
 io.dump(out/'run.json',dict(model=a.model,reasoning=a.reasoning,seconds=time.time()-start,stages=a.stages,quality=results))
