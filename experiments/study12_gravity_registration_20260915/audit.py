"""Independent arithmetic checks and archived-anchor transform comparison."""
import json,os,shutil,sys
from pathlib import Path
BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
sys.path.insert(0,str(ROOT/'EECBench/scripts'))
import numpy as np
from scipy.optimize import minimize
from scipy.spatial.transform import Rotation
import gravity_box_registration as reg
import gs_consistency_geometry as old_geometry
from run_box_registration_pilot import read,save,sha
from report_box_registration_pilot import model,render
from run_isolated_shot_static_3d import owned_compute_job
PRIOR=BASE.parent/'study12_box_registration_20260915'

def up_error(m):return float(np.linalg.norm(m[1]@np.array([0.,0.,1.])-np.array([0.,0.,1.])))
def compare_models(a,first,second,L):
    shift=np.linalg.norm(reg.transform(a.mean(1),first)-reg.transform(a.mean(1),second),axis=-1)
    return dict(relative_scale=first[0]/second[0],rotation_difference_deg=float(Rotation.from_matrix(first[1]@second[1].T).magnitude()*180/np.pi),
                translation_difference=float(np.linalg.norm(first[2]-second[2])),
                center_prediction_difference_rmse_normalized=float(np.sqrt(np.mean(shift**2))/L),
                center_prediction_difference_max_normalized=float(shift.max()/L))

