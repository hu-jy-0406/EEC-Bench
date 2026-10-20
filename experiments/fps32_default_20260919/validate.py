import json,os,subprocess,sys,hashlib
from pathlib import Path
import numpy as np
B=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(B/'scripts'))
from register_gs_3d import fitting_rows
from run_gs_integrated import plan
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
command=next(j['command'] for j in plan('/tmp/check-fps32',0,'GPU-test') if j['stage']=='registration')
assert command[-4:]==['--sampling','fps','--sample-count','32']
small=np.zeros((10,19));small[:,7:13]=np.random.default_rng(1).normal(size=(10,6));small[:,13]=1
assert set(fitting_rows(small))==set(range(10))
try:fitting_rows(small[:2])
except ValueError:pass
else:raise AssertionError('underconstrained pool accepted')
results={}
for name,case in [('study2',B/'experiments/study2_integrated_full_fresh_20260919/study2'),('study3',B/'experiments/study3/run_cpu02')]:
 source=case/'registration/roma_geometry/correspondences.npz';historical=source.with_name('registration.json');before={str(p):sha(p) for p in [source,historical]}
 dest=OUT/name/'registration.json'
 proc=subprocess.run([sys.executable,str(B/'scripts/register_gs_3d.py'),'--method','roma','--case',str(case),'--output',str(dest)],check=True,capture_output=True,text=True)
 print(proc.stdout,flush=True)
 new=read(dest);old=read(B/'experiments/registration_methods_20260919'/name/'m1_fps_32/registration.json')
 assert new['sampling']['selected_rows']==old['selected_rows']
 f=new['fits']['all_structures'];np.testing.assert_allclose(f['parameters'],old['fit']['parameters'],rtol=0,atol=1e-10)
 assert f['fit_rows']==32 and f['points_removed']==0
 assert abs(f['selected_distance_3d']['sum']-f['objective_value'])<1e-9
 for p,h in before.items():assert sha(Path(p))==h
 results[name]=dict(selected_count=32,reproduces_experimental_transform=True,old_sources_unchanged=True,hashes=before)
checks=[]
for pat in ['test_gs_registration_3d.py','test_gs_registration_variants.py','test_gs_integrated.py']:
 p=subprocess.run([sys.executable,'-m','unittest','discover','-s',str(B/'tests'),'-p',pat],capture_output=True,text=True)
 checks.append(dict(pattern=pat,code=p.returncode,output=p.stdout+p.stderr));print(checks[-1],flush=True);assert p.returncode==0
files=[B/'scripts/register_gs_3d.py',B/'scripts/gs_registration_3d.py',B/'scripts/gs_registration_variants.py',B/'scripts/run_gs_integrated.py',B/'scripts/review_aligned_entity_identities.py',B/'configs/gs-consistency-two-scores.v1.json']
(OUT/'audit.json').write_text(json.dumps(dict(passed=True,cases=results,checks=checks,small_pool_and_insufficient_pool_checked=True,new_model_calls=0,source_hashes={str(p):sha(p) for p in files}),ensure_ascii=False,indent=2)+'\n')
