import os,sys,subprocess,time,json
from pathlib import Path
H=Path(__file__).resolve().parent;B=H.parents[1];case,idx,uuid=sys.argv[1:];out=H/case;os.environ['CASE_ROOT']=str(out);os.environ['PYTHONPATH']=str(B/'experiments/shot_scene_boxes_goal_20260916/deps');t=time.time()
cache=out/'runtime_cache';cache.mkdir(exist_ok=True)
for key,sub in [('MIOPEN_USER_DB_PATH','miopen_db'),('MIOPEN_CUSTOM_CACHE_DIR','miopen_cache')]:
 d=cache/sub;d.mkdir(exist_ok=True);os.environ[key]=str(d)
cmd=[sys.executable,str(H/'guard_gpu.py'),idx,uuid,str(B/'experiments/study_inconsistent_3/geocalib_boxer_20260913/venv/bin/python'),str(H/'run_matching.py'),'--method','roma']
with (out/'matching_gpu.log').open('w') as f:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
(out/'matching_gpu_runtime.json').write_text(json.dumps(dict(started=t,seconds=time.time()-t,returncode=r.returncode),indent=2));raise SystemExit(r.returncode)
