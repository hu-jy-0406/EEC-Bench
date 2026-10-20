import os,json,time,hashlib,subprocess,sys,shutil,re,signal
from pathlib import Path
import cv2,psutil
ROOT=Path(__file__).resolve().parent;B=ROOT.parents[1];SRC=B/'experiments/study3-concise-mtd-local'
CPU='/vast/users/guangyi.chen/anaconda3/bin/python'
sys.path.insert(0,str(B/'scripts'))
from run_isolated_shot_static_3d import owned_compute_job

def save(p,x):
 p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 assert not (ROOT/'run').exists(),'No duplicate execution'
 start=time.time();job=owned_compute_job()
 smi=subprocess.check_output(['rocm-smi','--showuniqueid','--showuse','--showmeminfo','vram','--showpids','--showpidgpus'],text=True)
 (ROOT/'gpu_snapshot.txt').write_text(smi)
 pairs=re.findall(r'GPU\[(\d+)\].*Unique ID:\s*0x([0-9a-fA-F]+)',smi)
 assert len(pairs)==1,'Use one-GPU step'
 gpu=int(pairs[0][0]);uuid='GPU-'+pairs[0][1].lower().zfill(16)
 sources=json.loads((B/'experiments/alignment_full_four_20260919/source_hashes.json').read_text())
 for path in sources:
  p=Path(path);dest=ROOT/'code_snapshot'/p.relative_to(B);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
 save(ROOT/'source_hashes.json',{p:sha(Path(p)) for p in sources})
 prep=time.time();shots=[];videos=[]
 for n in [1,2,3]:
  p=SRC/f'shot_{n}/shot{n}';cap=cv2.VideoCapture(str(p));assert cap.isOpened()
  count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));fps=cap.get(cv2.CAP_PROP_FPS);width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH));height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
  indices=[round(i*(count-1)/5) for i in range(6)];frames=[]
  out=ROOT/'frames'/f'shot{n}';out.mkdir(parents=True,exist_ok=True)
  for i in indices:
   cap.set(cv2.CAP_PROP_POS_FRAMES,i);ok,im=cap.read();assert ok
   target=out/f'frame_{i:06d}.jpg';assert cv2.imwrite(str(target),im,[cv2.IMWRITE_JPEG_QUALITY,95])
   frames.append(dict(frame_id=i,path=str(target),timestamp_sec=i/fps,sha256=sha(target)))
  cap.release();shots.append(dict(shot_id=f'shot{n}',scene_id='garden' if n==2 else 'living_room',frames=frames))
  videos.append(dict(path=str(p),sha256=sha(p),frame_count=count,fps=fps,width=width,height=height,selected_frames=indices))
 save(ROOT/'manifest.json',dict(shots=shots))
 prompt_paths=[SRC/'global_prompt.md']+[SRC/f'shot_{n}/prompt.txt' for n in [1,2,3]]
 # Preserve only exact user-provided story prompts, never generation reviews or expected evaluator verdicts.
 facts=[dict(fact_id='global' if i==0 else f'shot{i}',text=p.read_text().strip()) for i,p in enumerate(prompt_paths)]
 save(ROOT/'narrative.json',dict(facts=facts))
 save(ROOT/'input_provenance.json',dict(videos=videos,prompts=[dict(path=str(p),sha256=sha(p)) for p in prompt_paths],frame_policy='six uniformly spaced decoded video frames including endpoints; original resolution; JPEG quality95; generation reference PNGs unused',preparation_seconds=time.time()-prep))
 guard=subprocess.run([CPU,str(B/'experiments/study2_detection_only_fresh_20260918/guard_gpu.py'),str(gpu),uuid,'/usr/bin/true'],capture_output=True,text=True)
 (ROOT/'gpu_preflight.txt').write_text(guard.stdout+guard.stderr);assert guard.returncode==0,guard.stdout+guard.stderr
 env=os.environ.copy()
 for k in ['ROCR_VISIBLE_DEVICES','HIP_VISIBLE_DEVICES','CUDA_VISIBLE_DEVICES']:env.pop(k,None)
 env.update(OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',TOKENIZERS_PARALLELISM='false')
 command=[CPU,str(B/'scripts/run_gs_integrated.py'),'--manifest',str(ROOT/'manifest.json'),'--narrative',str(ROOT/'narrative.json'),'--output',str(ROOT/'run'),'--gpu',str(gpu),'--gpu-uuid',uuid,'--runtime-profile','safe_spatial_medium','--alignment-method','roma_fps32','--stop-after','spatial']
 log=(ROOT/'pipeline.log').open('w');p=subprocess.Popen(command,env=env,cwd=B.parent,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 state=dict(status='running',started=start,allocation=job,pid=p.pid,command=command,gpu=gpu,uuid=uuid,rss_limit_gib=32)
 save(ROOT/'status.json',state)
 try:
  while p.poll() is None:
   try:
    processes=[psutil.Process(p.pid),*psutil.Process(p.pid).children(recursive=True)];rss=0
    for q in processes:
     try:rss+=q.memory_info().rss
     except psutil.Error:pass
   except psutil.Error:rss=0
   state.update(rss_gib=rss/1024**3,updated=time.time());save(ROOT/'status.json',state)
   if rss>32*1024**3:raise RuntimeError('Own process-tree RSS exceeded32GiB')
   time.sleep(5)
  state.update(status='success' if p.returncode==0 else 'failed',returncode=p.returncode)
 except BaseException as e:
  if p.poll() is None:os.killpg(p.pid,signal.SIGTERM)
  state.update(status='failed',error=repr(e));raise
 finally:
  log.close();state.update(finished=time.time(),seconds=time.time()-start);save(ROOT/'status.json',state)
 return p.returncode
if __name__=='__main__':raise SystemExit(main())
