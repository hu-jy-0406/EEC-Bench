"""Frozen 200-episode HoloCine campaign; atomic claims and strict 100/200 barrier."""
import argparse,contextlib,fcntl,hashlib,json,os,socket,sys,threading,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parent
FEAS=ROOT.parent/'generation_feasibility_20260921'
SHARED=ROOT.parent/'holocine_shared_prompts_20260922'
PY='/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python'
NEGATIVE='过曝，静态，细节模糊不清，字幕，最差质量，低质量，畸形，多余的手指'
def read(p):return json.loads(Path(p).read_text())
def write(p,d):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+f'.{os.getpid()}.{threading.get_ident()}.tmp');tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');os.replace(tmp,p)
@contextlib.contextmanager
def locked():
 with (ROOT/'queue.lock').open('a') as f:fcntl.flock(f,fcntl.LOCK_EX);yield

def prepare():
 with locked():
  assert not (ROOT/'queue.json').exists(),'Never overwrite existing queue'
  rows=[json.loads(s) for s in (SHARED/'deliverables/priority200.jsonl').read_text().splitlines()];assert len(rows)==200
  tasks=[]
  for i,row in enumerate(rows,1):
   assert row['generation_priority']==i and row['required_text_len']==1519
   prompt=read(SHARED/'deliverables'/row['input_path'])['prompt'];assert hashlib.sha256(prompt.encode()).hexdigest()==row['prompt_sha256']
   d=ROOT/'inputs'/row['episode_id'];d.mkdir(parents=True,exist_ok=True)
   import shutil
   src=SHARED/'deliverables'/Path(row['input_path']).parent
   for name in ['holocine_input.json','contract.json','alignment_contract.json','entity_schedule.json','shot_mapping.json','structured_prompt.json','token_audit.json']:shutil.copyfile(src/name,d/name)
   n=row['shot_count'];frames=80*n+1;cuts=[80*j+1 for j in range(1,n)]
   tasks.append(dict(episode_id=row['episode_id'],rank=i,stage=1 if i<=100 else 2,prompt=prompt,prompt_sha256=row['prompt_sha256'],shot_count=n,frames=frames,cuts=cuts,seed=int.from_bytes(hashlib.sha256(('holocine200-v1:'+row['episode_id']).encode()).digest()[:4],'big'),status='pending',attempts=0))
  write(ROOT/'queue.json',dict(created=time.time(),tasks=tasks));write(ROOT/'manifest.json',dict(episodes=200,shots=sum(t['shot_count'] for t in tasks),priority='first100 must all pass before additional100',source=str(SHARED),text_len=1519,model='HoloCine-14B-full',size=[832,480],fps=16,frames='80*shots+1',steps=50,cfg=5,sigma_shift=5,negative_prompt=NEGATIVE,weights='official BF16; no quantization',memory='original offload or exactly equivalent file-backed CPU storage',stop_after=200,new_allocations_requested=False))
def claim(worker):
 with locked():
  q=read(ROOT/'queue.json')
  for stage in (1,2):
   group=[t for t in q['tasks'] if t['stage']==stage]
   if all(t['status']=='done' for t in group):continue
   task=next((t for t in group if t['status']=='pending'),None)
   if task is None:return 'wait'
   task.update(status='running',worker=worker,started=time.time(),attempts=task['attempts']+1);write(ROOT/'queue.json',q);return dict(task)
  return None

def finish(task,worker,result=None,error=None):
 with locked():
  q=read(ROOT/'queue.json');t=next(t for t in q['tasks'] if t['episode_id']==task['episode_id']);assert t['status']=='running' and t['worker']==worker
  if error:t.update(status='pending' if t['attempts']<t.get('max_attempts',2) else 'failed',error=error,ended=time.time())
  else:t.update(status='done',result=result,ended=time.time())
  write(ROOT/'queue.json',q)
  if all(t['status']=='done' for t in q['tasks']):write(ROOT/'complete.json',dict(completed=time.time(),episodes=200,shots=sum(t['shot_count'] for t in q['tasks'])))

