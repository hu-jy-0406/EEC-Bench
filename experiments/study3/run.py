"""Fresh three-shot Study3 through all-entity aligned identity review."""
import copy,hashlib,json,os,re,shutil,socket,subprocess,sys,time,traceback
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from run_gs_integrated import read,save,sha,CPU,GEOM
VIDEO=B/'experiments/study2_white_lamp_shot3_20260917/white_lamp.mp4'
OLD=B/'experiments/study_inconsistent_3/wedetect_shot_entities_20260912'

def prepare_inputs():
 if (R/'manifest.json').exists():
  shots=read(R/'manifest.json')['shots']
  assert sha(VIDEO)==read(R/'input_provenance.json')['source_video_sha256']
  assert all(sha(f['path'])==f['sha256'] for shot in shots for f in shot['frames'])
  assert sha(R/'narrative.json')==sha(B/'experiments/study2_integrated_full_fresh_20260919/study2/narrative.json')
  return shots
 shots=copy.deepcopy(read(OLD/'input.json')['shots'][:2])
 for shot in shots:
  shot['scene_id']='study' if shot['shot_id']=='shot1' else 'hallway'
  for f in shot['frames']:
   f['path']=str((OLD/f['path']).resolve());assert sha(f['path'])==f['sha256']
 snippet='''import cv2,json,sys,hashlib
from pathlib import Path
cv2.setNumThreads(1)
video=Path(sys.argv[1]);dest=Path(sys.argv[2]);dest.mkdir(parents=True,exist_ok=False)
cap=cv2.VideoCapture(str(video));assert cap.isOpened()
n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));fps=cap.get(cv2.CAP_PROP_FPS);ids=[round((n-1)*i/5) for i in range(6)]
meta=dict(frame_count=n,fps=fps,width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),sample_frame_ids=ids);frames=[]
for i in range(n):
 ok,im=cap.read();assert ok
 if i in ids:
  p=dest/f'frame_{i:06d}.jpg';assert cv2.imwrite(str(p),im,[cv2.IMWRITE_JPEG_QUALITY,95])
  frames.append(dict(frame_id=i,path=str(p),timestamp_sec=i/fps,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
cap.release();assert len(frames)==6
print(json.dumps(dict(metadata=meta,frames=frames)))
'''
 sampled=json.loads(subprocess.check_output([GEOM,'-c',snippet,str(VIDEO),str(R/'frames/shot3')],text=True))
 shots.append(dict(shot_id='shot3',scene_id='study',frames=sampled['frames']))
 save(R/'manifest.json',dict(shots=shots));shutil.copy2(B/'experiments/study2_integrated_full_fresh_20260919/study2/narrative.json',R/'narrative.json')
 save(R/'input_provenance.json',dict(source_video=str(VIDEO),source_video_sha256=sha(VIDEO),sampling='six uniform decoded frame indices including endpoints, same OpenCV/JPEG95 protocol as Study2, original resolution',metadata=sampled['metadata'],unchanged_shots=['shot1','shot2'],normal_narrative_source='study2_integrated_full_fresh_20260919/study2/narrative.json',inference_reuse=False))
 return shots

def main():
 if '--prepare-only' in sys.argv:
  from run_isolated_shot_static_3d import owned_compute_job
  owned_compute_job();prepare_inputs();return 0
 state=dict(status='starting',started=time.time(),host=socket.gethostname(),job_id=os.environ.get('SLURM_JOB_ID'))
 save(R/'status.json',state)
 try:
  from run_isolated_shot_static_3d import owned_compute_job
  owned_compute_job()
  subprocess.run([CPU,'-m','unittest','discover','-s','tests','-p','test_gs_integrated.py','-v'],cwd=B,check=True)
  allocated=os.environ.get('SLURM_JOB_GPUS','');assert re.fullmatch(r'\d+',allocated)
  smi=subprocess.check_output(['rocm-smi','--showuse','--showmeminfo','vram','--showuniqueid','--showpids','--showpidgpus'],text=True,stderr=subprocess.STDOUT);(R/'gpu_preflight.txt').write_text(smi)
  devices={int(i):'GPU-'+u for i,u in re.findall(r'GPU\[(\d+)\].*Unique ID:\s*(?:GPU-)?(?:0x)?([0-9a-fA-F]{16})\b',smi)}
  if len(devices)==1:gpu,uuid=next(iter(devices.items()))
  else:gpu=int(allocated);uuid=devices[gpu]
  state.update(slurm_global_gpu=allocated,rocm_device_index=gpu,gpu_uuid=uuid);save(R/'status.json',state)
  subprocess.run([CPU,str(B/'experiments/study2_detection_only_fresh_20260918/guard_gpu.py'),str(gpu),uuid,'/usr/bin/true'],check=True)
  prepare_inputs()
  snap=R/'code_snapshot';snap.mkdir()
  sources=list((B/'scripts').glob('*.py'))+list((B/'prompts/gs_flow1').glob('*.txt'))+list((B/'skills/wedetect-shot-entities').glob('*'))+[B/'prompts/gs_aligned_identity_review_v1.txt',B/'configs/gs-consistency-two-scores.v1.json',B/'configs/gs-runtime-profiles.v1.json']
  hashes={}
  for p in sources:
   if not p.is_file():continue
   dst=snap/p.relative_to(B);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst);hashes[str(p)]=sha(p)
  save(R/'source_hashes.json',hashes)
  command=[CPU,str(B/'scripts/run_gs_integrated.py'),'--manifest',str(R/'manifest.json'),'--narrative',str(R/'narrative.json'),'--output',str(R/'run01'),'--gpu',str(gpu),'--gpu-uuid',uuid,'--runtime-profile','safe_spatial_medium','--stop-after','identity']
  state.update(status='running',command=command);save(R/'status.json',state)
  result=subprocess.run(command,cwd=B.parent);state.update(status='success' if result.returncode==0 else 'failed',returncode=result.returncode)
  assert all(sha(p)==h for p,h in hashes.items()),'Source changed during run'
 except BaseException as exc:state.update(status='failed',error=repr(exc));traceback.print_exc()
 finally:
  state.update(ended=time.time(),seconds=time.time()-state['started']);save(R/'status.json',state)
  reporting=subprocess.run([CPU,str(R/'report.py')])
  if reporting.returncode:
   state.update(status='failed',report_returncode=reporting.returncode,error='Post-run audit/report failed; preserve pipeline outputs for inspection');save(R/'status.json',state)
 return 0 if state['status']=='success' else 1
if __name__=='__main__':raise SystemExit(main())
