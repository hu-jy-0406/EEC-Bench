import copy, io, json, unittest
import numpy as np
from run_experiment import *

owned_compute_job()
# New fixed-scale capability added after the first eight tests: run the final nine.
suite=unittest.defaultTestLoader.discover(str(ROOT/'EECBench/tests'),pattern='test_center_axis_registration.py')
stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
save(HERE/'tests.json',dict(passed=result.wasSuccessful(),tests=result.testsRun,output=stream.getvalue()))
assert result.wasSuccessful(),stream.getvalue()
data=inputs('study2');fits=read(HERE/'study2/fits.json');specs=read(HERE/'specs.json')
# More yaw seeds for the potentially multimodal real case; diagnostics, not a certificate.
checks=[]
for name in ['center_huber','joint_0.01','joint_0.1','joint_1']:
    sp=specs[name]
    f=reg.fit(data['x'],data['y'],data['deltas'][data['eligible']],axis_weight=sp.get('weight',0),
              delta=sp.get('delta',.05),target_baseline=data['baseline'],starts=72)
    improvement=fits[name]['fit']['cost']-f['cost']
    assert improvement<1e-9
    checks.append(dict(method=name,extra_starts=72,objective_improvement=improvement,transform=reg.record(f['model'])))
save(HERE/'study2/multistart_audit.json',checks)
# Sensitivity: predeclared robust thresholds and aspect eligibility.
rows=[]
for delta,aspect in itertools.product([.025,.05,.1],[1.1,1.2,1.5]):
    elig=np.min(data['axes'][:,:,1],axis=0)>=aspect
    f=reg.fit(data['x'],data['y'],data['deltas'][elig],axis_weight=.1,delta=delta,target_baseline=data['baseline'])
    rows.append(dict(delta=delta,aspect=aspect,axis_groups=[g['group_id'] for g,e in zip(data['groups'],elig) if e],
                     transform=reg.record(f['model']),metrics=metric(data,f['model'])))
save(HERE/'study2/parameter_sensitivity.json',rows)
# Endpoint-excluded fits: observe potential absorption of the tested pair by registration.
pair=[]
for name in ['center_huber','joint_0.01','joint_0.1','axis_first']:
    omit=[i for i,g in enumerate(data['groups']) if g['group_id'] in ['g02','g06']]
    f=perform(data,specs[name],exclude=omit)
    pair.append(dict(method=name,excluded=['g02','g06'],transform=reg.record(f['model']),metrics=metric(data,f['model'])))
save(HERE/'study2/focal_pair_exclusion.json',pair)
# Score diagnostics replay + source integrity; all 38 boxes are in each export.
for case in SOURCES:
    d=inputs(case)
    for name,row in read(HERE/case/'fits.json').items():
        if 'transform' not in row:continue
        m=model_from_record(row['transform']);now=metric(d,m)
        np.testing.assert_allclose(now['center_rmse'],row['metrics']['center_rmse'],atol=1e-12)
        np.testing.assert_allclose(now['pair_cosine_mean'],row['metrics']['pair_cosine_mean'],atol=1e-12)
        assert m[0]>0 and np.linalg.det(m[1])>.999999
    assert all(sha(p)==h for p,h in d['source_hashes'].items())
files=[ROOT/'EECBench/scripts/center_axis_registration.py',ROOT/'EECBench/tests/test_center_axis_registration.py']
files += [HERE/n for n in ['run_experiment.py','diagnostics.py','final_checks.py','PLAN.md']]
for p in files:
    dest=HERE/'code_snapshot'/p.name;dest.parent.mkdir(exist_ok=True);dest.write_bytes(p.read_bytes())
save(HERE/'code_hashes.json',{str(p):sha(p) for p in files})
save(HERE/'post_run_changes.json',dict(initial_validation_failure='Study0 has only two reference entities; leaving one reference out leaves an underdetermined fit. First validation driver raised instead of recording unavailable. Fixed accounting; no primary fit changed.',
    solver_changes_after_primary_fit=['added rejection of vertical-only unidentifiable inputs; no real inputs meet this condition',
                                    'added optional fixed scale for secondary diagnostic; default primary objective unchanged'],
    tests=9,model_retries=0,old_scores_changed=False))
save(HERE/'audit.json',dict(status='pass',tests=9,primary_fit_cases=3,primary_methods_per_case=14,
    heldout_total=sum(sum(v['total_heldout'] for v in read(HERE/c/'validation.json').values()) for c in SOURCES),
    frame_fits=108,real_case_yaw_extra_starts_checks=checks,score_diagnostics_replayed=True,source_hashes_unchanged=True,
    physical_registration_certified=False,global_optimum_certified=False))
print('FINAL CHECKS PASS',flush=True)
