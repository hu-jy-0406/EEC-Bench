"""Resume only this fresh run's pending stages; archive the initial failed attempt."""
import copy,json,os,shutil,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CASE=ROOT/'run'
sys.path.insert(0,str(ROOT.parents[2]/'EECBench/scripts'))
import run_gs_temporal as pipeline
read,save=pipeline.read,pipeline.save
initial=read(CASE/'pipeline_runtime.json');outer=read(ROOT/'execution.json')
assert initial['status']=='failed' and outer['status']=='failed'
failed=[s for s in initial['stages'] if s['status']=='failed']
assert len(failed)==1 and failed[0]['stage']=='prompt_binding'
retry=CASE/'prompt_binding_retry'
assert (retry/'results.json').is_file()
# Keep exact initial attempt files, including the rejected raw response and usage.
archive=ROOT/'initial_attempt';archive.mkdir(exist_ok=False)
for name in ['pipeline_runtime.json','summary.json','stages.csv','calls.csv']:
 shutil.copyfile(CASE/name,archive/name)
shutil.copyfile(ROOT/'execution.json',archive/'execution.json')
shutil.copyfile(CASE/'prompt_binding.log',archive/'prompt_binding.log')
shutil.copytree(CASE/'prompt_binding',archive/'prompt_binding')
# The original model request succeeded, but materialization rejected its witnesses.
shutil.rmtree(CASE/'prompt_binding')
retry.rename(CASE/'prompt_binding')
shutil.copytree(archive/'prompt_binding/calls/binding',CASE/'prompt_binding/calls/binding_attempt1')
status=read(CASE/'prompt_binding/calls/binding/status.json')
old=failed[0];replacement=copy.deepcopy(old)
retry_attempt=dict(stage='prompt_binding',status='success',started=status['started'],seconds=status['seconds'],returncode=0,
                   gpu=False,api_slots=1,measurement='recorded retry call; local postprocessing overhead excluded')
replacement.update(status='success',returncode=0,seconds=old['seconds']+status['seconds'],
                   attempts=[copy.deepcopy(old),retry_attempt],recovered=True,
                   timing_note='Sum of initial stage elapsed and retry call elapsed; excludes between-attempt gap and retry local postprocessing')
prior=[replacement if s['stage']=='prompt_binding' else s for s in initial['stages']]
done={s['stage'] for s in prior if s['status']=='success'}
jobs=read(CASE/'execution_plan.json');pending=[copy.deepcopy(j) for j in jobs if j['stage'] not in done]
for j in pending:j['depends']=[dep for dep in j['depends'] if dep not in done]
save(ROOT/'recovery_plan.json',dict(source_initial_runtime=str(archive/'pipeline_runtime.json'),
  completed_stages=sorted(done),pending_stages=pending,reason='Retry original binding under unchanged witness validation; no model or prompt changes'))
outer.update(status='running',recovery_started=time.time());save(ROOT/'execution.json',outer)
env=os.environ.copy();env.update(CASE_ROOT=str(CASE),PYTHONPATH=str(pipeline.B/'experiments/shot_scene_boxes_goal_20260916/deps'),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='4')
for key,name in [('MIOPEN_USER_DB_PATH','miopen_db'),('MIOPEN_CUSTOM_CACHE_DIR','miopen_cache'),('MPLCONFIGDIR','matplotlib')]:env[key]=str(CASE/'runtime_cache'/name)
try:
 resumed=pipeline.execute(CASE,pending,env,outer['allocation'],'full',schedule_name='parallel_v1')
 save(ROOT/'recovery_runtime.json',resumed)
 combined=copy.deepcopy(initial)
 combined.update(status='success',stages=prior+resumed['stages'],finished=time.time(),seconds=time.time()-initial['started'],
   recovery=dict(initial_attempt_archive=str(archive),failed_attempts=1,extra_model_calls=1,
                 prior_successful_stages_reused_only_from_this_fresh_run=True))
 combined.pop('error',None)
 save(CASE/'pipeline_runtime.json',combined);pipeline.summarize(CASE,combined)
 outer.update(status='success',returncode=0,recovered=True,failed_binding_attempts=1)
except BaseException as exc:
 outer.update(status='failed',recovery_error=repr(exc));raise
finally:
 outer.update(finished=time.time(),elapsed_seconds=time.time()-outer['started']);save(ROOT/'execution.json',outer)
