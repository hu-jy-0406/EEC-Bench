import sys,json,time,hashlib,shutil,unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parent;B=ROOT.parents[1];sys.path.insert(0,str(B/'scripts'));sys.path.insert(0,str(B/'tests'))
from run_gs_temporal_stage import Stage,read,save
from gs_temporal_core import boundary_proposals
from run_isolated_shot_static_3d import owned_compute_job
owned_compute_job()
modules=['test_gs_temporal','test_gs_registration_3d','test_gs_registration_variants','test_gs_integrated','test_gs_codex_registration']
suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(m) for m in modules)
with (ROOT/'tests.log').open('w') as stream:result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
save(ROOT/'tests.json',dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),success=result.wasSuccessful()))
if not result.wasSuccessful():raise RuntimeError('Regression tests failed; see tests.log')
source=B/'experiments/study3_concise_mtd_fps32_20260919/run';case=ROOT/'replay';case.mkdir(exist_ok=False)
paths=[source/'narrative.json',source/'matching.json',source/'registration/roma_geometry/registration.json']
for sid in ('shot1','shot3'):paths += [source/'inputs'/f'{sid}.json',source/'selected'/f'{sid}_scene.json']
hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
for p in paths:
    if p.parent.name=='selected':continue
    dest=case/p.relative_to(source);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
(case/'pi3x').mkdir()
for sid in ('shot1','shot3'):(case/'pi3x'/sid).symlink_to(source/'pi3x'/sid,target_is_directory=True)
save(case/'replay_provenance.json',dict(scope='fresh expected-motion and temporal/boundary judgments on frozen prior detection, geometry, identity and FPS32 registration; shot2 not in this component replay',source=str(source),hashes=hashes))
started=time.time();status=dict(status='running',stages=[],source=str(source))
def timed(stage,sid=None):
    t=time.time();s=Stage(case,'safe_spatial_medium');getattr(s,stage)(sid) if sid else getattr(s,stage)()
    return dict(stage=stage,shot_id=sid,seconds=time.time()-t)
try:
    # Each call remains a fresh single-shot context. Two bounded API workers, no GPU.
    with ThreadPoolExecutor(max_workers=2) as pool:
        status['stages']+=list(pool.map(lambda sid:timed('expectation',sid),('shot1','shot3')))
    save(ROOT/'replay_status.json',status)
    with ThreadPoolExecutor(max_workers=2) as pool:
        status['stages']+=list(pool.map(lambda sid:timed('within',sid),('shot1','shot3')))
    save(ROOT/'replay_status.json',status)
    status['stages'].append(timed('boundary'))
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())
    status['status']='success'
except BaseException as exc:
    status.update(status='failed',error=repr(exc));raise
finally:
    status['seconds']=time.time()-started;save(ROOT/'replay_status.json',status)
print(json.dumps(status),flush=True)
