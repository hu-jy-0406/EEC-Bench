import os,sys,time,subprocess,json
from pathlib import Path
H=Path(__file__).resolve().parent;B=H.parents[1];case=sys.argv[1];out=H/case;os.environ['CASE_ROOT']=str(out);os.environ['OPENBLAS_NUM_THREADS']='2';os.environ['OMP_NUM_THREADS']='2';pygeom=B/'experiments/study_inconsistent_3/geocalib_boxer_20260913/venv/bin/python'
from motion_fusion import run,owned_compute_job
owned_compute_job()
# One shot at a time here; external stages may run in bounded parallel across cases.
start=time.time();records=[]
def stage(name,cmd):
 t=time.time()
 with (out/(name+'.log')).open('a') as f:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
 records.append(dict(stage=name,started=t,seconds=time.time()-t,returncode=r.returncode));(out/'cpu_runtime.json').write_text(json.dumps(dict(started=start,seconds=time.time()-start,stages=records),indent=2))
 if r.returncode:raise SystemExit(r.returncode)
 print(case,name,'complete',flush=True)
for sid in ['shot1','shot3']:
 if not (out/'selected'/f'{sid}_scene.json').exists():run(case,sid)
stage('match',[sys.executable,str(H/'evaluate.py'),case,'match'])
stage('lift',[str(pygeom),str(H/'prepare_correspondences.py'),'--method','roma'])
stage('registration',[str(pygeom),str(H/'register.py'),'--method','roma'])
stage('identity_review',[sys.executable,str(H/'evaluate.py'),case,'review_identity'])
stage('presence',[sys.executable,str(H/'evaluate.py'),case,'presence'])
stage('spatial',[sys.executable,str(H/'evaluate.py'),case,'spatial'])
print(case,'COMPLETE',flush=True)
