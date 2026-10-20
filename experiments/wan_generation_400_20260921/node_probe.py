#!/usr/bin/env python3
"""Read-only compute-side inventory; no GPU initialization."""
import csv
import json
import os
from pathlib import Path
import runpy
import socket
import subprocess
import sys
import time

def run(cmd):return subprocess.check_output(cmd,text=True)

def cpu():
    rows={}
    for line in Path('/proc/stat').read_text().splitlines():
        x=line.split()
        if x and x[0].startswith('cpu') and x[0]!='cpu':
            v=list(map(int,x[1:]));rows[int(x[0][3:])]=(sum(v[:8]),v[3]+v[4])
    return rows

def main():
    checker=runpy.run_path('/vast/users/guangyi.chen/causal_group/jinyuan.hu/check_guangyi_gpus.py')
    remote=checker['REMOTE_PROBE']
    r=subprocess.run([sys.executable,'-c',remote,'--samples','3','--interval','2','--user','guangyi.chen'],text=True,capture_output=True,check=True)
    data=json.loads(r.stdout.strip().splitlines()[-1])
    uids=list(csv.DictReader(run(['rocm-smi','--showuniqueid','--csv']).splitlines()))
    for card in data['cards']:
        row=next(u for u in uids if u['device']==card['card'])
        card['uuid']='GPU-'+format(int(row['Unique ID'],16),'016x')
    cg=Path('/sys/fs/cgroup')/Path('/proc/self/cgroup').read_text().strip().split(':')[-1].lstrip('/')
    job=next(p for p in [cg,*cg.parents] if p.name.startswith('job_'))
    data['job_cgroup']=str(job)
    data['memory']={k:(job/k).read_text().strip() for k in ['memory.max','memory.current','memory.stat','memory.events']}
    data['allowed_cpus']=sorted(os.sched_getaffinity(0))
    a=cpu();time.sleep(1);b=cpu()
    data['cpu_busy_percent']={str(c):round(100*(1-(b[c][1]-a[c][1])/max(1,b[c][0]-a[c][0])),1) for c in b}
    data['host_memory']=Path('/proc/meminfo').read_text().splitlines()[:3]
    data['processes']=run(['ps','-u','guangyi.chen','-o','pid,pcpu,rss,psr,comm','--sort=-pcpu']).splitlines()[:20]
    data['job_id']=os.environ.get('SLURM_JOB_ID')
    path=Path(__file__).resolve().parent/'inventory'/f'{socket.gethostname()}.json'
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data,indent=2))
    print(json.dumps(data))

if __name__=='__main__':main()
