"""Frozen upstream, fresh minimal identity and all downstream judgments. Experimental only."""
import os,sys,json,shutil,time,traceback,hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from types import SimpleNamespace
R=Path(__file__).resolve().parent; B=R.parents[1]; S=B/'scripts';sys.path.insert(0,str(S))
from run_gs_integrated import read,save,sha,CPU,GEOM
BASES=read(B/'experiments/gravity_free_pipeline_20260921/baselines.json')

def cp(a,b):
 b.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(a,b)

def reference(study,source):
 import gs_prompt_alignment as pa
 out=R/'references'/study
 if study=='study3':
  shutil.copytree(source/'prompt_alignment_reference',out);return out
 story=read(source/'narrative.json');facts={f['fact_id']:f['text'] for f in story['facts']};shots=['shot1','shot2','shot3']
 if study=='study2':
  specs=[('woman','adult woman','p01','adult woman with brown hair in a loose bun, taupe sweater and dark trousers',[1,2,3]),('notebook','red hardcover notebook','p01','red hardcover notebook',[1,2]),('desk','walnut desk','p01','walnut desk',[1,3]),('chair','wooden chair','p01','wooden chair',[1,3]),('console','hallway console','p06','narrow hallway console',[2])]
 else:
  specs=[('woman','woman','shot1','brown-haired British woman',[1,2,3]),('sofa','beige sofa','shot1','beige sofa',[1,3]),('tall_cup','tall teacup','shot1','tall narrow cup',[1,3]),('short_cup','short teacup','shot1','shorter wider cup',[1,3]),('table','wooden tea table','shot3','wooden tea table',[1,3]),('door','garden doorway','shot1','glazed garden doorway',[1,3]),('lawn','lawn','shot2','green lawn',[2]),('hedge','hedge','shot2','hedge',[2]),('planting','garden planting','shot2','garden planting',[2]),('fireplace','fireplace','shot1','fireplace',[1]),('television_cabinet','television cabinet','shot1','television cabinet',[1]),('curtains','curtains','shot1','curtains',[1,3]),('rug','rug','shot1','rug',[1,3]),('lamp','lamp','shot3','lamp',[3]),('plant','plant','shot3','plant',[3])]
 entities=[]
 for pid,name,fid,quote,required in specs:
  assert quote in facts[fid]
  entities.append(dict(prompt_entity_id=pid,name=name,description=quote,evidence=[dict(fact_id=fid,quote=quote)],schedule=[dict(shot_id=s,expectation='required' if i in required else 'not_required',reason='Explicit entity/action or scene-preservation requirement in this shot.' if i in required else 'No required on-screen appearance specified; this is not an absence claim.') for i,s in enumerate(shots,1)]))
 registry=dict(schema_version='prompt_registry_v1',shot_ids=shots,entities=entities)
 src=dict(reference_text='\n\n'.join(f['text'] for f in story['facts']),shot_ids=shots,narrative=story,registry=registry)
 save(R/'references'/f'{study}_input.json',src)
 compiled=pa.compile_reference(R/'references'/f'{study}_input.json',R/'reference_compilation'/study,1800)
 shutil.copytree(compiled.parent,out)
 return out

def prepare(study):
 source=Path(BASES[study]);case=R/'runs'/study;case.mkdir(parents=True,exist_ok=False)
 for name in ['raw_manifest.json','narrative.json','identity_scope.json','alignment_method.json']:
  cp(source/name,case/name)
 for dirname in ['inputs','selected','expected_motion','within']:
  shutil.copytree(source/dirname,case/dirname)
 for sid in ['shot1','shot2','shot3']:
  for name in ['input.json','entities.json']:cp(source/'entities/shots'/sid/name,case/'entities/shots'/sid/name)
 old=source/'pairs/pair_000';new=case/'pairs/pair_000'
 for dirname in ['inputs','selected']:shutil.copytree(old/dirname,new/dirname)
 for name in ['narrative.json','pair_scope.json','matching_initial.json','identity_review_payload.json','identity_review_images.json']:
  cp(old/name,new/name)
 cp(old/'matching_initial.json',new/'matching.json')
 cp(old/'registration/roma_geometry/registration.json',new/'registration/roma_geometry/registration.json')
 from gs_runtime_profile import profile
 from run_gs_temporal import scheduling
 for root in [case,new]:save(root/'runtime_profile.json',profile('scoring_efficiency_v1'));save(root/'scheduling.json',scheduling('parallel_v2',prompt_alignment=True))
 pinned={str(p):sha(p) for p in [source/'raw_manifest.json',source/'narrative.json',old/'matching.json',old/'matching_initial.json',old/'registration/roma_geometry/registration.json',*[source/'selected'/f'{s}_scene.json' for s in ['shot1','shot2','shot3']]]}
 save(case/'frozen_upstream.json',dict(source_case=str(source),hashes=pinned,reused=['detection','clustering','geometry','motion','registration','within_shot_reviews'],fresh=['identity','boundary_presence','boundary_spatial','appearance_codex','prompt_binding','prompt_alignment'],production_default_changed=False))
 return case

