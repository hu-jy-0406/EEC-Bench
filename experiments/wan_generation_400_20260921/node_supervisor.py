#!/usr/bin/env python3
"""Bounded compute-node workers; no retries that bypass the idle GPU guard."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent
PY='/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python'
GUARD=ROOT.parent/'study2_detection_only_fresh_20260918/guard_gpu.py'

def main():
    p=argparse.ArgumentParser();p.add_argument('--cards',required=True);args=p.parse_args()
    validation=json.loads((ROOT/'streaming_validation.json').read_text())
    assert validation['exact_equal'] and validation['finite'],'Streaming validation is mandatory'
    subprocess.run([sys.executable,str(ROOT/'node_probe.py')],check=True,stdout=subprocess.DEVNULL)
    node=socket.gethostname()
    inv=json.loads((ROOT/'inventory'/f'{node}.json').read_text())
    selected=[]
    for idx in [int(x) for x in args.cards.split(',')]:
        card=next(c for c in inv['cards'] if c['card']==f'card{idx}')
        if card['util_max']>0 or card['vram_used_mib']>=95 or card['kfd_processes']:
            print('SKIP_NOT_IDLE',idx,card,flush=True);continue
        selected.append((idx,card['uuid']))
    stats=dict(line.split() for line in inv['memory']['memory.stat'].splitlines())
    cap=int(inv['memory']['memory.max'])
    # File-backed caches are reclaimable; anonymous RAM is not. Reserve 5 GiB
    # per worker plus 8 GiB shared/transient margin, without raising cgroup limits.
    needed=int(stats['anon'])+len(selected)*5*2**30+8*2**30
    assert needed<cap*.95,('Insufficient anonymous-memory headroom',needed,cap)
    allowed=sorted(os.sched_getaffinity(0))
    physical={}
    for cpu in allowed:
        topology=Path(f'/sys/devices/system/cpu/cpu{cpu}/topology')
        key=((topology/'physical_package_id').read_text().strip(),(topology/'core_id').read_text().strip())
        physical.setdefault(key,[]).append(cpu)
    choices=[]
    for key,cpus in physical.items():
        busy=max(inv['cpu_busy_percent'].get(str(c),100) for c in cpus)
        if busy<=20:choices.append((busy,min(cpus)))
    choices.sort()
    chosen=[c for _,c in choices]
    assert len(chosen)>=4*len(selected),('Insufficient low-utilization CPU cores',len(chosen),len(selected))
    processes=[];records=[]
    for n,(idx,uid) in enumerate(selected):
        cpus=chosen[n*4:n*4+4]
        name=f'node{node.rsplit("-",1)[-1]}_gpu{idx}'
        env=os.environ.copy();env['TOKENIZERS_PARALLELISM']='false'
        cmd=[PY,str(GUARD),str(idx),uid,'taskset','-c',','.join(map(str,cpus)),PY,'-u',str(ROOT/'campaign.py'),
            'worker','--worker',name,'--memory-mode','stream']
        log=(ROOT/'logs'/f'{name}.log').open('a')
        proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,env=env)
        processes.append((name,proc,log))
        records.append(dict(worker=name,pid=proc.pid,cpus=cpus,uuid=uid,physical_gpu=idx,command=cmd))
        # Guard/import/initial VAE are staggered; checkpoint loading has node lock.
        time.sleep(3)
    (ROOT/'launches').mkdir(exist_ok=True)
    (ROOT/'launches'/f'{node}.json').write_text(json.dumps(dict(node=node,job=inv['job_id'],
        started=time.time(),workers=records,anon_budget_bytes=needed),indent=2))
    print('WORKERS_STARTED',json.dumps(records),flush=True)
    while processes:
        remaining=[]
        for name,proc,log in processes:
            rc=proc.poll()
            if rc is None:remaining.append((name,proc,log));continue
            log.close();print('WORKER_EXIT',name,rc,flush=True)
        processes=remaining
        if processes:time.sleep(30)

if __name__=='__main__':main()
