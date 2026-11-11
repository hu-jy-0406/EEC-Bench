"""Run hard Z-up registration; otherwise the same frozen-input pilot protocol."""
import argparse,hashlib,json,os,sys,time
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
import gravity_box_registration as reg
from run_isolated_shot_static_3d import owned_compute_job

def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def native(x):
    if isinstance(x,np.ndarray):return x.tolist()
    if isinstance(x,np.generic):return x.item()
    if isinstance(x,dict):return {k:native(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [native(v) for v in x]
    return x
def save(p,x):p.write_text(json.dumps(native(x),ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def record_fit(fit,a,b,baseline):
    result={k:v for k,v in fit.items() if k!='model'}
    result['transform']=reg.model_record(fit['model'])
    result['metrics']=reg.diagnostics(a,b,fit['model'],baseline)
    return result

def main(args):
    job=owned_compute_job();assert os.getloadavg()[0]<8
    args.out.mkdir(parents=True,exist_ok=False)
    sources=[args.source/n for n in ['graph_a.json','graph_b.json','matching.json']]
    hashes={str(p.resolve()):sha(p) for p in sources}
    graphs=[read(p) for p in sources[:2]];matching=read(sources[2])
    assert all(g['coordinate_system']['z_axis']=='up' for g in graphs), 'Requires Z-up inputs'
    inventories=[{e['entity_id']:e for e in g['entities']} for g in graphs]
    groups=[g for g in matching['groups'] if g['identity']=='matched']
    assert all(len(g['a_ids'])==len(g['b_ids'])==1 for g in groups)
    selected=[[inventories[i][g[key][0]] for g in groups] for i,key in enumerate(['a_ids','b_ids'])]
    assert all(e['motion_status']=='static' and e['geometry'] is not None for side in selected for e in side)
    a,b=[np.array([reg.corners(e['geometry']) for e in side]) for side in selected]
    for side,boxes in zip(selected,[a,b]):
        for entity,box in zip(side,boxes):assert np.allclose(box,entity['geometry']['corners_world'],atol=1e-6)
    baseline=reg.scene_baseline(b)
    state=dict(status='running',job=job,started=time.time(),source_hashes=hashes,matched_entities=len(a),
               unmatched_groups=[g['group_id'] for g in matching['groups'] if g['identity']!='matched'],
               normalization='median pairwise target entity-center distance',baseline=baseline,
               rotation_constraint='R_times_up_equals_up',primary_delta=.05,per_entity_weight='equal before group Huber weighting',
               geometry_frozen=True,identities_frozen=True,new_model_calls=0)
    save(args.out/'run.json',state)
    center=reg.weighted_similarity(a.mean(1),b.mean(1))
    fits={'box_least_squares':reg.fit_boxes(a,b,delta=None),'box_huber':reg.fit_boxes(a,b,delta=.05)}
    robust=fits['box_huber']['model']
    results={'identity':dict(transform=reg.model_record(reg.identity()),metrics=reg.diagnostics(a,b,reg.identity(),baseline)),
             'center_least_squares':dict(transform=reg.model_record(center),metrics=reg.diagnostics(a,b,center,baseline))}
    results.update({k:record_fit(v,a,b,baseline) for k,v in fits.items()})
    save(args.out/'fits.json',results)
    print('FIT',json.dumps({k:v['metrics']['normalized_corner_rmse'] for k,v in results.items()}),flush=True)
    loo=[];models=[]
    for i,g in enumerate(groups):
        keep=np.arange(len(a))!=i
        fit=reg.fit_boxes(a[keep],b[keep],delta=.05,baseline=baseline,starts=4)
        model=fit['model'];models.append(model)
        error=reg.box_residuals(a[i:i+1],b[i:i+1],model)[0][0]
        center_error=np.linalg.norm(reg.transform(a[i].mean(0),model)-b[i].mean(0))
        difference=reg.transform(a.mean(1),model)-reg.transform(a.mean(1),robust)
        loo.append(dict(group_id=g['group_id'],name=selected[0][i]['name'],a_id=g['a_ids'][0],b_id=g['b_ids'][0],
                        fit_excludes_tested_entity=True,transform=reg.model_record(model),
                        heldout_corner_rmse=error,heldout_center_error=center_error,
                        heldout_normalized_corner_rmse=error/baseline,
                        full_fit_weight=fits['box_huber']['weights'][i],
                        other_center_prediction_shift_max=np.linalg.norm(difference[keep],axis=1).max()/baseline,
                        raw=results['identity']['metrics']['per_entity_corner_rmse'][i],
                        fitted=results['box_huber']['metrics']['per_entity_corner_rmse'][i]))
    save(args.out/'leave_one_out.json',loo)
    print('LOO',len(loo),'median',np.median([r['heldout_normalized_corner_rmse'] for r in loo]),flush=True)
    sensitivity={}
    for delta in [.025,.05,.1]:
        fit=fits['box_huber'] if delta==.05 else reg.fit_boxes(a,b,delta=delta)
        sensitivity[str(delta)]=record_fit(fit,a,b,baseline)
    reverse=reg.fit_boxes(b,a,delta=.05,baseline=baseline/robust[0])
    roundtrip=reg.transform(reg.transform(a,robust),reverse['model'])
    sensitivity['reverse_roundtrip_max_corner_error_normalized']=float(np.linalg.norm(roundtrip-a,axis=-1).max()/baseline)
    save(args.out/'sensitivity.json',sensitivity)
    # A declared diagnostic intervention: move exactly one matched small object.
    # It is never merged into real results or interpreted as observed video truth.
    idx=next((i for i,e in enumerate(selected[0]) if 'mug' in e['name'].lower()),0)
    corrupt=b.copy();offset=np.array([.5*baseline,0.,0.]);corrupt[idx]+=offset
    stress={}
    for label,delta in [('box_least_squares',None),('box_huber',.05)]:
        fit=reg.fit_boxes(a,corrupt,delta=delta,baseline=baseline)
        keep=np.arange(len(a))!=idx
        drift=reg.transform(a.mean(1)[keep],fit['model'])-reg.transform(a.mean(1)[keep],fits[label]['model'])
        stress[label]=dict(transform=reg.model_record(fit['model']),
                          moved_entity_normalized_residual=float(reg.box_residuals(a,corrupt,fit['model'])[0][idx]/baseline),
                          other_entities_mean_prediction_drift_normalized=float(np.linalg.norm(drift,axis=1).mean()/baseline))
    save(args.out/'synthetic_movement.json',dict(group_id=groups[idx]['group_id'],name=selected[0][idx]['name'],
         injected_translation=offset,normalized_translation=.5,synthetic_only=True,results=stress))
    singular=np.linalg.svd((b.mean(1)-b.mean((0,1)))/baseline,compute_uv=False)
    summary=dict(methods={k:v['metrics'] for k,v in results.items()},robust_transform=reg.model_record(robust),
        matched_entities=len(groups),unmatched_groups=state['unmatched_groups'],baseline=baseline,
        loo_corner_rmse=float(np.sqrt(np.mean([r['heldout_corner_rmse']**2 for r in loo]))),
        loo_corner_median=float(np.median([r['heldout_corner_rmse'] for r in loo])),
        loo_normalized_corner_median=float(np.median([r['heldout_normalized_corner_rmse'] for r in loo])),
        loo_scale_range=[min(m[0] for m in models),max(m[0] for m in models)],
        loo_rotation_deviation_max_deg=float(max(np.linalg.norm(Rotation.from_matrix(m[1]@robust[1].T).as_rotvec())*180/np.pi for m in models)),
        loo_other_prediction_shift_max=max(r['other_center_prediction_shift_max'] for r in loo),
        normalized_target_center_singular_values=singular,
        optimizer_starts=fits['box_huber']['starts_refined'],
        start_solution_spread=fits['box_huber']['start_solution_prediction_spread'],
        limitation='Hard gravity direction assumption; numerical graph registration only; fit errors mix reconstruction and real changes. No physical consistency verdict or calibrated confidence.')
    save(args.out/'summary.json',summary)
    save(args.out/'box_inputs.json',dict(groups=groups,names=[e['name'] for e in selected[0]],a=a,b=b))
    assert all(sha(p)==v for p,v in hashes.items())
    state.update(status='success',ended=time.time(),source_hashes_unchanged=True)
    save(args.out/'run.json',state)
    print('COMPLETE',json.dumps(native(summary),ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    main(p.parse_args())