def identity(case):
 import gs_efficient_transport as transport
 import run_wedetect_shot_entities as io
 from review_aligned_entity_identities import validate,FOCUSED_SCHEMA,FOCUSED_PROTOCOL
 from gs_identity_review_minimal_input import build
 canonical=read(case/'identity_review_payload.json');payload,images=build(canonical,read(case/'identity_review_images.json'))
 for im in images:assert sha(im['path'])==im['sha256']
 args=SimpleNamespace(out=case/'calls',model='gpt-6-astra',reasoning='medium',codex_bin='/vast/users/guangyi.chen/.local/bin/codex',timeout=1800,disabled_skills=io.disabled_skills_config())
 result=transport.call('identity_review',B/'prompts/gs_aligned_identity_minimal_v1.txt',payload,images,FOCUSED_SCHEMA,args)
 validate(result,canonical,FOCUSED_PROTOCOL)
 save(case/'identity_review.json',result);save(case/'matching.json',result['matching'])
 save(case/'identity_review_audit.json',dict(passed=True,inventory_conserved=True,source_registration_frozen=True,original_witnesses_valid=True,matching_revision=FOCUSED_PROTOCOL,input_profile='aligned_centers_sizes_v1',reviewed_initial_groups=len(result['initial_group_reviews']),final_groups=len(result['matching']['groups'])))

def dino_cpu(out):
 # Same pinned processor, CLS features and scoring; CPU only to avoid occupied GPUs.
 import numpy as np,torch
 from PIL import Image
 from transformers import AutoImageProcessor,AutoModel
 import gs_entity_appearance as ap
 torch.set_num_threads(1);started=time.time();modelpath=B/'experiments/entitybench-wan21-smoke/cache/models/dinov2-base'
 m=ap.verify_sources(out);processor=AutoImageProcessor.from_pretrained(modelpath,local_files_only=True);model=AutoModel.from_pretrained(modelpath,local_files_only=True).to('cpu').eval()
 vectors=[];keys=[]
 for e in m['entities']:
  folder=out/'entities'/e['global_entity_id'];apps=read(folder/'input.json')['appearances'];zs=[]
  for start in range(0,len(apps),8):
   ims=[]
   for a in apps[start:start+8]:
    assert sha(a['crop_path'])==a['crop_sha256']
    with Image.open(a['crop_path']) as im:ims.append(im.convert('RGB'))
   with torch.inference_mode():
    z=model(**processor(images=ims,return_tensors='pt')).last_hidden_state[:,0,:].float();z=torch.nn.functional.normalize(z,dim=-1)
   zs.append(z.numpy())
  z=np.concatenate(zs);vectors.append(z);keys += [e['global_entity_id']+'/'+a['appearance_id'] for a in apps]
  result=ap.dino_statistics(z,[a['shot_id'] for a in apps]);result['appearance_ids']=[a['appearance_id'] for a in apps];save(folder/'dino.json',result)
 np.savez_compressed(out/'dino_embeddings.npz',embeddings=np.concatenate(vectors),keys=np.asarray(keys))
 save(out/'dino_runtime.json',dict(seconds=time.time()-started,device='cpu',threads=1,model_path=str(modelpath),model_hashes={p.name:sha(p) for p in modelpath.iterdir() if p.name in ('config.json','preprocessor_config.json','model.safetensors')},processor=processor.to_dict(),torch=torch.__version__,cpu_vs_gpu_exact_equivalence_claimed=False))

def run(study):
 import run_gs_temporal as pipeline
 start=time.time();state=dict(study=study,started=start,status='running');save(R/f'{study}_status.json',state)
 try:
  source=Path(BASES[study]);case=prepare(study);ref=reference(study,source)
  shutil.copytree(ref,case/'prompt_alignment_reference');cp(ref/'prompt_registry.json',case/'prompt_registry.json')
  jobs=pipeline.plan(case,read(case/'raw_manifest.json')['shots'],-1,'unused',runtime_name='scoring_efficiency_v1',stop_after='full',prompt_alignment=True)
  keep={'pair_000_identity_review','pair_000_boundary','entity_displacement','global_entity_table','prompt_binding','prompt_alignment','appearance_prepare','appearance_dino','appearance_compact','appearance_codex','appearance_report','prompt_binding_report'}
  jobs=[j for j in jobs if j['stage'] in keep]
  for j in jobs:
   j['depends']=[d for d in j['depends'] if d in keep]
   if j['stage']=='pair_000_identity_review':j['command']=[CPU,str(__file__),'identity',str(case/'pairs/pair_000')]
   if j['stage']=='appearance_dino':j.update(command=[str(GEOM),str(__file__),'dino_cpu',str(case/'appearance/canonical')],gpu=False)
  save(case/'replay_plan.json',jobs)
  env=os.environ.copy();env.update(ROCR_VISIBLE_DEVICES='',HIP_VISIBLE_DEVICES='',CUDA_VISIBLE_DEVICES='',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',MPLBACKEND='Agg')
  pipeline.execute(case,jobs,env,os.environ['SLURM_JOB_ID'],'full')
  for p,h in read(case/'frozen_upstream.json')['hashes'].items():assert sha(p)==h
  state.update(status='success',case=str(case))
 except BaseException as e:state.update(status='failed',error=repr(e),traceback=traceback.format_exc())
 state.update(seconds=time.time()-start);save(R/f'{study}_status.json',state);print(json.dumps(state),flush=True);return state

if __name__=='__main__':
 if len(sys.argv)>1:
  {'identity':identity,'dino_cpu':dino_cpu}[sys.argv[1]](Path(sys.argv[2]));sys.exit()
 from run_isolated_shot_static_3d import owned_compute_job
 owned_compute_job();start=time.time()
 with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(run,['study2','study3','study4']))
 save(R/'run_status.json',dict(status='success' if all(r['status']=='success' for r in results) else 'failed',seconds=time.time()-start,results=results))
