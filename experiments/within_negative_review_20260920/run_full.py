"""Three independent fresh temporal v2 pipelines, disjoint GPUs and CPU cores, guarded RSS."""
import json,os,signal,subprocess,sys,time,shutil,traceback,re
from pathlib import Path
import psutil
ROOT=Path(__file__).resolve().parent/'full';ROOT.mkdir(exist_ok=True);B=ROOT.parents[2];sys.path.insert(0,str(B/'scripts'))
from run_gs_integrated import read,save,sha,CPU,GEOM
from run_isolated_shot_static_3d import owned_compute_job
NAMES=[('study2','roma_fps32'),('study3','roma_fps32'),('study4','roma_fps32')]
def main():
 job=owned_compute_job()
 smi=subprocess.check_output(['rocm-smi','--showuniqueid','--showuse','--showmeminfo','vram','--showpids','--showpidgpus'],text=True)
 (ROOT/'allocation_gpu_snapshot.txt').write_text(smi)
 gpu_pairs=[(int(i),'GPU-'+u.lower().zfill(16)) for i,u in re.findall(r'GPU\[(\d+)\].*Unique ID:\s*0x([0-9a-fA-F]+)',smi)]
 if len(gpu_pairs)!=3:raise RuntimeError('Launch this coordinator in a three-GPU Slurm step')
 cores=sorted(os.sched_getaffinity(0))
 if len(cores)<12:raise RuntimeError('Need12allocatedCPUcores for3pipelines')
 assert not (ROOT/'status.json').exists(),'Do not duplicate this three-run launch'
 manifests={};narratives={}
 for study in ['study2','study3','study4']:
  source=(B/'experiments/alignment_full_four_20260919'/f'{study}_manifest.json') if study!='study4' else B/'experiments/study3_concise_mtd_fps32_20260919/manifest.json'
  value=read(source)
  for shot in value['shots']:
   for frame in shot['frames']:assert sha(frame['path'])==frame['sha256']
  save(ROOT/f'{study}_manifest.json',value);manifests[study]=ROOT/f'{study}_manifest.json'
  narrative=(B/'experiments/alignment_full_four_20260919/narrative.json') if study!='study4' else B/'experiments/study3_concise_mtd_fps32_20260919/narrative.json'
  shutil.copy2(narrative,ROOT/f'{study}_narrative.json');narratives[study]=ROOT/f'{study}_narrative.json'
 save(ROOT/'input_sources.json',dict(study4_original_directory=str(B/'experiments/study3-concise-mtd-local'),input_reuse='original keyframe bytes and normal prompts only; all model inference fresh'))
 sources=[B/'configs/gs-temporal-v2.json']+list((B/'scripts').glob('*.py'))+list((B/'prompts/gs_flow1').glob('*.txt'))+list((B/'skills/wedetect-shot-entities').glob('*.*'))+[B/'prompts/gs_direct_registration_v1.txt',B/'prompts/gs_aligned_identity_review_v1.txt',B/'configs/gs-consistency-two-scores.v1.json',B/'configs/gs-runtime-profiles.v1.json']
 for p in sources:
  dest=ROOT/'code_snapshot'/p.relative_to(B);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
 save(ROOT/'source_hashes.json',{str(p):sha(p) for p in sources})
 # Each guard checks utilization, VRAM, UUID and every resident KFD mapping.
 for gpu,uuid in gpu_pairs:
  result=subprocess.run([CPU,str(B/'experiments/study2_detection_only_fresh_20260918/guard_gpu.py'),str(gpu),uuid,'/usr/bin/true'],capture_output=True,text=True)
  (ROOT/f'gpu_preflight_{gpu}.txt').write_text(result.stdout+result.stderr);assert result.returncode==0,result.stdout+result.stderr
 state=dict(status='running',started=time.time(),allocation=job,pid=os.getpid(),runs=[],rss_limit_gib=52,protocol='three independent fresh temporal v2 inferences; only input bytes/code/pretrained weights reused; no appearance stage')
 save(ROOT/'status.json',state);active=[]
 try:
  for index,((study,method),(gpu,uuid)) in enumerate(zip(NAMES,gpu_pairs)):
   name=study;case=ROOT/name;assert not case.exists()
   env=os.environ.copy();env.update(OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',TOKENIZERS_PARALLELISM='false')
   for key in ['HIP_VISIBLE_DEVICES','CUDA_VISIBLE_DEVICES','ROCR_VISIBLE_DEVICES']:env.pop(key,None)
   command=['taskset','-c',','.join(map(str,cores[index*4:index*4+4])),CPU,str(B/'scripts/run_gs_integrated.py'),'--manifest',str(manifests[study]),'--narrative',str(narratives[study]),'--output',str(case),'--gpu',str(gpu),'--gpu-uuid',uuid,'--runtime-profile','temporal_spatial_v1','--alignment-method',method,'--stop-after','spatial','--consistency-protocol','temporal_v2']
   log=(ROOT/f'{name}.log').open('w');p=subprocess.Popen(command,env=env,cwd=B.parent,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   rec=dict(name=name,study=study,method=method,case=str(case),gpu=gpu,uuid=uuid,cpu_cores=cores[index*4:index*4+4],pid=p.pid,command=command,status='running',started=time.time());state['runs'].append(rec);active.append((p,log,rec));save(ROOT/'status.json',state)
  while any(p.poll() is None for p,_,_ in active):
   rss=0
   for p,log,rec in active:
    if p.poll() is not None:
     if rec['status']=='running':rec.update(status='success' if p.returncode==0 else 'failed',returncode=p.returncode,finished=time.time());log.flush()
     continue
    try:
     processes=[psutil.Process(p.pid),*psutil.Process(p.pid).children(recursive=True)]
     for proc in processes:
      try:rss+=proc.memory_info().rss
      except psutil.Error:pass
    except psutil.Error:pass
   state['rss_gib']=rss/1024**3;state['updated']=time.time();save(ROOT/'status.json',state)
   if rss>52*1024**3:raise RuntimeError('Own three-run process-tree RSS exceeded52GiB; stop own runs to protect allocation')
   time.sleep(5)
  for p,log,rec in active:
   rec.update(status='success' if p.returncode==0 else 'failed',returncode=p.returncode,finished=rec.get('finished',time.time()));log.close()
  state['status']='success' if all(r['status']=='success' for r in state['runs']) else 'failed'
 except BaseException as exc:
  state.update(status='failed',error=repr(exc));traceback.print_exc()
  for p,log,rec in active:
   if p.poll() is None:
    os.killpg(p.pid,signal.SIGTERM);rec.update(status='interrupted_by_resource_guard',reason=repr(exc))
 finally:
  state.update(finished=time.time(),seconds=time.time()-state['started']);save(ROOT/'status.json',state)
  if (ROOT/'report.py').exists():
   p=subprocess.run([CPU,str(ROOT/'report.py')],cwd=B.parent);state['report_returncode']=p.returncode;save(ROOT/'status.json',state)
 return 0 if state['status']=='success' else 1
if __name__=='__main__':raise SystemExit(main())