def load_pipe(mode, use_usp=False):
 import torch
 from diffsynth.pipelines.wan_video_holocine import WanVideoHoloCinePipeline,ModelConfig
 base=FEAS/'models/Wan2.2-T2V-A14B';ck=FEAS/'models/HoloCine/HoloCine_dit/full'
 paths=[base/'models_t5_umt5-xxl-enc-bf16.pth',ck/'full_high_noise.safetensors',ck/'full_low_noise.safetensors',base/'Wan2.1_VAE.pth']
 if mode=='mapped':
  assert read(ROOT/'mapped_weights/complete.json')['all_tensors_equal_official_bf16']
  from local_cache import CACHE
  assert read(CACHE/'verified.json')['source_proof']==read(ROOT/'mapped_weights/complete.json')
  paths=[CACHE/f'{i}.safetensors' for i in range(4)]
  from mapped_storage import install_shared_loader
  install_shared_loader(CACHE)
 pipe=WanVideoHoloCinePipeline.from_pretrained(torch_dtype=torch.bfloat16,device='cuda',model_configs=[ModelConfig(path=str(p),offload_device='cpu') for p in paths],tokenizer_config=ModelConfig(path=str(base/'google/umt5-xxl')),redirect_common_files=False,use_usp=use_usp)
 pipe.enable_vram_management(vram_limit=52)
 if mode=='mapped':
  from mapped_storage import install
  install(pipe)
 from text_context import configure_pipeline
 configure_pipeline(pipe);return pipe

