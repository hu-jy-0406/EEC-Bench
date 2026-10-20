"""One clean full run. No stage output is imported from a previous experiment."""
import os,sys,json,time,subprocess,hashlib,shutil
from pathlib import Path
from PIL import Image
H=Path(__file__).resolve().parent;B=H.parents[1];O=H/'study2'
sys.path.insert(0,str(B/'scripts'))
from run_isolated_shot_static_3d import owned_compute_job
allocation=owned_compute_job();idx,uuid=sys.argv[1:]
CPU='/vast/users/guangyi.chen/anaconda3/bin/python';GEOM=str(B/'experiments/study_inconsistent_3/geocalib_boxer_20260913/venv/bin/python')
os.environ['CASE_ROOT']=str(O);os.environ['PYTHONPATH']=str(B/'experiments/shot_scene_boxes_goal_20260916/deps')
os.environ['OPENBLAS_NUM_THREADS']='2';os.environ['OMP_NUM_THREADS']='4'
for key,name in [('MIOPEN_USER_DB_PATH','miopen_db'),('MIOPEN_CUSTOM_CACHE_DIR','miopen_cache'),('MPLCONFIGDIR','matplotlib')]:
 d=O/'runtime_cache'/name;d.mkdir(parents=True,exist_ok=True);os.environ[key]=str(d)
def save(p,x):p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
def read(p):return json.loads(p.read_text())
assert not (O/'pipeline_runtime.json').exists(), 'Never implicitly resume a previous run'
records=[];started=time.time()
def stage(name,cmd):
 t=time.time();rec=dict(stage=name,command=cmd,started=t,status='running');records.append(rec)
 save(O/'pipeline_runtime.json',dict(started=started,allocation=allocation,status='running',stages=records))
 print('START',name,flush=True)
 with (O/(name+'.log')).open('w') as log:p=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
 rec.update(finished=time.time(),seconds=time.time()-t,returncode=p.returncode,status='success' if p.returncode==0 else 'failed')
 save(O/'pipeline_runtime.json',dict(started=started,finished=time.time(),seconds=time.time()-started,allocation=allocation,status='running' if p.returncode==0 else 'failed',stages=records))
 print('END',name,rec['status'],rec['seconds'],flush=True)
 if p.returncode:raise SystemExit(p.returncode)
def gpu(name,cmd):stage(name,[CPU,str(H/'guard_gpu.py'),idx,uuid]+cmd)
stage('detection_and_clustering',[CPU,str(B/'scripts/run_wedetect_shot_entities.py'),'--manifest',str(H/'raw_manifest.json'),'--output',str(O/'entities'),'--gpu',idx,'--model','gpt-6-astra','--reasoning','medium','--shot-workers','2','--codex-bin','/vast/users/guangyi.chen/.local/bin/codex','--timeout','1800'])
gpu('geocalib',[GEOM,str(H/'calibrate_fresh.py')])
for s in read(O/'entities/manifest.json')['shots']:
 sid=s['shot_id'];es=read(O/'entities/shots'/sid/'entities.json')['entities'];cal=read(O/'calibration_new/calibration'/f'{sid}.json')
 for f in s['frames']:assert hashlib.sha256(Path(f['path']).read_bytes()).hexdigest()==f['sha256']
 (O/'inputs').mkdir(exist_ok=True)
 save(O/'inputs'/f'{sid}.json',dict(shot_id=sid,frames=s['frames'],entities=es,image_sizes=[list(Image.open(f['path']).size) for f in s['frames']],calibration=cal))
for sid in ['shot1','shot3']:
 gpu('pi3x_'+sid,[GEOM,str(H/'geometry.py'),'--method','pi3x','--shot',sid])
 gpu('boxer_'+sid,[GEOM,str(H/'boxer.py'),'--method','pi3x','--shot',sid])
stage('motion_and_fusion',[CPU,str(H/'motion_fusion.py'),'study2'])
save(O/'pipeline_runtime.json',dict(started=started,finished=time.time(),seconds=time.time()-started,allocation=allocation,status='frontend_complete',stages=records))
print('FRESH FRONTEND COMPLETE',flush=True)
