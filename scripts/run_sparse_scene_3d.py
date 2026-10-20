#!/usr/bin/env python3
"""Two independent sparse-3D proposals and deterministic projection diagnostics."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import shutil
import socket
import time
import run_wedetect_shot_entities as io
import run_partial_scene_comparison as calls
from sparse_scene_3d import VERSION,RAW_SCHEMA,validate,audit_geometry


def run(args):
    job=io.safe_compute()
    if os.getloadavg()[0]>max(8,(os.cpu_count() or 1)*.5):raise RuntimeError('Compute node busy')
    src=io.read(args.source_run/'run.json');assert src['status']=='success'
    args.out.mkdir(parents=True,exist_ok=False)
    snapshot=args.out/'source_snapshot';snapshot.mkdir()
    graphs=[io.read(args.source_run/('graph_'+s)/'graph.json') for s in src['shots']]
    for g in graphs:io.dump(snapshot/('graph_'+g['shot_id']+'.json'),g)
    for n in ('manifest.json','alignment.json','policy.json','comparison.json','run.json'):
        shutil.copy2(args.source_run/n,snapshot/n)
    io.dump(args.out/'source_hashes.json',{p.name:io.sha(p) for p in snapshot.iterdir()})
    code=args.out/'code_snapshot';code.mkdir()
    files=[Path(__file__),Path(__file__).with_name('sparse_scene_3d.py'),Path(calls.__file__),Path(io.__file__),
           Path(__file__).with_name('partial_scene_contract.py'),calls.PROMPTS/'sparse_scene_3d_v0.3.txt']
    for p in files:shutil.copy2(p,code/p.name)
    io.dump(args.out/'code_hashes.json',{p.name:io.sha(p) for p in files});io.dump(args.out/'output.schema.json',RAW_SCHEMA)
    images=io.read(snapshot/'manifest.json')['images']
    for f in images:assert io.sha(f['path'])==f['sha256']
    io.dump(args.out/'manifest.json',dict(images=images))
    state=dict(status='running',started=time.time(),protocol_version=VERSION,source_run=str(args.source_run),
        shots=src['shots'],host=socket.gethostname(),allocation=job,model=args.model,reasoning=args.reasoning,
        dense_reconstruction=False)
    io.dump(args.out/'run.json',state);args.disabled_skills=io.disabled_skills_config()
    try:
        def extract(g):
            sid=g['shot_id'];imgs=[f for f in images if f['shot_id']==sid]
            payload={k:g[k] for k in ('shot_id','entities','frames','entity_scopes')}
            payload['images']=[dict(attachment_index=i+1,frame_id=f['frame_id']) for i,f in enumerate(imgs)]
            raw=calls.call('scene_'+sid,'sparse_scene_3d_v0.3.txt',payload,imgs,RAW_SCHEMA,args)
            validate(raw,payload);quality=audit_geometry(raw,payload)
            io.dump(args.out/('scene_'+sid)/'geometry_audit.json',quality)
            io.dump(args.out/('scene_'+sid)/'scene.json',dict(protocol_version=VERSION,proposal=raw,
                frozen_observations=payload['entities'],frames=payload['frames'],source_hash=io.sha(snapshot/('graph_'+sid+'.json'))))
            return quality
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(extract,g) for g in graphs];quality=[f.result() for f in futures]
        state.update(status='success',geometry_summary=[q['summary'] for q in quality])
    except BaseException as exc:
        state.update(status='failed',error=type(exc).__name__+': '+str(exc));raise
    finally:
        state.update(ended=time.time(),seconds=time.time()-state['started'])
        state['calls']=[dict(stage=p.parent.name,**io.read(p)) for p in sorted(args.out.glob('*/status.json'))]
        io.dump(args.out/'run.json',state)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source-run',required=True,type=Path);p.add_argument('--out',required=True,type=Path)
    p.add_argument('--model',default='gpt-6-astra');p.add_argument('--reasoning',default='medium');p.add_argument('--codex-bin',default='codex');p.add_argument('--timeout',default=1800,type=int)
    a=p.parse_args();a.source_run=a.source_run.resolve();a.out=a.out.resolve();run(a)