def worker(args):
 sys.path[:0]=[str(FEAS/'holocine_deps'),str(FEAS/'deps'),str(FEAS/'repos/HoloCine'),str(SHARED)]
 os.environ.update(HF_HUB_OFFLINE='1',TOKENIZERS_PARALLELISM='false')
 cache=Path('/tmp')/'eecbench_holocine200_miopen'/args.worker;cache.mkdir(parents=True,exist_ok=True)
 os.environ.update(MIOPEN_USER_DB_PATH=str(cache),MIOPEN_CUSTOM_CACHE_DIR=str(cache))
 state=dict(worker=args.worker,node=socket.gethostname(),pid=os.getpid(),job=os.environ.get('SLURM_JOB_ID'),uuid=os.environ['ROCR_VISIBLE_DEVICES'],mode=args.mode,transport=('local_staged_mmap_v4' if args.mode=='mapped' else 'standard'),cpus=sorted(os.sched_getaffinity(0)),state='loading',started=time.time());stop=threading.Event()
 def heartbeat():
  while not stop.is_set():write(ROOT/'workers'/f'{args.worker}.json',dict(state,heartbeat=time.time()));stop.wait(20)
 threading.Thread(target=heartbeat,daemon=True).start();task=None
 try:
  import torch
  from diffsynth import save_video
  from text_context import generate_episode,validate_prompt
  import imageio_ffmpeg
  import numpy as np
  # Serialize model construction on each node to bound transient host RAM.
  lockpath=ROOT/'loader_locks'/state['node'];lockpath.parent.mkdir(exist_ok=True)
  with lockpath.open('a') as f:
   fcntl.flock(f,fcntl.LOCK_EX);pipe=load_pipe(args.mode)
  torch.cuda.synchronize();state.update(state='ready',loaded=time.time());print('MODEL_READY',json.dumps(state),flush=True)
  scheduler_step=pipe.scheduler.step
  def finite_step(*a,**kw):
   y=scheduler_step(*a,**kw)
   if not torch.isfinite(y).all().item():raise RuntimeError('Nonfinite diffusion latent')
   return y
  pipe.scheduler.step=finite_step
  original_convert=pipe.vae_output_to_video
  def finite_pixels(x,*a,**kw):
   if not torch.isfinite(x).all().item():raise RuntimeError('Nonfinite decoded tensor')
   return original_convert(x,*a,**kw)
  pipe.vae_output_to_video=finite_pixels
  while not (ROOT/'STOP').exists():
   task=claim(args.worker)
   if task is None:state['state']='complete';break
   if task=='wait':task=None;state['state']='waiting_for_phase_barrier';time.sleep(20);continue
   attempt=ROOT/'attempts'/task['episode_id']/str(task['attempts']);attempt.mkdir(parents=True,exist_ok=True)
   state.update(state='generating',episode_id=task['episode_id'],rank=task['rank'],step=0,steps=50,episode_started=time.time());write(attempt/'input.json',task)
   audit=validate_prompt(pipe,task['prompt'],task['shot_count']);write(attempt/'text_audit.json',audit)
   def progress(it):
    for i,ts in enumerate(it):
     if i==0:fcntl.flock(prep_lock,fcntl.LOCK_UN)
     state.update(state='denoising',step=i,step_started=time.time());start=time.perf_counter();yield ts;torch.cuda.synchronize()
     state.update(step=i+1,last_step_at=time.time())
     with (attempt/'steps.jsonl').open('a') as f:f.write(json.dumps(dict(step=i+1,seconds=time.perf_counter()-start,timestep=float(ts)))+'\n')
   start=time.perf_counter();torch.cuda.reset_peak_memory_stats()
   # Serialize text/input preparation to bound observed transient host allocations.
   prep_lock=(ROOT/'loader_locks'/(state['node']+'_prefill')).open('a')
   fcntl.flock(prep_lock,fcntl.LOCK_EX)
   try:
    video=generate_episode(pipe,task['prompt'],task['shot_count'],num_frames=task['frames'],shot_cut_frames=task['cuts'],width=832,height=480,num_inference_steps=50,cfg_scale=5.,sigma_shift=5.,negative_prompt=NEGATIVE,tiled=True,seed=task['seed'],progress_bar_cmd=progress)
   finally:
    fcntl.flock(prep_lock,fcntl.LOCK_UN);prep_lock.close()
   state['state']='validating';generation=time.perf_counter()-start;assert len(video)==task['frames']
   lo,hi=255,0
   for im in video:
    ar=np.asarray(im);assert ar.shape==(480,832,3) and np.isfinite(ar).all();lo=min(lo,int(ar.min()));hi=max(hi,int(ar.max()))
   assert hi>lo,'Constant output'
   path=attempt/'episode.mp4';save_video(video,str(path),fps=16,quality=5)
   import subprocess
   subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-threads','2','-i',str(path),'-f','null','-'],check=True,capture_output=True)
   decoded,seconds=imageio_ffmpeg.count_frames_and_secs(str(path));assert decoded==task['frames']
   from PIL import Image,ImageDraw
   picks=sorted(set([0,len(video)-1]+[min(len(video)-1,40+80*i) for i in range(task['shot_count'])]));sheet=Image.new('RGB',(416*4,260*((len(picks)+3)//4)))
   draw=ImageDraw.Draw(sheet)
   for j,idx in enumerate(picks):sheet.paste(video[idx].resize((416,240)),((j%4)*416,(j//4)*260));draw.text(((j%4)*416,(j//4)*260+242),str(idx),fill='white')
   sheet.save(attempt/'contactsheet.jpg')
   result=dict(episode_id=task['episode_id'],rank=task['rank'],frames=decoded,seconds=seconds,generation_seconds=generation,finite_latents_and_decoder=True,full_decode=True,prompt_sha256=task['prompt_sha256'],seed=task['seed'],worker=args.worker,peak_gib=torch.cuda.max_memory_allocated()/2**30,completed=time.time(),video_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),attempt=str(attempt))
   write(attempt/'result.json',result);dest=ROOT/'videos'/task['episode_id'];dest.parent.mkdir(exist_ok=True)
   os.symlink(os.path.relpath(attempt,dest.parent),dest);finish(task,args.worker,result=result);print('EPISODE_DONE',json.dumps(result),flush=True);task=None;del video;torch.cuda.empty_cache()
  else:state['state']='stopped_between_episodes'
 except BaseException:
  err=traceback.format_exc();state.update(state='failed',error=err)
  if isinstance(task,dict):finish(task,args.worker,error=err)
  print(err,flush=True);raise
 finally:stop.set();write(ROOT/'workers'/f'{args.worker}.json',dict(state,heartbeat=time.time()))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','worker']);p.add_argument('--worker');p.add_argument('--mode',choices=['standard','mapped'],default='standard');a=p.parse_args()
 if a.action=='prepare':prepare()
 else:worker(a)
