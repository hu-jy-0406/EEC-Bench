"""Revalidate the corrected anchor-field adapter; reuse unchanged binary/within stages."""
import os,sys,shutil,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from validate_downstream import command,CPU,GEOM
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from run_gs_temporal_stage import Stage,read,save,prepare_pair
from run_isolated_shot_static_3d import owned_compute_job
BASE=B/'experiments/temporal_v2_study234_revised_20260920'

def one(name):
    src=R/name;case=R/'production_replay'/name;case.mkdir(parents=True,exist_ok=False)
    for pattern in ['narrative.json','alignment_method.json','runtime_profile.json','inputs/*.json','selected/*.json','expected_motion/*.json']:
        for p in src.glob(pattern):
            dest=case/p.relative_to(src);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    for folder in ['pi3x','within']:(case/folder).symlink_to((src/folder).resolve(),target_is_directory=True)
    save(case/'reuse_provenance.json',dict(unchanged_classification_and_within_source=str(src),
         correction='Remove unintended every-frame geometric-stability veto from binary anchor adapter; restore original visual/usable-geometry criteria.',
         fresh_stages=['initial_identity','lift','FPS32','identity_review','boundary']))
    state=dict(status='running');start=time.time();save(case/'downstream_status.json',state)
    try:
        prepare_pair(case,'pair_000',['shot1','shot3']);pair=case/'pairs/pair_000'
        env=dict(os.environ,CASE_ROOT=str(pair),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
        command(pair,'initial_identity',[CPU,str(B/'scripts/run_gs_flow1_stage.py'),str(pair),'match','--runtime-profile','temporal_binary_v1'],env)
        print(name,'corrected matching',flush=True)
        (pair/'registration').mkdir(exist_ok=True)
        (pair/'registration/roma').symlink_to((BASE/name/'pairs/pair_000/registration/roma').resolve(),target_is_directory=True)
        command(pair,'lift',[GEOM,str(B/'experiments/study2_full_fresh_20260918/prepare_correspondences.py'),'--method','roma'],env)
        command(pair,'registration_fit',[GEOM,str(B/'scripts/register_gs_3d.py'),'--method','roma','--sampling','fps','--sample-count','32'],env)
        print(name,'corrected registration',flush=True)
        command(pair,'identity_review',[CPU,str(B/'scripts/run_gs_flow1_stage.py'),str(pair),'review_identity','--runtime-profile','temporal_binary_v1'],env)
        stage=Stage(pair,'temporal_binary_v1');stage.runtime['temporal_parallel_local_spatial']=False
        stage.boundary();state['status']='success';print(name,'corrected boundary',flush=True)
    except BaseException as e:
        state.update(status='failed',error=repr(e));print(name,repr(e),flush=True)
    finally:
        state['seconds']=time.time()-start;save(case/'downstream_status.json',state)
    return state

if __name__=='__main__':
    owned_compute_job()
    # Original Study2/3 may still be completing. One corrective stream keeps the
    # combined limit at three; launch the other two only when those are done.
    with ThreadPoolExecutor(max_workers=3) as pool:
        pending=[pool.submit(one,'study4')]
        while any(read(R/n/'downstream_status.json')['status']=='running' for n in ('study2','study3')):
            time.sleep(10)
        pending += [pool.submit(one,n) for n in ('study2','study3')]
        save(R/'corrected_summary.json',[f.result() for f in pending])
