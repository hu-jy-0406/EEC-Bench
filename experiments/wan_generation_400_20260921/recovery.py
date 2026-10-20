#!/usr/bin/env python3
"""Finite campaign supervisor: bounded cache-error recovery and expired-job cleanup."""
import json
import os
from pathlib import Path
import subprocess
import time
import traceback
import campaign

ROOT=Path(__file__).resolve().parent

def job_state(job):
    p=subprocess.run(['scontrol','show','job','-o',str(job)],text=True,capture_output=True,timeout=15)
    if p.returncode:return 'UNKNOWN'
    fields=dict(x.split('=',1) for x in p.stdout.split() if '=' in x)
    return fields.get('JobState','UNKNOWN')

def main():
    recovered={};processes={};started=time.time()
    while not (ROOT/'STOP_RECOVERY').exists():
        try:
            states=[json.loads(p.read_text()) for p in (ROOT/'workers').glob('*.json')]
            jobs={str(d['job']):job_state(d['job']) for d in states}
            for d in states:
                name=d['worker'];job=str(d['job'])
                if jobs[job] in {'TIMEOUT','CANCELLED','COMPLETED','FAILED','NODE_FAIL','OUT_OF_MEMORY','PREEMPTED'}:
                    with campaign.queue_lock():
                        q=json.loads((ROOT/'queue.json').read_text());changed=False
                        for t in q['tasks']:
                            if t['status']=='running' and t.get('worker')==name:
                                t.update(status='pending',error='allocation_ended:'+jobs[job],ended=time.time());changed=True
                        if changed:campaign.write_json(ROOT/'queue.json',q)
                    continue
                if jobs[job]!='RUNNING' or d['state']!='failed':continue
                if 'miopenStatusInternalError' not in d.get('error',''):continue
                previous=recovered.get(name,{})
                if previous.get('source_started')==d['started'] or previous.get('count',0)>=2:continue
                if name in processes and processes[name].poll() is None:continue
                planpath=ROOT/'launches'/f'{d["node"]}.json'
                if not planpath.exists():continue
                plan=json.loads(planpath.read_text());w=next(w for w in plan['workers'] if w['worker']==name)
                # This is a recorded failed process; the GPU guard rechecks that
                # it actually exited and no other workload has occupied the card.
                history=ROOT/'worker_history';history.mkdir(exist_ok=True)
                campaign.write_json(history/f'{name}.{int(d["started"])}.json',d)
                with campaign.queue_lock():
                    q=json.loads((ROOT/'queue.json').read_text())
                    for task in q['tasks']:
                        if task['status']=='failed' and 'miopenStatusInternalError' in task.get('error',''):
                            task.update(status='pending',requeued_after_cache_fix=time.time())
                    campaign.write_json(ROOT/'queue.json',q)
                cmd=['srun','-u','--jobid='+job,'--overlap','-N1','-n1','-c64','--cpu-bind=none',
                    'env','TOKENIZERS_PARALLELISM=false',w['command'][0],str(ROOT/'lease_guard.py'),*w['command'][2:]]
                with (ROOT/'logs'/f'{name}.log').open('a') as log:
                    log.write('\nBOUNDED_CACHE_RECOVERY '+str(time.time())+'\n');log.flush()
                    clean_env={k:v for k,v in os.environ.items() if not k.startswith(('SLURM_','SRUN_'))}
                    proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,env=clean_env)
                processes[name]=proc
                recovered[name]=dict(source_started=d['started'],count=previous.get('count',0)+1,pid=proc.pid,time=time.time())
                print('RECOVER',name,proc.pid,flush=True)
            q=json.loads((ROOT/'queue.json').read_text())
            campaign.write_json(ROOT/'recovery_status.json',dict(started=started,heartbeat=time.time(),recovered=recovered,jobs=jobs))
            if all(t['status']=='done' for t in q['tasks']):
                for episode in sorted({t['episode_id'] for t in q['tasks']}):campaign.concat_episode(episode)
                campaign.write_json(ROOT/'complete.json',dict(completed=time.time(),episodes=400,shots=2000));return
        except Exception:print(traceback.format_exc(),flush=True)
        time.sleep(60)

if __name__=='__main__':main()
