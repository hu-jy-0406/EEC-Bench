import os,sys,json,gc,time
from pathlib import Path
from campaign import ROOT,FEAS,SHARED,read,write,load_pipe,NEGATIVE
sys.path[:0]=[str(FEAS/'holocine_deps'),str(FEAS/'deps'),str(FEAS/'repos/HoloCine'),str(SHARED)]
os.environ['HF_HUB_OFFLINE']='1';os.environ['TOKENIZERS_PARALLELISM']='false'
import torch,numpy as np
from text_context import generate_episode
q=read(ROOT/'queue.json');task=max(q['tasks'],key=lambda t:len(t['prompt']))
# Same original prompt with all shot spans, short geometry only for storage equivalence.
n=task['shot_count'];frames=4*n+1;cuts=[4*j+1 for j in range(1,n)];reference=None;proof=[]
for mode in ['standard','mapped']:
 pipe=load_pipe(mode);last={};orig=pipe.scheduler.step
 def step(*a,**k):
  v=orig(*a,**k);last['latents']=v.detach().cpu();return v
 pipe.scheduler.step=step
 for repeat in range(1 if mode=='standard' else 2):
  start=time.time();out=generate_episode(pipe,task['prompt'],n,num_frames=frames,shot_cut_frames=cuts,width=256,height=144,num_inference_steps=2,negative_prompt=NEGATIVE,seed=20260922,tiled=True)
  pixels=np.stack([np.asarray(im) for im in out]);latents=last['latents'];assert torch.isfinite(latents).all()
  if reference is None:reference=(latents.clone(),pixels.copy())
  else:assert torch.equal(reference[0],latents) and np.array_equal(reference[1],pixels),'Storage changed generated result'
  proof.append(dict(mode=mode,repeat=repeat,seconds=time.time()-start,latent_bit_exact=True,pixels_bit_exact=True));print(proof[-1],flush=True)
 del pipe,last,out;gc.collect();torch.cuda.empty_cache()
write(ROOT/'mapped_validation.json',dict(pass_all=True,proof=proof,episode_id=task['episode_id'],frames=frames,size=[256,144],steps=2,scope='Short generation storage equivalence; not full-resolution production quality',finished=time.time()))
