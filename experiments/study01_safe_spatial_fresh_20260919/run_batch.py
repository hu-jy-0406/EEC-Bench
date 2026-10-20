#!/usr/bin/env python3
"""Run both fresh cases on one allocated GPU; fail if prepared code/inputs drift."""
import hashlib,json,os,re,socket,subprocess,sys,time,traceback
from pathlib import Path
R=Path(__file__).resolve().parent
B=R.parents[1]
CPU='/vast/users/guangyi.chen/anaconda3/bin/python'
sys.path.insert(0,str(B/'scripts'))

def read(p):return json.loads(Path(p).read_text())
def save(p,x):
    p=Path(p);tmp=p.with_suffix(p.suffix+'.tmp')
    tmp.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n');tmp.replace(p)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def preflight():
    for name,digest in read(R/'source_hashes.json').items():
        if sha(name)!=digest:raise RuntimeError('Prepared source changed: '+name)
    for rows in read(R/'input_audit.json').values():
        for f in rows:
            if sha(f['path'])!=f['sha256']:raise RuntimeError('Original JPEG changed: '+f['path'])
    from gs_runtime_profile import profile
    p=profile('safe_spatial_medium')
    assert p['model']==p['clustering_model']=='gpt-6-astra'
    assert p['reasoning']==p['clustering_reasoning']=='medium'
    assert p['efficient_call_stages']==['observe_shot1','observe_shot3','verify_relations']
    from run_wedetect_shot_entities import load_manifest
    for c in ['study0','study1']:
        shots=load_manifest(R/'manifests'/f'{c}.json')
        assert [s['shot_id'] for s in shots]==['shot1','shot3']
        assert all(len(s['frames'])==6 for s in shots)
    print('Preflight: source hashes, original JPEG hashes, manifests and medium profile passed.',flush=True)

def render(state):
    lines=['# Study0 / Study1 fresh evaluation','',
      'Profile: `safe_spatial_medium`; GPT-6 Astra medium; independent Shot1–Shot3 cases.',
      'Original JPEGs: Study0 852×480, Study1 854×480; no inference reuse.',
      '',f"Status: **{state['status']}**.",'',
      'Times below exclude Slurm queue time. Cached input is already included in input tokens.',
      '', '| Case | Status | Presence | Spatial | Runtime (s) | Tokens |',
      '|---|---|---:|---:|---:|---:|']
    summaries={}
    for c in ['study0','study1']:
        f=R/c/'summary.json'
        if not f.exists():
            lines.append(f"| {c} | {state.get('cases',{}).get(c,{}).get('status','pending')} | — | — | — | — |")
            continue
        s=read(f);summaries[c]=s
        def score(k):
            v=s.get(k,{}).get('score');return '—' if v is None else f'{v:.2f}'
        lines.append(f"| {c} | {s['status']} | {score('presence')} | {score('spatial')} | {s.get('elapsed_seconds',0):.2f} | {s['total_tokens']} |")
    for c,s in summaries.items():
        lines+=['',f'## {c}','', '| Stage | Status | Seconds | Tokens |','|---|---|---:|---:|']
        for st in s['stages']:
            lines.append(f"| {st['stage']} | {st['status']} | {st.get('seconds',0):.2f} | {st.get('total_tokens',0)} |")
        lines+=['',f"Full judgments and penalty reasons: [{c}/presence.json]({R/c/'presence.json'}), [{c}/spatial.json]({R/c/'spatial.json'}).",'',f"Per-call usage: [{c}/calls.csv]({R/c/'calls.csv'})."]
    if state.get('error'):lines+=['','Error: `'+state['error']+'`']
    (R/'REPORT.md').write_text('\n'.join(lines)+'\n')
    save(R/'comparison.json',dict(batch=state,results=summaries))

def main():
    if '--check-only' in sys.argv:
        preflight();return 0
    state=dict(status='starting',started=time.time(),host=socket.gethostname(),job_id=os.environ.get('SLURM_JOB_ID'),cases={})
    save(R/'batch_status.json',state)
    try:
        preflight()
        from run_isolated_shot_static_3d import owned_compute_job
        owned_compute_job()
        allocated=os.environ.get('SLURM_JOB_GPUS','')
        if not re.fullmatch(r'\d+',allocated):
            raise RuntimeError('Expected exactly one physical GPU in SLURM_JOB_GPUS, got '+repr(allocated))
        # A one-GPU Slurm cgroup may expose its global device as local card0.
        # Enumerate inside the allocation instead of treating SLURM_JOB_GPUS as an SMI ordinal.
        smi=subprocess.check_output(['rocm-smi','--showuse','--showmeminfo','vram','--showuniqueid'],text=True,stderr=subprocess.STDOUT)
        (R/'allocated_gpu.txt').write_text(smi)
        devices=dict((int(i),'GPU-'+u) for i,u in re.findall(r'GPU\[(\d+)\].*Unique ID:\s*(?:GPU-)?(?:0x)?([0-9a-fA-F]{16})\b',smi))
        if len(devices)==1:
            gpu,uuid=next(iter(devices.items()))
        elif int(allocated) in devices:
            gpu=int(allocated);uuid=devices[gpu]
        else:
            raise RuntimeError('Cannot resolve the single allocated GPU in the visible SMI inventory')
        state.update(status='running',slurm_global_gpu=int(allocated),rocm_device_index=gpu,gpu_uuid=uuid)
        save(R/'batch_status.json',state);render(state)
        guard=B/'experiments/study2_detection_only_fresh_20260918/guard_gpu.py'
        for c in ['study0','study1']:
            # Recheck sources and idle/resident state immediately before each independent case.
            preflight()
            with (R/'logs'/f'{c}_gpu_guard.log').open('w') as log:
                subprocess.run([CPU,str(guard),str(gpu),uuid,'/usr/bin/true'],stdout=log,stderr=subprocess.STDOUT,check=True)
            cmd=[CPU,str(B/'scripts/run_gs_integrated.py'),'--manifest',str(R/'manifests'/f'{c}.json'),'--narrative',str(R/'manifests'/f'{c}_narrative.json'),'--output',str(R/c),'--gpu',str(gpu),'--gpu-uuid',uuid,'--runtime-profile','safe_spatial_medium']
            record=dict(status='running',started=time.time(),command=cmd)
            state['cases'][c]=record;save(R/'batch_status.json',state);render(state)
            env=os.environ.copy();env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='4')
            with (R/'logs'/f'{c}_pipeline.log').open('w') as log:
                result=subprocess.run(cmd,cwd=B.parent,env=env,stdout=log,stderr=subprocess.STDOUT)
            record.update(status='success' if result.returncode==0 else 'failed',returncode=result.returncode,seconds=time.time()-record['started'])
            save(R/'batch_status.json',state);render(state)
        state['status']='success' if all(x['status']=='success' for x in state['cases'].values()) else 'failed'
    except BaseException as exc:
        state.update(status='failed',error=repr(exc));traceback.print_exc()
    finally:
        state.update(finished=time.time(),seconds=time.time()-state['started'])
        save(R/'batch_status.json',state);render(state)
    return 0 if state['status']=='success' else 1
if __name__=='__main__':raise SystemExit(main())