def audit_case(case):
    out=BASE/case;run=read(out/'run.json');inp=read(out/'box_inputs.json');fits=read(out/'fits.json');loo=read(out/'leave_one_out.json')
    a,b=np.array(inp['a']),np.array(inp['b']);L=run['baseline'];n=len(a)
    assert run['status']=='success' and run['rotation_constraint']=='R_times_up_equals_up'
    assert all(sha(p)==h for p,h in run['source_hashes'].items())
    assert inp==read(PRIOR/case/'box_inputs.json')
    free=read(PRIOR/case/'fits.json')['box_huber']
    for fit in fits.values():
        m=model(fit['transform'])
        assert m[0]>0 and np.allclose(m[1].T@m[1],np.eye(3),atol=1e-10) and np.linalg.det(m[1])>.999999 and up_error(m)<1e-12
        transformed=m[0]*a@m[1].T+m[2]
        direct=[min(np.sqrt(np.mean(np.sum((aa-bb[perm])**2,axis=1))) for perm in reg.PERMUTATIONS) for aa,bb in zip(transformed,b)]
        assert np.allclose(direct,fit['metrics']['per_entity_corner_rmse'],atol=1e-12)
        if 'objective_history' in fit:assert np.max(np.diff(fit['objective_history']),initial=0)<1e-10
    m=model(fits['box_huber']['transform']);yaw=np.arctan2(m[1][1,0],m[1][0,0])
    def objective(v):
        candidate=(m[0]*np.exp(v[0]),Rotation.from_euler('z',yaw+v[1]).as_matrix(),m[2]+v[2:]*L)
        return float(np.mean(reg.huber(reg.box_residuals(a,b,candidate)[0]/L,.05)))
    opt=minimize(objective,np.zeros(5),method='BFGS',options={'gtol':1e-8,'maxiter':300})
    gain=objective(np.zeros(5))-float(opt.fun)
    eps=1e-6;grad=np.array([(objective(v)-objective(-v))/(2*eps) for v in np.eye(5)*eps])
    assert gain<1e-9 and np.linalg.norm(grad)<1e-6,(gain,grad)
    # Additional starting headings independently probe other yaw basins.
    sweep=[]
    for angle in np.arange(-180,180,15):
        r=Rotation.from_euler('z',angle,degrees=True).as_matrix()
        initial=(m[0],r,b.mean((0,1))-m[0]*r@a.mean((0,1)))
        try:
            candidate=reg.refine(a,b,initial,L,delta=.05)
            sweep.append(dict(initial_yaw=float(angle),cost=candidate['cost'],transform=reg.model_record(candidate['model'])))
        except ValueError as error:sweep.append(dict(initial_yaw=float(angle),error=str(error)))
    successful=[r for r in sweep if 'cost' in r]
    sweep_gain=fits['box_huber']['cost']-min(r['cost'] for r in successful)
    save(out/'yaw_start_sweep.json',sweep)
    assert sweep_gain<1e-8,('better yaw start found',sweep_gain)
    for i,row in enumerate(loo):
        lm=model(row['transform']);assert up_error(lm)<1e-12
        e=reg.box_residuals(a[i:i+1],b[i:i+1],lm)[0][0]
        assert abs(e-row['heldout_corner_rmse'])<1e-10 and row['fit_excludes_tested_entity']
    idx=next(i for i,g in enumerate(inp['groups']) if g['group_id']==read(out/'synthetic_movement.json')['group_id'])
    keep=np.arange(n)!=idx;refit=reg.fit_boxes(a[keep],b[keep],delta=.05,baseline=L,starts=4)
    assert np.max(np.abs(reg.transform(a,refit['model'])-reg.transform(a,model(loo[idx]['transform']))))<1e-10
    sens=read(out/'sensitivity.json')
    for key in ['0.025','0.05','0.1']:assert up_error(model(sens[key]['transform']))<1e-12
    for row in read(out/'synthetic_movement.json')['results'].values():assert up_error(model(row['transform']))<1e-12
    # Archived identity/anchor stage, code-based fit and visual review contracts.
    source=Path(next(iter(run['source_hashes']))).parent
    old=read(source/'geometry_diagnostics.json');matching=read(source/'matching.json')
    graphs=[read(source/'graph_a.json'),read(source/'graph_b.json')]
    assert all(g['coordinate_system']['z_axis']=='up' for g in graphs)
    replay=old_geometry.diagnose(graphs,matching)
    assert replay==old
    old_records=[]
    for h in old['retained_hypotheses']:
        om=model(h);metrics=reg.diagnostics(a,b,om,L)
        nonanchors=np.array([g['group_id'] not in old['anchor_groups'] for g in inp['groups']])
        old_records.append(dict(transform=reg.model_record(om),gravity_constraint_imposed=False,
            actual_up_rotation_angle_deg=float(np.degrees(np.arccos(np.clip(om[1][2,2],-1,1)))),
            metrics_same_boxes_same_baseline=metrics,anchor_group_ids=h['fit_anchor_groups'],
            original_normalized_anchor_rmse=h['normalized_anchor_rmse'],original_anchor_baseline=old['target_anchor_baseline'],
            nonanchor_normalized_corner_rmse=float(np.sqrt(np.mean(np.array(metrics['per_entity_corner_rmse'])[nonanchors]**2))/L),
            gravity_fit_nonanchor_normalized_corner_rmse=float(np.sqrt(np.mean(np.array(fits['box_huber']['metrics']['per_entity_corner_rmse'])[nonanchors]**2))/L),
            gravity_vs_old=compare_models(a,m,om,L)))
        # Generic gravity model_record adds gravity metadata; correct archived record.
        old_records[-1]['transform'].pop('rotation_constraint');old_records[-1]['transform'].pop('up_rotation_angle_deg')
        old_records[-1]['transform'].pop('yaw_deg')
    schema=read(source/'matching/output.schema.json');wschema=read(source/'witness/output.schema.json')
    assert 'R_b_from_a' not in json.dumps(schema) and 'R_b_from_a' not in json.dumps(wschema)
    paths=[source/n for n in ['geometry_diagnostics.json','matching.json','matching/response.json','matching/output.schema.json','witness/output.schema.json','witness/response.json','verification/response.json']]
    historic=dict(source=str(source),hashes={str(p):sha(p) for p in paths},codex_output_explicit_transform=False,
                  codex_role='identity matching and anchor eligibility; local visual witness mapping',
                  numeric_solver='gs_consistency_geometry.fit_similarity via diagnose',
                  anchor_groups=old['anchor_groups'],hypotheses_generated=old['hypotheses_generated'],trusted=old['trusted'],
                  old_policy=old['policy'],retained_transforms_evaluated=old_records,
                  local_visual_has_no_global_matrix=True,
                  witness_mapping_bases={row['group_id']:row['mapping_basis'] for row in read(source/'witness/response.json')['checks']})
    save(out/'historical_anchor_comparison.json',historic)
    result=dict(status='pass',input_hashes_unchanged=True,same_boxes_and_matches_as_unconstrained=True,hard_gravity_satisfied=True,
                direct_corner_replays=list(fits),loo_replays=n,independent_heldout_refit=inp['groups'][idx]['group_id'],
                objective_monotonicity=True,gradient_norm=float(np.linalg.norm(grad)),independent_BFGS_gain=gain,
                independent_BFGS_success=bool(opt.success),independent_BFGS_message=str(opt.message),
                uniform_yaw_extra_starts=len(sweep),uniform_yaw_extra_successful=len(successful),uniform_yaw_extra_gain=sweep_gain,
                archived_anchor_diagnostics_exact_replay=True,global_optimality_certified=False,
                gravity_vs_free=compare_models(a,m,model(free['transform']),L),tests=read(BASE/'tests.json'))
    save(out/'audit.json',result)
    notice='硬重力约束：Z轴保持向上。仅为数值配准；几何误差不等于一致性分数。'
    render(out,a,b,m,inp,loo,L,case_title=case.title()+' 重力约束',notice=notice)
    print(case,json.dumps(result,ensure_ascii=False),flush=True)
    return historic

if __name__=='__main__':
    owned_compute_job();assert os.getloadavg()[0]<8
    for case in ['study1','study2']:audit_case(case)
    snapshot=BASE/'code_snapshot';snapshot.mkdir(exist_ok=True)
    paths=[ROOT/'EECBench/scripts'/n for n in ['gravity_box_registration.py','robust_box_registration.py','run_gravity_box_registration.py','run_box_registration_pilot.py','report_box_registration_pilot.py','gs_consistency_geometry.py']]+[ROOT/'EECBench/tests/test_gravity_box_registration.py',Path(__file__).resolve()]
    manifest=[]
    for p in paths:
        target=snapshot/p.name;shutil.copy2(p,target);manifest.append(dict(path=str(p),sha256=sha(p),snapshot=str(target)))
    save(BASE/'code_hashes.json',manifest)
