"""Fresh isolated binary calls; frozen original detection/geometry, no GPU work."""
import sys, time, shutil, hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
R=Path(__file__).resolve().parent; B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from run_gs_temporal_stage import Stage,read,save
from gs_runtime_profile import profile
from run_isolated_shot_static_3d import owned_compute_job
BASE=B/'experiments/temporal_v2_study234_revised_20260920'

def one(name):
    src=BASE/name; dst=R/name;dst.mkdir(exist_ok=False)
    hashes={}
    for pattern in ['narrative.json','inputs/*.json','alignment_method.json']:
        for f in src.glob(pattern):
            t=dst/f.relative_to(src);t.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,t)
            hashes[str(f)]=hashlib.sha256(f.read_bytes()).hexdigest()
    (dst/'pi3x').symlink_to((src/'pi3x').resolve(),target_is_directory=True)
    for sid in ['shot1','shot2','shot3']:
        for f in [src/'pi3x'/sid/'complete.json', *(src/'pi3x'/sid/'boxer_depth').glob('frame_*.json')]:
            hashes[str(f)]=hashlib.sha256(f.read_bytes()).hexdigest()
    save(dst/'upstream_hashes.json',hashes);save(dst/'runtime_profile.json',profile('temporal_binary_v1'))
    state=dict(status='running',shots={});save(dst/'classification_status.json',state);start=time.time()
    try:
        for sid in ['shot1','shot2','shot3']:
            Stage(dst,'temporal_binary_v1').expectation(sid)
            before=read(src/'expected_motion'/f'{sid}.json');after=read(dst/'expected_motion'/f'{sid}.json')
            names={e['entity_id']:e['name'] for e in read(dst/'selected'/f'{sid}_scene.json')['entities']}
            rows=[]
            for a,b in zip(before['entities'],after['entities']):
                assert a['entity_id']==b['entity_id']
                old='moving' if any(r['expected']=='reasonable_motion' for r in a['intervals']) else 'static'
                rows.append(dict(entity_id=b['entity_id'],name=names[b['entity_id']],
                                 old_projected_binary=old,new=b['motion_status'],reason=b['reason'],
                                 basis=b['basis'],changed=old!=b['motion_status']))
            state['shots'][sid]=rows;save(dst/'classification_status.json',state)
            print(name,sid,'moving',sum(r['new']=='moving' for r in rows),'differences',sum(r['changed'] for r in rows),flush=True)
        state['status']='success'
    except BaseException as e:
        state.update(status='failed',error=repr(e));print(name,repr(e),flush=True)
    finally:
        state['seconds']=time.time()-start;save(dst/'classification_status.json',state)
    return state

if __name__=='__main__':
    owned_compute_job()
    with ThreadPoolExecutor(max_workers=3) as pool: results=list(pool.map(one,['study2','study3','study4']))
    save(R/'classification_summary.json',results)
