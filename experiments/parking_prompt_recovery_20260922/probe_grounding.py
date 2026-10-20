import sys,os,time
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'EECBench'))
from eval.evaluate_benchmark import get_grounding_dino
from groundingdino.util.inference import load_image,predict
import torch
torch.set_num_threads(4);t=time.time();m,_=get_grounding_dino(device='cpu',strict=True);print('LOADED',time.time()-t,flush=True)
p=Path('EECBench/experiments/multishot_registration_ab_20260922/inputs/parking4/frames/Shot1/frame_000000.jpg');im,x=load_image(str(p));a=predict(model=m,image=x,caption='pillar.',box_threshold=.30,text_threshold=.25,device='cpu');print('RESULT',a,'SECONDS',time.time()-t,flush=True)
