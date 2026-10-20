"""Frozen-data alignment ablation; CPU-only, existing owned Slurm allocation."""
import argparse, copy, hashlib, itertools, json, os, sys, time
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'EECBench/scripts'))
import center_axis_registration as reg
import gravity_box_registration as corner_reg
from run_isolated_shot_static_3d import owned_compute_job

SOURCES={
    'study0': ROOT/'EECBench/experiments/study01_gs_v12_20260915/study0/gs_v11',
    'study1': ROOT/'EECBench/experiments/study01_gs_v12_20260915/study1/gs_v11',
    'study2': ROOT/'EECBench/experiments/study2_static_set_consistency_20260916/run01',
}

def read(p): return json.loads(Path(p).read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def native(x):
    if isinstance(x,np.ndarray): return x.tolist()
    if isinstance(x,np.generic): return x.item()
    if isinstance(x,dict): return {k:native(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)): return [native(v) for v in x]
    return x
def save(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(native(x),ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def inputs(case):
    root=SOURCES[case]
    graphs=[read(root/f'graph_{s}.json') for s in ['a','b']]
    match=read(root/'matching.json')
    groups=[g for g in match['groups'] if g['identity']=='matched']
    maps=[{e['entity_id']:e for e in g['entities']} for g in graphs]
    entities=[[m[g[side+'_ids'][0]] for g in groups] for m,side in zip(maps,['a','b'])]
    assert all(e['motion_status']=='static' for es in entities for e in es)
    y,x=[np.array([e['geometry']['center_world'] for e in es]) for es in entities]
    axes=np.array([[reg.long_axis(e['geometry']) for e in es] for es in entities])
    eligible=np.min(axes[:,:,1],axis=0)>=1.2
    deltas=reg.axis_angle(axes[0,:,0]-axes[1,:,0])
    return dict(graphs=graphs,groups=groups,entities=entities,x=x,y=y,deltas=deltas,
        eligible=eligible,axes=axes,anchor=np.array([g['anchor_eligible'] for g in groups]),
        baseline=reg.baseline(y),source_hashes={str(root/n):sha(root/n) for n in ['graph_a.json','graph_b.json','matching.json']})

def model_from_record(r): return r['scale'],np.array(r['rotation']),np.array(r['translation'])

def metric(data,model):
    x,y=data['x'],data['y']; L=data['baseline'];theta=np.arctan2(model[1][1,0],model[1][0,0])
    err=np.linalg.norm(reg.transform(x,model)-y,axis=1)/L
    angles=np.abs(np.degrees(reg.axis_angle(theta-data['deltas'][data['eligible']])))
    pairs=reg.pair_cosines(x,y,model)
    for p in pairs:
        p['groups']=[data['groups'][k]['group_id'] for k in [p['i'],p['j']]]
    vals=[p['cosine'] for p in pairs if p['cosine'] is not None]
    focal=next((p['cosine'] for p in pairs if set(p['groups'])=={'g02','g06'}),None)
    # focal is used for reporting Study2 only, never in fitting or selection.
    return dict(center_rmse=float(np.sqrt(np.mean(err**2))),center_median=float(np.median(err)),
        per_entity_center_error=err,axis_mae_deg=float(np.mean(angles)) if len(angles) else None,
        axis_errors_deg=angles,pair_cosine_mean=float(np.mean(vals)),pair_cosine_min=float(min(vals)),
        negative_pair_count=sum(v<0 for v in vals),focal_pair_cosine=focal,pairs=pairs)

def perform(data,spec,exclude=(),frame=None):
    x,y=data['x'].copy(),data['y'].copy()
    elig=data['eligible'].copy();deltas=data['deltas'].copy()
    if frame is not None:
        for i in range(len(x)):
            for side,points in [(0,y),(1,x)]:
                row=next((r for r in data['entities'][side][i]['frame_evidence']
                    if r['frame_id']==frame and r.get('selected') and r.get('visible') and r.get('geometry')),None)
                if row is None: continue
                points[i]=row['geometry']['center_world']
    keep=np.array([i not in exclude for i in range(len(x))])
    if spec.get('anchors'): keep &= data['anchor']
    if keep.sum()<2: raise ValueError('insufficient fitting identities')
    eligible=elig&keep;d=deltas[eligible]
    opts=dict(delta=spec.get('delta',.05),target_baseline=data['baseline'],starts=12)
    if spec.get('axis_first'):
        if not len(d): raise ValueError('no eligible axes')
        yaw=float(np.angle(np.mean(np.exp(2j*d)))/2)
        fs=[reg.fit(x[keep],y[keep],d,fixed_yaw=t,**opts) for t in [yaw,yaw+np.pi]]
        best=min(fs,key=lambda f:f['center_cost'])
        best['axial_branches']=[dict(transform=reg.record(f['model']),center_cost=f['center_cost'],scale_bound_hit=f['normalized_scale_bound_hit']) for f in fs]
    else:
        best=reg.fit(x[keep],y[keep],d,axis_weight=spec.get('weight',0),**opts)
    best['fit_groups']=[g['group_id'] for g,k in zip(data['groups'],keep) if k]
    best['axis_groups']=[g['group_id'] for g,k in zip(data['groups'],eligible) if k]
    return best

def main_fits():
    state=dict(status='running',allocation=owned_compute_job(),started=time.time(),direction='shot3_to_shot1',
        new_model_calls=0,gpu_calls=0,plan_sha256=sha(HERE/'PLAN.md'))
    assert os.getloadavg()[0]<8
    save(HERE/'run.json',state)
    specs={'center_ls':dict(delta=None),'center_huber':dict(delta=.05)}
    specs.update({f'joint_{w:g}':dict(weight=w) for w in [.001,.01,.03,.1,.3,1.]})
    specs.update({'axis_first':dict(axis_first=True),'anchors_axis_first':dict(axis_first=True,anchors=True),
                  'anchors_joint_0.03':dict(anchors=True,weight=.03),'anchors_joint_0.1':dict(anchors=True,weight=.1),
                  'anchors_center':dict(anchors=True)})
    save(HERE/'specs.json',specs)
    for case in SOURCES:
        data=inputs(case);out=HERE/case
        save(out/'inputs.json',data)
        rows={}
        for name,spec in specs.items():
            try:
                f=perform(data,spec);model=f.pop('model')
                rows[name]=dict(transform=reg.record(model),fit=f,metrics=metric(data,model),spec=spec)
                print(case,name,'yaw',round(rows[name]['transform']['yaw_deg'],3),'center',round(rows[name]['metrics']['center_rmse'],4),
                      'axis',rows[name]['metrics']['axis_mae_deg'],flush=True)
            except ValueError as ex: rows[name]=dict(error=str(ex),spec=spec)
        # Same historical gravity/corner algorithm, now fit directly Shot3 -> Shot1.
        a,b=[np.array([corner_reg.corners(e['geometry']) for e in es]) for es in data['entities'][::-1]]
        f=corner_reg.fit_boxes(a,b,delta=.05,baseline=data['baseline'])
        rows['corner_huber']=dict(transform=reg.record(f['model']),metrics=metric(data,f['model']),
            fit=dict(cost=f['cost'],weights=f['weights'],starts_refined=f['starts_refined']))
        save(out/'fits.json',rows)
        assert all(sha(p)==h for p,h in data['source_hashes'].items())
    state.update(status='fits_complete',ended=time.time(),source_hashes_unchanged=True)
    save(HERE/'run.json',state)

def validate():
    owned_compute_job();assert os.getloadavg()[0]<8
    specs=read(HERE/'specs.json')
    selected=['center_ls','center_huber','joint_0.01','joint_0.03','joint_0.1','joint_0.3','axis_first','anchors_joint_0.1','anchors_axis_first']
    for case in SOURCES:
        data=inputs(case);full=read(HERE/case/'fits.json');rows={}
        for name in selected:
            if 'error' in full[name]: continue
            m=model_from_record(full[name]['transform']);theta=np.arctan2(m[1][1,0],m[1][0,0])
            loo=[]
            for i,g in enumerate(data['groups']):
                try: f=perform(data,specs[name],exclude=[i]);model=f['model']
                except ValueError as ex:
                    loo.append(dict(group_id=g['group_id'],unavailable=str(ex)));continue
                err=np.linalg.norm(reg.transform(data['x'][i],model)-data['y'][i])/data['baseline']
                shift=np.max(np.linalg.norm(reg.transform(data['x'],model)-reg.transform(data['x'],m),axis=1))/data['baseline']
                dt=float(np.degrees(abs(reg.wrap(np.arctan2(model[1][1,0],model[1][0,0])-theta))))
                loo.append(dict(group_id=g['group_id'],center_error=err,yaw_change_deg=dt,prediction_shift=shift,transform=reg.record(model)))
            valid=[r for r in loo if 'unavailable' not in r]
            rows[name]=dict(loo=loo,valid_heldout=len(valid),total_heldout=len(loo),
                heldout_center_rmse=float(np.sqrt(np.mean([r['center_error']**2 for r in valid]))) if valid else None,
                max_loo_yaw_deg=max((r['yaw_change_deg'] for r in valid),default=None),
                max_loo_shift=max((r['prediction_shift'] for r in valid),default=None))
            print('VALID',case,name,rows[name]['heldout_center_rmse'],rows[name]['max_loo_yaw_deg'],flush=True)
        save(HERE/case/'validation.json',rows)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['fit','validate'],default='fit');a=p.parse_args()
    main_fits() if a.stage=='fit' else validate()
