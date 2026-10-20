"""Resume unexecuted stages after a fail-closed GPU handoff check."""
import os,json,re,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent;B=ROOT.parents[1];sys.path.insert(0,str(B/'scripts'))
from run_gs_integrated import read,save,plan,execute,summarize,CPU
from run_isolated_shot_static_3d import owned_compute_job
case=ROOT/'study3_fps32';old=read(case/'pipeline_runtime.json');assert old['status']=='failed' and old['stages'][-1]['stage']=='boxer_shot3'
assert not (case/'pipeline_runtime_before_resume.json').exists()
save(case/'pipeline_runtime_before_resume.json',old)
(case/'boxer_shot3.log').rename(case/'boxer_shot3_preflight_attempt1.log')
job=owned_compute_job();uuid='GPU-f218ecc49371b0a5';smi=subprocess.check_output(['rocm-smi','--showuniqueid','--showuse','--showmeminfo','vram','--showpids','--showpidgpus'],text=True)
(case/'resume_gpu_check.txt').write_text(smi)
found=[int(i) for i,u in re.findall(r'GPU\[(\d+)\].*Unique ID:\s*0x([0-9a-fA-F]+)',smi) if int(u,16)==int(uuid[4:],16)];assert len(found)==1
idx=found[0];subprocess.run([CPU,str(B/'experiments/study2_detection_only_fresh_20260918/guard_gpu.py'),str(idx),uuid,'/usr/bin/true'],check=True)
done={s['stage'] for s in old['stages'] if s['status']=='success'}
jobs=[j for j in plan(case,idx,uuid,'spatial','safe_spatial_medium',read(case/'identity_scope.json'),'roma_fps32') if j['stage'] not in done]
env=os.environ.copy();env.update(CASE_ROOT=str(case),PYTHONPATH=str(B/'experiments/shot_scene_boxes_goal_20260916/deps'),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='4',MKL_NUM_THREADS='1')
for key,name in [('MIOPEN_USER_DB_PATH','miopen_db'),('MIOPEN_CUSTOM_CACHE_DIR','miopen_cache'),('MPLCONFIGDIR','matplotlib')]:env[key]=str(case/'runtime_cache'/name)
save(case/'resume_status.json',dict(status='running',started=time.time(),pid=os.getpid(),reason='GPU handoff guard blocked before boxer inference; same-run upstream retained',allocation=job,steps=[j['stage'] for j in jobs]))
try:execute(case,jobs,env,job,overlap_roma=True)
finally:
 resumed=read(case/'pipeline_runtime.json');save(case/'pipeline_runtime_resume_segment.json',resumed)
 combined=dict(resumed,started=old['started'],seconds=resumed['finished']-old['started'],stages=old['stages']+resumed['stages'],resume_reason='GPU release handoff preflight; no completed inference repeated',resume_segments=[dict(started=old['started'],finished=old['finished'],status=old['status']),dict(started=resumed['started'],finished=resumed['finished'],status=resumed['status'])])
 save(case/'pipeline_runtime.json',combined);summarize(case,combined);save(case/'resume_status.json',dict(status=resumed['status'],finished=time.time(),seconds_including_original_run=combined['seconds']))
 print('RESUME FINAL',combined['status'],flush=True)
