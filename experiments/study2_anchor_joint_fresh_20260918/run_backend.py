"""Continue this NEW run after its fresh per-shot front end; log every new stage."""
import json,os,sys,time,subprocess,shutil
from pathlib import Path
H=Path(__file__).resolve().parent;B=H.parents[1];O=H/'study2';sys.path.insert(0,str(B/'scripts'))
from run_isolated_shot_static_3d import owned_compute_job
allocation=owned_compute_job();idx,uuid=sys.argv[1:];CPU='/vast/users/guangyi.chen/anaconda3/bin/python';GEOM=str(B/'experiments/study_inconsistent_3/geocalib_boxer_20260913/venv/bin/python')
os.environ['CASE_ROOT']=str(O);os.environ['PYTHONPATH']=str(B/'experiments/shot_scene_boxes_goal_20260916/deps');os.environ['OPENBLAS_NUM_THREADS']='2';os.environ['OMP_NUM_THREADS']='4'
for key,sub in [('MIOPEN_USER_DB_PATH','miopen_db'),('MIOPEN_CUSTOM_CACHE_DIR','miopen_cache'),('MPLCONFIGDIR','matplotlib')]:
 d=O/'runtime_cache'/sub;d.mkdir(parents=True,exist_ok=True);os.environ[key]=str(d)
def read(p):return json.loads(p.read_text())
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
for _ in range(720):
 try:r=read(O/'pipeline_runtime.json')
 except (FileNotFoundError,json.JSONDecodeError):time.sleep(5);continue
 if r['status']=='frontend_complete':break
 if r['status']=='failed':raise SystemExit('Fresh frontend failed; do not start dependent processing')
 time.sleep(5)
else:raise SystemExit('Fresh frontend not complete after bounded wait')
assert not (O/'backend_started.json').exists();backend_start=time.time();save(O/'backend_started.json',dict(started=backend_start,frontend_finished=r['finished'],handoff_gap_seconds=backend_start-r['finished']))
started=r['started'];records=r['stages']
def stage(name,cmd):
 t=time.time();rec=dict(stage=name,command=cmd,started=t,status='running');records.append(rec);save(O/'pipeline_runtime.json',dict(started=started,status='running',allocation=allocation,stages=records))
 print('START',name,flush=True)
 with (O/(name+'.log')).open('w') as f:p=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
 rec.update(finished=time.time(),seconds=time.time()-t,status='success' if p.returncode==0 else 'failed',returncode=p.returncode)
 save(O/'pipeline_runtime.json',dict(started=started,finished=time.time(),seconds=time.time()-started,status='running' if p.returncode==0 else 'failed',allocation=allocation,stages=records));print('END',name,rec['status'],rec['seconds'],flush=True)
 if p.returncode:raise SystemExit(p.returncode)
stage('anchors_only',[CPU,str(H/'evaluate.py'),'study2','anchors'])
stage('roma_matches',[CPU,str(H/'guard_gpu.py'),idx,uuid,GEOM,str(H/'run_matching.py'),'--method','roma'])
stage('lift_correspondences',[GEOM,str(H/'prepare_correspondences.py'),'--method','roma'])
stage('registration',[GEOM,str(H/'register.py'),'--method','roma'])
initial_anchor_count=len(read(O/'anchors.json')['anchors'])
for round_id in range(1,initial_anchor_count+1):
 os.environ['JOINT_ROUND']=str(round_id);stage('joint_identity_presence' if round_id==1 else f'joint_identity_presence_round{round_id}',[CPU,str(H/'evaluate.py'),'study2','joint'])
 if not (O/'refit_request.json').exists():break
 q=read(O/'refit_request.json');assert q['refit_required'] and q['rejected_or_uncertain'];remaining=q['remaining_anchors']
 if len(remaining)<2:raise RuntimeError('Rejected contributing anchors leave insufficient registration support; no completed score is emitted')
 archive=O/'refit_archive'/f'round{round_id}';archive.mkdir(parents=True)
 for name in ['anchors.json','anchor_matching.json','refit_request.json']:shutil.copy2(O/name,archive/name)
 shutil.move(str(O/'registration/roma_geometry'),str(archive/'roma_geometry'))
 a=read(O/'anchors.json');a['anchors']=remaining;retained={x['anchor_id'] for x in remaining}
 for k in ['local_origin_anchor_id','local_reference_anchor_id']:
  if a[k] not in retained:a[k]=''
 save(O/'anchors.json',a)
 import evaluate
 evaluate.Eval('study2').write_anchor_matching(a)
 stage(f'lift_refit_round{round_id+1}',[GEOM,str(H/'prepare_correspondences.py'),'--method','roma'])
 stage(f'registration_refit_round{round_id+1}',[GEOM,str(H/'register.py'),'--method','roma'])
else:raise RuntimeError('No stable joint judgment after bounded anchor removal/refit')
stage('spatial',[CPU,str(H/'evaluate.py'),'study2','spatial'])
end=time.time();save(O/'pipeline_runtime.json',dict(started=started,finished=end,seconds=end-started,status='success',allocation=allocation,stages=records,frontend_backend_handoff_seconds=backend_start-r['finished']))
print('NEW PIPELINE COMPLETE',end-started,flush=True)
