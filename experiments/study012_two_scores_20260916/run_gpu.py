import os,sys,json,time,subprocess
from pathlib import Path
H=Path(__file__).resolve().parent;B=H.parents[1];case,idx,uuid=sys.argv[1:];out=H/case;os.environ['CASE_ROOT']=str(out);os.environ['PYTHONPATH']=str(B/'experiments/shot_scene_boxes_goal_20260916/deps')
cache=out/'runtime_cache';cache.mkdir(exist_ok=True)
for key,sub in [('MIOPEN_USER_DB_PATH','miopen_db'),('MIOPEN_CUSTOM_CACHE_DIR','miopen_cache')]:
 d=cache/sub;d.mkdir(exist_ok=True);os.environ[key]=str(d)
py=B/'experiments/study_inconsistent_3/geocalib_boxer_20260913/venv/bin/python';cpu='/vast/users/guangyi.chen/anaconda3/bin/python'
previous=json.loads((out/'gpu_runtime.json').read_text()) if (out/'gpu_runtime.json').exists() else {};t=previous.get('started',time.time());records=previous.get('stages',[])
for sid in ['shot1','shot3']:
 for script,done in [('geometry.py','complete.json'),('boxer.py','boxer_depth/inference_complete.json')]:
  if (out/'pi3x'/sid/done).exists():continue
  start=time.time()
  with (out/f'{sid}_{script}.log').open('a') as log:
   p=subprocess.run([cpu,str(H/'guard_gpu.py'),idx,uuid,str(py),str(H/script),'--method','pi3x','--shot',sid],stdout=log,stderr=subprocess.STDOUT)
  records.append(dict(shot=sid,script=script,started=start,seconds=time.time()-start,returncode=p.returncode));(out/'gpu_runtime.json').write_text(json.dumps(dict(started=t,seconds=time.time()-t,stages=records),indent=2))
  if p.returncode:raise SystemExit(p.returncode)
  print(case,sid,script,'done',records[-1]['seconds'],flush=True)
