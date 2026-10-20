"""Study1 original JPEG versus width852 lossless resized inputs; WeDetect only."""
import argparse, hashlib, importlib.util, json, os, shutil, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
BASE=ROOT/'EECBench'
SCRIPTS=BASE/'scripts'
sys.path.insert(0,str(SCRIPTS))
import run_wedetect_shot_entities as io
from run_isolated_shot_static_3d import owned_compute_job
GROUPS=['original_shot1','resized_shot1','original_shot3','resized_shot3']
DETPY=BASE/'experiments/study_inconsistent_2/detector_upgrade_20260910/venv/bin/python'
GEOPY=BASE/'experiments/study_inconsistent_3/geocalib_boxer_20260913/venv/bin/python'
PY=Path('/vast/users/guangyi.chen/anaconda3/bin/python')
PORT=ROOT/'to_human/eec-bench-repro-20260912'
def save(p,x):io.dump(p,x)
def read(p):return io.read(p)
def log(*x):print(time.strftime('%H:%M:%S'),*x,flush=True)
def module(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def prepare():
 import cv2,numpy as np
 from PIL import Image
 cv2.setNumThreads(1)
 source=BASE/'experiments/study01_gs_v12_20260915/study1/entities/manifest.json'
 target=BASE/'experiments/study01_gs_v12_20260915/study0/entities/manifest.json'
 originals={s['shot_id']:s for s in read(source)['shots']}
 targets={s['shot_id']:s for s in read(target)['shots']}
 records=[]
 for sid in ['shot1','shot3']:
  original=originals[sid];converted=[]
  size=Image.open(targets[sid]['frames'][0]['path']).size
  assert size==(852,480)
  for f in original['frames']:
   assert io.sha(f['path'])==f['sha256']
   im=Image.open(f['path']).convert('RGB');assert im.size==(854,480)
   array=cv2.resize(np.asarray(im),size,interpolation=cv2.INTER_LINEAR)
   dest=OUT/('resized_'+sid)/'inputs'/f"frame_{f['frame_id']:06d}.png";dest.parent.mkdir(parents=True,exist_ok=True)
   Image.fromarray(array).save(dest,format='PNG')
   assert np.array_equal(np.asarray(Image.open(dest).convert('RGB')),array)
   converted.append(dict(f,path=str(dest),sha256=io.sha(dest)))
   records.append(dict(shot=sid,frame_id=f['frame_id'],source=f['path'],source_sha256=f['sha256'],source_size=list(im.size),resized=str(dest),resized_sha256=io.sha(dest),resized_size=list(size),resampling='OpenCV INTER_LINEAR on PIL decoded original RGB',encoding='lossless PNG',pixel_roundtrip_exact=True))
  save(OUT/('original_'+sid)/'entities/manifest.json',dict(shots=[original]))
  save(OUT/('resized_'+sid)/'entities/manifest.json',dict(shots=[dict(shot_id=sid,frames=converted)]))
 save(OUT/'inputs.json',records)
 log('PREPARED',len(records),'pairs')
def detect():
 import numpy as np, torch
 from PIL import Image
 sys.path.insert(0,str(PORT/'detector'))
 from wedetect_adapter import Detector, np_sigmoid, rescale
 torch.set_num_threads(2);torch.manual_seed(0);np.random.seed(0)
 det=Detector(PORT/'weights/wedetect_base_uni.pth','cpu')
 captured={}
 def capture(mod,args,result):
  captured['data']=[x[0].detach().cpu().numpy().copy() for x in result]
 hook=det.model.register_forward_hook(capture)
 state=dict(status='running',device='cpu',python=sys.executable,torch=torch.__version__,numpy=np.__version__,seed=0,threads=2,weights_sha256=io.sha(PORT/'weights/wedetect_base_uni.pth'),source_hashes=det.source_hashes,adapter_sha256=io.sha(PORT/'detector/wedetect_adapter.py'),policy=dict(objectness=.1,nms_iou=.7,top100=100,class_match=.4),groups={})
 save(OUT/'detector_runtime.json',state)
 for group in GROUPS:
  torch.manual_seed(0);np.random.seed(0)
  er=OUT/group/'entities';shot=read(er/'manifest.json')['shots'][0];results=[];diagnostics=[]
  for f in shot['frames']:
   p=Path(f['path']);assert io.sha(p)==f['sha256'];im=Image.open(p).convert('RGB');w,h=im.size
   ds=det.predict(im);scores,boxes,embeds=captured.pop('data');d=er/'detections'/shot['shot_id']/f"frame_{f['frame_id']:06d}";d.mkdir(parents=True,exist_ok=False)
   np.savez_compressed(d/'raw_forward.npz',scores=scores,boxes_letterbox=boxes,embeds=embeds)
   save(d/'detections.json',dict(shot=shot['shot_id'],frame_id=f['frame_id'],sha256=f['sha256'],image_size=[w,h],detections=ds))
   results.append(dict(shot=shot['shot_id'],frame_id=f['frame_id'],count=len(ds)))
   diagnostic=dict(frame_id=f['frame_id'],count=len(ds),window=[x for x in ds if x['label']=='窗户'],door=[x for x in ds if x['label']=='门'])
   obj=scores.max(1);pix=np.array([rescale((640,640),b.copy(),(h,w)) for b in boxes])
   for label,roi in [('窗户',[277*w/852,0,445*w/852,225]),('门',[0,0,166*w/854,480])]:
    roi=np.array(roi);inter=np.maximum(0,np.minimum(pix[:,2:],roi[2:])-np.maximum(pix[:,:2],roi[:2])).prod(1);union=np.maximum(0,pix[:,2:]-pix[:,:2]).prod(1)+np.prod(roi[2:]-roi[:2])-inter;near=np.flatnonzero(inter/np.maximum(union,1e-12)>=.5)
    k=det.vocab.index(label);probs=np_sigmoid((embeds[near]@det.text[k])*det.scales[near]+det.biases[near])
    diagnostic[label]=dict(roi=roi.tolist(),raw_roi_candidates=len(near),objectness_pass=int((obj[near]>.1).sum()),max_objectness=float(obj[near].max()),max_class_score=float(probs.max()))
   diagnostics.append(diagnostic);log('DETECT',group,f['frame_id'],len(ds),'window',len(diagnostic['window']),'door',len(diagnostic['door']))
  save(er/'detections/run.json',dict(status='success',model='wedetect',results=results));save(er/'detections/diagnostic.json',diagnostics)
  state['groups'][group]=dict(frames=6,raw_proposals=50400,final_candidates=sum(x['count'] for x in results));save(OUT/'detector_runtime.json',state)
 hook.remove();state['status']='success';save(OUT/'detector_runtime.json',state)
if __name__=='__main__':
 job=owned_compute_job();assert os.getloadavg()[0]<8
 state=dict(status='running',job=job,started=time.time(),scope='study1 shot1 and shot3 original854 versus resized852, WeDetect only')
 save(OUT/'run.json',state)
 try:
  prepare();detect();state['status']='success'
 except BaseException as e:state.update(status='failed',error=repr(e));raise
 finally:state['ended']=time.time();save(OUT/'run.json',state)
