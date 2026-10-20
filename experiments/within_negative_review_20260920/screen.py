"""Fresh negative-only model calls with frozen current shot inputs."""
import json,sys,shutil,time,hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from run_gs_temporal_stage import Stage,read,save
from run_isolated_shot_static_3d import owned_compute_job
SRC=B/'experiments/shot_binary_motion_20260920'

def one(study):
    src=SRC/study;case=R/'screen'/study;case.mkdir(parents=True,exist_ok=False)
    hashes={}
    for pattern in ['narrative.json','inputs/*.json','selected/*.json','expected_motion/*.json']:
        for p in src.glob(pattern):
            out=case/p.relative_to(src);out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,out)
            hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    save(case/'reuse_provenance.json',dict(source=str(src),input_hashes=hashes,scope='fresh within review only; frozen frontend/motion'))
    state=dict(study=study,status='running',started=time.time());save(case/'status.json',state)
    try:
        for sid in ['shot1','shot2','shot3']:
            Stage(case,'temporal_spatial_v1').within(sid)
            print(study,sid,'done',flush=True)
        state['status']='success'
    except BaseException as e:state.update(status='failed',error=repr(e));print(study,repr(e),flush=True)
    finally:state['seconds']=time.time()-state['started'];save(case/'status.json',state)
    return state

if __name__=='__main__':
    owned_compute_job()
    with ThreadPoolExecutor(max_workers=3) as p:save(R/'screen_status.json',list(p.map(one,['study2','study3','study4'])))
