#!/usr/bin/env python3
"""Fresh WeDetect -> isolated shot graphs -> Flow1 identity, single B judgment and original spatial scoring."""
import argparse,csv,hashlib,json,os,subprocess,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from gs_runtime_profile import profile as runtime_profile, names as runtime_names, IDENTITY_REVIEW_INPUTS, resolve_identity_review_input
from gs_identity_population import scene_scope
B=Path(__file__).resolve().parents[1];S=B/'scripts'
FRONT=B/'experiments/study2_detection_only_fresh_20260918';REG=B/'experiments/study2_full_fresh_20260918'
CPU='/vast/users/guangyi.chen/anaconda3/bin/python'
GEOM=B/'experiments/study_inconsistent_3/geocalib_boxer_20260913/venv/bin/python'
def read(p):return json.loads(Path(p).read_text())
def save(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n');tmp.replace(p)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def supported_scene_scope(shots):
 scope=scene_scope(shots)
 if any(set(pair['shot_ids'])!={'shot1','shot3'} for pair in scope['cross_shot_pairs']):
  raise ValueError('The current geometry adapter supports the same-scene shot1/shot3 pair only; other multi-shot scenes require separate pair cases, never silently skip them')
 return scope

def plan(case,gpu,uuid,stop_after="spatial",profile_name=None,identity_scope=None,alignment_method="roma_fps32",identity_review_input=None):
 if alignment_method not in ["roma_fps32","codex_direct"]:raise ValueError("Unknown alignment method")
 profile=runtime_profile(profile_name)
 identity_input=resolve_identity_review_input(profile,identity_review_input)
 case=Path(case)
 def step(name,cmd,on_gpu=False):return dict(stage=name,command=([CPU,str(FRONT/'guard_gpu.py'),str(gpu),uuid] if on_gpu else [])+list(map(str,cmd)))
 def cross(name,task):return step(name,[CPU,S/'run_gs_flow1_stage.py',case,task,'--runtime-profile',profile['name']]+(['--identity-review-input',identity_input] if task=='review_identity' else []))
 jobs=[step('detection_and_clustering',[CPU,S/'run_wedetect_shot_entities.py','--manifest',case/'raw_manifest.json','--output',case/'entities','--gpu',gpu,'--model',profile['clustering_model'],'--reasoning',profile['clustering_reasoning'],'--shot-workers','2','--codex-bin','/vast/users/guangyi.chen/.local/bin/codex','--timeout','1800'],True),step('geocalib',[GEOM,S/'prepare_gs_integrated.py',case,'calibrate'],True),step('prepare_shot_inputs',[CPU,S/'prepare_gs_integrated.py',case,'inputs'])]
 if identity_scope is not None and not identity_scope['cross_shot_pairs']:return jobs[:1]
 for sid in ['shot1','shot3']:
  jobs += [step('pi3x_'+sid,[GEOM,FRONT/'geometry.py','--method','pi3x','--shot',sid],True),step('boxer_'+sid,[GEOM,FRONT/'boxer.py','--method','pi3x','--shot',sid],True)]
 jobs += [step('motion_and_fusion',[CPU,S/'run_gs_motion_fusion.py',case,'--runtime-profile',profile['name']]),cross('initial_identity','match'),step('roma_matches',[GEOM,REG/'run_matching.py','--method','roma'],True),step('lift_correspondences',[GEOM,REG/'prepare_correspondences.py','--method','roma']),step('registration',[GEOM,S/'register_gs_3d.py','--method','roma','--sampling','fps','--sample-count','32']),cross('aligned_identity_review','review_identity')]
 if alignment_method=='codex_direct':
  jobs=[j for j in jobs if j['stage'] not in ['roma_matches','lift_correspondences']]
  jobs=[step('registration',[CPU,S/'register_gs_codex.py','--case',case]) if j['stage']=='registration' else j for j in jobs]
 if stop_after!='identity':jobs.append(cross('presence','presence'))
 if stop_after=="spatial":jobs.append(cross("spatial","spatial"))
 return jobs

def summarize(case,runtime):
 rows=[]
 paths=list(case.glob('entities/shots/*/status.json'))+list(case.glob('calls/*/status.json'))
 entity_run=read(case/'entities/run.json') if (case/'entities/run.json').exists() else {}
 shot_timing={r['shot_id']:r for r in entity_run.get('shots',[])}
 for p in sorted(set(paths)):
  state=read(p)
  if 'usage' not in state and 'known_usage' not in state:continue
  usage=state.get('usage',state.get('known_usage',[]));totals={k:sum(int(u.get(k,0)) for u in usage if u) for k in ['input_tokens','output_tokens','cached_input_tokens']}
  timing=shot_timing.get(state.get('shot_id'),state);duration=timing.get('seconds')
  if duration is None and 'started' in timing and 'finished' in timing:duration=timing['finished']-timing['started']
  rows.append(dict(call=str(p.parent.relative_to(case)),status=state['status'],seconds=duration,**totals,total_tokens=totals['input_tokens']+totals['output_tokens']))
 stage_calls={'detection_and_clustering':['entities/shots/'],'motion_and_fusion':['calls/motion_'],'initial_identity':['calls/matching'],'registration':['calls/registration_direct'],'aligned_identity_review':['calls/identity_review'],'presence':['calls/presence_1'],'spatial':['calls/observe_','calls/verify_relations']}
 for stage in runtime['stages']:
  stage['total_tokens']=sum(r['total_tokens'] for r in rows if any(r['call'].startswith(prefix) for prefix in stage_calls.get(stage['stage'],[])))
 frontend_detail={}
 times=[r for r in shot_timing.values() if 'started' in r and 'finished' in r]
 if times:
  frontend_detail['clustering_wall_seconds']=max(r['finished'] for r in times)-min(r['started'] for r in times)
  frontend_detail['detection_and_preparation_seconds']=min(r['started'] for r in times)-entity_run['started']
 runtime_config=read(case/'runtime_profile.json') if (case/'runtime_profile.json').exists() else runtime_profile('baseline')
 result=dict(frontend_timing=frontend_detail,status=runtime['status'],elapsed_seconds=runtime.get('seconds'),stages=runtime['stages'],calls=rows,total_tokens=sum(r['total_tokens'] for r in rows),model=runtime_config['model'],reasoning=runtime_config['reasoning'],runtime_profile=runtime_config,completed_through=runtime['stages'][-1]['stage'] if runtime['status']=='success' else None,spatial_evaluation_run=any(s['stage']=='spatial' and s['status']=='success' for s in runtime['stages']))
 if runtime['status']=='success':
  scope=read(case/'identity_scope.json') if (case/'identity_scope.json').exists() else None
  result['identity_scope']=scope
  has_pair=scope is None or bool(scope['cross_shot_pairs'])
  result['cross_shot_identity_status']='completed' if has_pair else 'skipped_single_shot_scenes'
  result['presence_evaluation_run']=any(st['stage']=='presence' and st['status']=='success' for st in runtime['stages'])
  if result['presence_evaluation_run']:result['presence']=read(case/'presence.json')['summary']
  if result['spatial_evaluation_run']:result['spatial']=read(case/'spatial.json')['summary']
  result['shot_counts']={s:read(case/'selected'/f'{s}_scene.json')['counts'] for s in (['shot1','shot3'] if has_pair else [])}
  result['scored_pair']=['shot1','shot3'] if has_pair else []
  result['auxiliary_clustering_counts']={p.parent.name:len(read(p)['entities']) for p in (case/'entities/shots').glob('*/entities.json') if p.parent.name not in result['scored_pair']}
 result['alignment_method']=read(case/'alignment_method.json')['method'] if (case/'alignment_method.json').exists() else 'roma_fps32'
 save(case/'summary.json',result)
 if rows:
  with (case/'calls.csv').open('w') as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 with (case/'stages.csv').open('w') as f:
  w=csv.DictWriter(f,fieldnames=['stage','status','seconds','returncode','total_tokens'],extrasaction='ignore');w.writeheader();w.writerows(runtime['stages'])
 return result

def execute_parallel_stages(case,jobs,env,run,runtime):
 """Overlap only raw RoMa inference with CPU/API motion and initial identity.

 One GPU stage at a time. Anchor filtering still waits for initial identity.
 All state writes are owned by this coordinator; workers write separate logs.
 """
 names=[j['stage'] for j in jobs]
 deps={name:({names[i-1]} if i else set()) for i,name in enumerate(names)}
 if {'roma_matches','boxer_shot3','initial_identity','lift_correspondences'}<=set(names):
  deps['roma_matches']={'boxer_shot3'}
  deps['lift_correspondences']={'roma_matches','initial_identity'}
 pending=list(jobs);done=set();active={};failed=[]
 def worker(spec):
  started=time.time()
  with (case/(spec['stage']+'.log')).open('w') as log:
   p=run(spec['command'],env=env,stdout=log,stderr=subprocess.STDOUT)
  return dict(seconds=time.time()-started,returncode=p.returncode,status='success' if p.returncode==0 else 'failed')
 with ThreadPoolExecutor(max_workers=2) as pool:
  while pending or active:
   if not failed:
    for spec in list(pending):
     if len(active)>=2:break
     if deps[spec['stage']]<=done:
      record=dict(spec,status='running',started=time.time());runtime['stages'].append(record)
      active[pool.submit(worker,spec)]=record;pending.remove(spec);print('START',spec['stage'],flush=True)
   save(case/'pipeline_runtime.json',runtime)
   if not active:
    if failed:break
    raise RuntimeError('Unresolved stage dependencies')
   completed,_=wait(active,return_when=FIRST_COMPLETED)
   for future in completed:
    record=active.pop(future)
    try:record.update(future.result())
    except Exception as exc:record.update(status='failed',seconds=time.time()-record['started'],returncode=-1,error=repr(exc))
    if record['status']=='success':done.add(record['stage'])
    else:failed.append(record['stage'])
    print('END',record['stage'],record['seconds'],record['status'],flush=True)
 if failed:raise RuntimeError('Stage failed: '+', '.join(failed))

def execute(case,jobs,env,allocation,run=subprocess.run,overlap_roma=False):
 start=time.time();runtime=dict(status='running',started=start,allocation=allocation,stages=[])
 try:
  if overlap_roma:
   execute_parallel_stages(case,jobs,env,run,runtime)
  else:
   for spec in jobs:
    record=dict(spec,status='running',started=time.time());runtime['stages'].append(record);save(case/'pipeline_runtime.json',runtime);print('START',spec['stage'],flush=True)
    with (case/(spec['stage']+'.log')).open('w') as log:p=run(spec['command'],env=env,stdout=log,stderr=subprocess.STDOUT)
    record.update(seconds=time.time()-record['started'],returncode=p.returncode,status='success' if p.returncode==0 else 'failed')
    if p.returncode:raise RuntimeError('Stage failed: '+spec['stage'])
    print('END',spec['stage'],record['seconds'],flush=True)
  for shot in read(case/'raw_manifest.json')['shots']:
   for frame in shot['frames']:
    if sha(frame['path'])!=frame['sha256']:raise ValueError('Original input changed during run')
  if any(j['stage']=='presence' for j in jobs) and read(case/'presence.json')['aggregation_version']!='single_presence_witness_v1':raise ValueError('Expected single B aggregation')
  if (case/'calls/presence_2').exists():raise ValueError('Unexpected second B call')
  if jobs[-1]['stage']=='aligned_identity_review' and not (case/'identity_review.json').is_file():raise ValueError('Missing final identity review')
  if jobs[-1]['stage']=='spatial' and not (case/'spatial.json').is_file():raise ValueError('Missing final spatial score')
  runtime['status']='success'
 except BaseException as exc:
  runtime.update(status='failed',error=repr(exc))
  if runtime['stages'] and runtime['stages'][-1]['status']=='running':runtime['stages'][-1].update(status='failed',seconds=time.time()-runtime['stages'][-1]['started'])
  raise
 finally:
  runtime.update(finished=time.time(),seconds=time.time()-start);save(case/'pipeline_runtime.json',runtime);summarize(case,runtime)
 return runtime

def prepare(case,manifest,narrative,model_manifest,geocalib_weights,protocol='flow1_fused_v1',coordinate_mode='gravity_aligned'):
 from PIL import Image
 from run_wedetect_shot_entities import load_manifest
 if case.exists():raise FileExistsError('Use a new output directory; no implicit reuse or resume')
 shots=load_manifest(manifest)
 scope=scene_scope(shots) if protocol=='temporal_v2' else supported_scene_scope(shots)
 for shot in shots:
  sizes=[]
  for frame in shot['frames']:
   with Image.open(frame['path']) as im:
    if im.format!='JPEG':raise ValueError('Supply original JPEG keyframes')
    sizes.append(im.size)
  if len(set(sizes))!=1:raise ValueError('Existing geometry backend requires constant resolution within each shot')
 story=read(narrative)
 if not isinstance(story.get('facts'),list) or not story['facts']:raise ValueError('Provide normal story facts including relevant intervening shots')
 ids=[f['fact_id'] for f in story['facts']]
 if len(ids)!=len(set(ids)):raise ValueError('Duplicate story fact IDs')
 needs_geometry=protocol=='temporal_v2' or bool(scope['cross_shot_pairs'])
 metadata=read(model_manifest) if needs_geometry else {'files':[]}
 if needs_geometry and (not all(Path(f['path']).is_file() for f in metadata['files']) or (coordinate_mode=='gravity_aligned' and not geocalib_weights.is_file())):raise FileNotFoundError('Pretrained assets missing')
 config=read(B/'configs/gs-consistency-two-scores.v1.json')
 if config['static_entity_consistency']['judgment_calls']!=1:raise ValueError('Expected single B config')
 case.mkdir(parents=True);save(case/'identity_scope.json',scope);save(case/'raw_manifest.json',dict(shots=shots));save(case/'narrative.json',story);save(case/'yyfz233--Pi3X_download.json',metadata);save(case/'config_snapshot.json',config)
 if needs_geometry and coordinate_mode=='gravity_aligned':
  weight=case/'calibration_new/weights/geocalib-pinhole.tar';weight.parent.mkdir(parents=True);weight.symlink_to(geocalib_weights.resolve())
 sources=[Path(__file__),S/'prepare_gs_integrated.py',S/'run_gs_motion_fusion.py',S/'run_wedetect_shot_entities.py',S/'run_gs_flow1_stage.py',S/'gs_flow1_evaluator.py']+[FRONT/n for n in ['geometry.py','boxer.py','guard_gpu.py']]+[REG/n for n in ['common.py','run_matching.py','prepare_correspondences.py','register.py']]
 sources += [S/'register_gs_3d.py',S/'register_gs_codex.py',B/'prompts/gs_direct_registration_v1.txt',S/'gs_registration_3d.py',S/'gs_registration_so3.py',S/'gs_boxer_camera_frame.py',S/'gs_registration_variants.py',B/'configs/gs-consistency-two-scores.v1.json', S/'gs_flow1_compact_payload.py',S/'gs_flow1_compact_transport.py',S/'run_isolated_shot_static_3d.py',S/'review_aligned_entity_identities.py']
 sources += [S/'gs_identity_population.py', B/'prompts/gs_aligned_identity_review_v1.txt', B/'prompts/gs_aligned_identity_scoring_v1.txt', S/'gs_runtime_profile.py',S/'gs_efficient_transport.py',S/'gs_witness_codec.py',B/'configs/gs-runtime-profiles.v1.json']
 sources += [S/'gs_identity_review_minimal_input.py',B/'prompts/gs_aligned_identity_minimal_v1.txt']
 sources+=list((B/'prompts/gs_flow1').glob('*.txt'))+list((B/'skills/wedetect-shot-entities').glob('*.txt'))
 if protocol=='temporal_v2':
  sources += list(S.glob('gs_temporal_*.py'))+list(S.glob('run_gs_temporal*.py'))+[S/'gs_episode_entities.py',S/'gs_boundary_spatial_review.py',S/'gs_boundary_relative_review.py',S/'gs_shot_motion.py',S/'gs_entity_displacement.py']
  sources += [S/n for n in ['gs_appearance_integration.py','gs_entity_appearance.py','gs_entity_appearance_compact.py','gs_entity_appearance_minimal.py','gs_entity_appearance_scoring.py']]
  sources += [B/'prompts/appearance'/n for n in ['entity_v1.txt','entity_compact_v2.txt','evaluator_base_v1.txt']]
 save(case/'coordinate_mode.json',dict(mode=coordinate_mode))
 save(case/'provenance.json',dict(inference_reuse=False,model_metadata_source=str(model_manifest),geocalib_weights=str(geocalib_weights.resolve()) if coordinate_mode=='gravity_aligned' else None,source_hashes={str(p):sha(p) for p in sources}))

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ['manifest','narrative','output']:p.add_argument('--'+name,required=True,type=Path)
 p.add_argument('--alignment-method',choices=['roma_fps32','roma_fps32_free3d','codex_direct'],default='roma_fps32')
 p.add_argument('--consistency-protocol',choices=['temporal_v2','flow1_fused_v1'],default='temporal_v2')
 p.add_argument('--schedule-profile',choices=['parallel_v2','parallel_v1','legacy'],default='parallel_v2',help='Temporal scheduling only; legacy restores the previous dependencies and worker counts')
 p.add_argument('--identity-review-input',choices=IDENTITY_REVIEW_INPUTS,help='Post-registration review evidence: minimal (current default) or full (previous workflow); other runtime profiles retain their own defaults')
 p.add_argument('--runtime-profile',choices=runtime_names());p.add_argument('--stop-after',choices=['identity','presence','spatial','full'],help='Default: full (temporal_v2 includes appearance); historical flow1_fused_v1 defaults to spatial');p.add_argument('--gpu',required=True,type=int);p.add_argument('--gpu-uuid',required=True);p.add_argument('--plan-only',action='store_true',help='Print commands without creating outputs or running models')
 p.add_argument('--model-manifest',type=Path,default=FRONT/'study2/yyfz233--Pi3X_download.json');p.add_argument('--geocalib-weights',type=Path,default=B/'experiments/study_inconsistent_3/geocalib_boxer_20260913/weights/geocalib-pinhole.tar')
 p.add_argument('--prompt-recovery',choices=['auto','off'],default='auto',help='With a registry, recover shot-level detection gaps before geometry; off restores old frontend')
 p.add_argument('--prompt-recovery-device',choices=['cuda','cpu'],default='cuda')
 p.add_argument('--prompt-registry',type=Path,help='Frozen prompt_registry_v1 with schedule; enables post-identity binding')
 p.add_argument('--prompt-alignment-contract',type=Path,help='Frozen prompt_alignment_b_v1; independent normal reference, binding and full-run alignment scores')
 a=p.parse_args()
 if a.alignment_method=='roma_fps32_free3d':
  if a.consistency_protocol!='temporal_v2':p.error('Gravity-free pipeline requires temporal_v2')
  if a.runtime_profile is None:a.runtime_profile='gravity_free_v1'
 if a.prompt_registry and a.consistency_protocol!='temporal_v2':p.error('--prompt-registry requires temporal_v2')
 if a.prompt_alignment_contract and a.consistency_protocol!='temporal_v2':p.error('--prompt-alignment-contract requires temporal_v2')
 if a.stop_after is None:a.stop_after='full' if a.consistency_protocol=='temporal_v2' else 'spatial'
 if a.consistency_protocol=='flow1_fused_v1' and a.stop_after=='full':
  p.error('Appearance integration requires temporal_v2; use --stop-after spatial for the historical Flow1 pipeline')
 if a.consistency_protocol=='temporal_v2':
  from run_gs_temporal import run
  return run(a)
 profile=runtime_profile(a.runtime_profile);profile['identity_review_input']=resolve_identity_review_input(profile,a.identity_review_input);case=a.output.resolve();scope=supported_scene_scope(read(a.manifest)['shots']);jobs=plan(case,a.gpu,a.gpu_uuid,a.stop_after,profile['name'],scope,a.alignment_method,profile['identity_review_input'])
 if a.plan_only:print(json.dumps(jobs,indent=2));return
 from run_isolated_shot_static_3d import owned_compute_job
 allocation=owned_compute_job()
 if not a.gpu_uuid.startswith('GPU-'):raise ValueError('Verified ROCr UUID required')
 prepare(case,a.manifest.resolve(),a.narrative.resolve(),a.model_manifest.resolve(),a.geocalib_weights.resolve());save(case/'runtime_profile.json',profile);save(case/'alignment_method.json',dict(method=a.alignment_method))
 env=os.environ.copy();env.update(CASE_ROOT=str(case),PYTHONPATH=str(B/'experiments/shot_scene_boxes_goal_20260916/deps'),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='4')
 for key,name in [('MIOPEN_USER_DB_PATH','miopen_db'),('MIOPEN_CUSTOM_CACHE_DIR','miopen_cache'),('MPLCONFIGDIR','matplotlib')]:
  d=case/'runtime_cache'/name;d.mkdir(parents=True);env[key]=str(d)
 execute(case,jobs,env,allocation,overlap_roma=profile['overlap_roma_with_identity'])
if __name__=='__main__':main()
