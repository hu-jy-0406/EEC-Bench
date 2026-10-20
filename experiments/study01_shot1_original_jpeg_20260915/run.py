"""Two independent shot pipelines, exact original JPEG inputs and common runtime."""
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
GROUPS=['study0','study1']
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
 provenance=[]
 for group in GROUPS:
  source=BASE/'experiments/study01_gs_v12_20260915'/group/'entities/manifest.json'
  shot=next(s for s in read(source)['shots'] if s['shot_id']=='shot1')
  for f in shot['frames']:
   assert Path(f['path']).suffix=='.jpg' and io.sha(f['path'])==f['sha256']
  save(OUT/group/'entities/manifest.json',dict(shots=[shot]))
  provenance.append(dict(group=group,source_manifest=str(source),source_manifest_sha256=io.sha(source),image_policy='Direct original JPEG paths; no copying, resizing, re-encoding or new frame extraction',frames=shot['frames']))
 save(OUT/'inputs.json',provenance)
 log('PREPARED_ORIGINAL_JPEGS',GROUPS)
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
   ds=det.predict(im);scores,boxes,embeds=captured.pop('data');d=er/'detections/shot1'/f"frame_{f['frame_id']:06d}";d.mkdir(parents=True,exist_ok=False)
   np.savez_compressed(d/'raw_forward.npz',scores=scores,boxes_letterbox=boxes,embeds=embeds)
   save(d/'detections.json',dict(shot='shot1',frame_id=f['frame_id'],sha256=f['sha256'],image_size=[w,h],detections=ds))
   results.append(dict(shot='shot1',frame_id=f['frame_id'],count=len(ds)))
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
def cluster_group(group):
 er=OUT/group/'entities';shots=read(er/'manifest.json')['shots'];ds=io.load_detections(er/'detections',shots)
 args=SimpleNamespace(model='gpt-6-astra',reasoning='medium',codex_bin='/vast/users/guangyi.chen/.local/bin/codex',timeout=1800,shot_workers=1,prepare_only=False)
 state=dict(status='running',model=args.model,reasoning=args.reasoning);save(er/'run.json',state)
 io.review_shots(shots,ds,args,er,state);state['status']='success';save(er/'run.json',state);log('CLUSTER_DONE',group)
def geometry(group):
 old=module('case_geometry_adapter',BASE/'experiments/study01_gs_v12_20260915/run_cases.py');old.OUT=OUT
 old.geometry(group,OUT/group/'entities')
def static_group(group):
 cmd=[str(PY),str(SCRIPTS/'run_isolated_shot_static_3d.py'),'--source',str(OUT/group/'geometry/boxer_scene_graph.json'),'--shot','shot1','--out',str(OUT/group/'static'),'--model','gpt-6-astra','--reasoning','medium','--codex-bin','/vast/users/guangyi.chen/.local/bin/codex']
 with (OUT/group/'static.log').open('w') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
 log('STATIC_DONE',group,read(OUT/group/'static/run.json')['counts'])
def child(py,stage,group=None):
 cmd=[str(py),str(Path(__file__).resolve()),stage]+(['--group',group] if group else [])
 with (OUT/f'{stage}_{group or "all"}.log').open('w') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
def all_stages():
 state=dict(status='running',job=owned_compute_job(),groups=GROUPS,started=time.time());save(OUT/'run.json',state)
 try:
  child(DETPY,'prepare');child(DETPY,'detect')
  with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(cluster_group,GROUPS))
  for g in GROUPS:child(GEOPY,'geometry',g)
  with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(static_group,GROUPS))
  state['status']='success'
 except BaseException as e:state.update(status='failed',error=repr(e));raise
 finally:state['ended']=time.time();save(OUT/'run.json',state)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['all','prepare','detect','cluster','geometry','static']);p.add_argument('--group',choices=GROUPS);a=p.parse_args()
 owned_compute_job();assert os.getloadavg()[0]<8
 if a.stage=='all':all_stages()
 elif a.stage=='prepare':prepare()
 elif a.stage=='detect':detect()
 elif a.stage=='cluster':cluster_group(a.group)
 elif a.stage=='geometry':geometry(a.group)
 else:static_group(a.group)
