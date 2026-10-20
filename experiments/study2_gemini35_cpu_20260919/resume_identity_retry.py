"""Retain the incomplete identity response, retry once unchanged, then continue."""
import json,os,shutil,subprocess,time,traceback
from pathlib import Path
import resume_two_cpu as runner
R,B,C=runner.R,runner.B,runner.C
read,save,sha=runner.read,runner.save,runner.sha

def main():
 job=runner.owned_compute_job();assert job=='191764'
 os.sched_setaffinity(0,runner.GROUPS[0])
 state=read(C/'pipeline_runtime.json');assert state['status']=='failed' and state['stages'][-1]['stage']=='aligned_identity_review'
 save(R/'runtime_before_identity_retry.json',state)
 failed=C/'calls/identity_review';archive=C/'calls/identity_review_attempt1';assert not archive.exists();failed.rename(archive)
 status=read(archive/'status.json');status.update(transport_status=status['status'],status='failed',semantic_validation='incomplete_initial_group_reviews_4_of_29');save(archive/'status.json',status)
 shutil.copy2(C/'flow1_stage_review_identity.json',archive/'semantic_stage_status.json');shutil.copy2(C/'aligned_identity_review.log',archive/'semantic_validation.log')
 previous=state['stages'].pop();state.update(status='running',model_retry=dict(stage='identity_review',attempts=2,reason='Original response reviewed only4of29 initial groups',request_must_be_byte_identical=True));state.pop('error',None);state.pop('finished',None);state.pop('seconds',None)
 env=os.environ.copy();env.update(ROCR_VISIBLE_DEVICES='-1',HIP_VISIBLE_DEVICES='-1',CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',OPENBLAS_NUM_THREADS='1',CASE_ROOT=str(C),PYTHONPATH=str(B/'experiments/shot_scene_boxes_goal_20260916/deps'))
 for key,name in [('MPLCONFIGDIR','matplotlib'),('XDG_CACHE_HOME','cache'),('YOLO_CONFIG_DIR','yolo')]:env[key]=str(C/'runtime_cache'/name)
 jobs=[dict(stage='aligned_identity_review',command=[runner.CPU,str(R/'retry_identity_stage.py')])]+[j for j in read(C/'plan.json') if j['stage'] in ['presence','spatial']]
 provenance=read(C/'provenance.json')
 for source in [Path(__file__),R/'retry_identity_stage.py']:
  provenance['source_hashes'][str(source)]=sha(source);dest=C/'code_snapshot'/source.relative_to(B);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
 save(C/'provenance.json',provenance);save(C/'pipeline_runtime.json',state)
 try:
  for spec in jobs:
   start=previous['started'] if spec['stage']=='aligned_identity_review' else time.time()
   record=dict(spec,started=start,status='running');state['stages'].append(record);save(C/'pipeline_runtime.json',state);print('START',spec['stage'],flush=True)
   runner.monitor([spec['command']],env,[C/(spec['stage']+'.log')]);record.update(status='success',seconds=time.time()-start,returncode=0);save(C/'pipeline_runtime.json',state);print('END',spec['stage'],record['seconds'],flush=True)
  state['status']='success'
 except BaseException as exc:
  state.update(status='failed',error=repr(exc));state['stages'][-1].update(status='failed',seconds=time.time()-state['stages'][-1]['started']);traceback.print_exc();raise
 finally:
  state.update(finished=time.time(),seconds=time.time()-state['started']);save(C/'pipeline_runtime.json',state);runner.summarize(C,state)
 if state['status']=='success':subprocess.run([runner.CPU,str(R/'report.py')],env=env,check=True)

if __name__=='__main__':main()
