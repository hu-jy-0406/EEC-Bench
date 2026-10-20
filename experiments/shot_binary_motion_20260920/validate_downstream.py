"""One CPU/API replay per case, reusing only original frontend and raw RoMa matches."""
import os, sys, subprocess, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from run_gs_temporal_stage import Stage, read, save, prepare_pair
from run_isolated_shot_static_3d import owned_compute_job
BASE=B/'experiments/temporal_v2_study234_revised_20260920'
CPU='/vast/users/guangyi.chen/anaconda3/bin/python'
GEOM=str(B/'experiments/study_inconsistent_3/geocalib_boxer_20260913/venv/bin/python')

def command(case, name, argv, env):
    start=time.time();state=dict(status='running',command=argv,started=start)
    path=case/(name+'_status.json');save(path,state)
    try:
        with (case/(name+'.log')).open('w') as log:
            subprocess.run(argv,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        state['status']='success'
    except BaseException as e:
        state.update(status='failed',error=repr(e));raise
    finally:
        state['seconds']=time.time()-start;save(path,state)

def one(name):
    case=R/name;state=dict(status='running',stages={});start=time.time()
    save(case/'downstream_status.json',state)
    try:
        assert read(case/'classification_status.json')['status']=='success'
        for sid in ['shot1','shot2','shot3']:
            t=time.time();Stage(case,'temporal_binary_v1').within(sid)
            state['stages']['within_'+sid]=time.time()-t;save(case/'downstream_status.json',state)
            print(name,'within',sid,flush=True)
        prepare_pair(case,'pair_000',['shot1','shot3']);pair=case/'pairs/pair_000'
        env=dict(os.environ,CASE_ROOT=str(pair),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
        command(pair,'initial_identity',[CPU,str(B/'scripts/run_gs_flow1_stage.py'),str(pair),'match','--runtime-profile','temporal_binary_v1'],env)
        print(name,'initial_identity',flush=True)
        # Refilter/lift against newly reviewed anchors, then run the original FPS32 objective.
        reg=pair/'registration';reg.mkdir(exist_ok=True)
        source=(BASE/name/'pairs/pair_000/registration/roma').resolve()
        (reg/'roma').symlink_to(source,target_is_directory=True)
        save(reg/'reuse_provenance.json',dict(scope='frozen original raw RoMa image correspondences only',source=str(source),
                                            frontend_reused=True,registration_reused=False,identity_reused=False))
        command(pair,'lift',[GEOM,str(B/'experiments/study2_full_fresh_20260918/prepare_correspondences.py'),'--method','roma'],env)
        command(pair,'registration_fit',[GEOM,str(B/'scripts/register_gs_3d.py'),'--method','roma','--sampling','fps','--sample-count','32'],env)
        command(pair,'identity_review',[CPU,str(B/'scripts/run_gs_flow1_stage.py'),str(pair),'review_identity','--runtime-profile','temporal_binary_v1'],env)
        print(name,'identity_review',flush=True)
        t=time.time();stage=Stage(pair,'temporal_binary_v1')
        # Limit this validation to three total API streams, one per study.
        # Production still parallelizes the two isolated local calls.
        stage.runtime['temporal_parallel_local_spatial']=False
        stage.boundary();state['stages']['boundary_serial_validation']=time.time()-t
        state['status']='success';print(name,'boundary success',flush=True)
    except BaseException as e:
        state.update(status='failed',error=repr(e));print(name,repr(e),flush=True)
    finally:
        state['seconds']=time.time()-start;save(case/'downstream_status.json',state)
    return state

if __name__=='__main__':
    owned_compute_job()
    with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(one,['study2','study3','study4']))
    save(R/'downstream_summary.json',results)
