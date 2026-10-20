import os,sys,time,threading,socket
from pathlib import Path
from campaign import ROOT,FEAS,SHARED,read,write,load_pipe,NEGATIVE
sys.path[:0]=[str(FEAS/'holocine_deps'),str(FEAS/'deps'),str(FEAS/'repos/HoloCine'),str(SHARED)]
os.environ.update(HF_HUB_OFFLINE='1',TOKENIZERS_PARALLELISM='false')
cache=Path('/tmp/eecbench_holocine_staging_validation');cache.mkdir(exist_ok=True)
os.environ.update(MIOPEN_USER_DB_PATH=str(cache),MIOPEN_CUSTOM_CACHE_DIR=str(cache))
import torch
from text_context import generate_episode
row=max(read(ROOT/'queue.json')['tasks'],key=lambda t:len(t['prompt']));n=row['shot_count'];samples=[];done=threading.Event()
def monitor():
 while not done.is_set():
  d={x.split(':')[0]:x.split(':')[1].strip() for x in Path('/proc/self/smaps_rollup').read_text().splitlines() if ':' in x};samples.append(dict(t=time.time(),anon_kb=int(d['Anonymous'].split()[0])));done.wait(1)
threading.Thread(target=monitor,daemon=True).start();start=time.time();pipe=load_pipe('mapped');print('LOADED',time.time()-start,flush=True)
last={};original=pipe.scheduler.step
def step(*a,**k):
 y=original(*a,**k);assert torch.isfinite(y).all();last['finite']=True;print('STEP',time.time()-start,flush=True);return y
pipe.scheduler.step=step
out=generate_episode(pipe,row['prompt'],n,num_frames=4*n+1,shot_cut_frames=[4*j+1 for j in range(1,n)],width=256,height=144,num_inference_steps=2,negative_prompt=NEGATIVE,seed=20260922,tiled=True)
done.set();proof=dict(pass_all=last['finite'],node=socket.gethostname(),seconds=time.time()-start,peak_anon_gib=max(x['anon_kb'] for x in samples)/1024**2,samples=samples,frames=len(out));write(ROOT/'staged_memory_pilot.json',proof);print({k:v for k,v in proof.items() if k!='samples'},flush=True)
