import copy, itertools, json, sys
from pathlib import Path
import numpy as np
from run_experiment import HERE,ROOT,inputs,read,save,sha,perform,metric,model_from_record,reg,owned_compute_job

def frame_data(data,fa,fb):
    out=copy.deepcopy(data);valid=np.ones(len(data['x']),bool)
    for i in range(len(valid)):
        for side,fid,points in [(0,fa,out['y']),(1,fb,out['x'])]:
            row=next((r for r in data['entities'][side][i]['frame_evidence'] if r['frame_id']==fid and
                      r.get('visible') and r.get('selected') and r.get('geometry')),None)
            if row is None:valid[i]=False;continue
            points[i]=row['geometry']['center_world']
            out['axes'][side,i]=reg.long_axis(row['geometry'])
    idx=np.flatnonzero(valid)
    for k in ['x','y','anchor']:out[k]=out[k][idx]
    out['axes']=out['axes'][:,idx]
    out['eligible']=np.min(out['axes'][:,:,1],axis=0)>=1.2
    out['deltas']=reg.axis_angle(out['axes'][0,:,0]-out['axes'][1,:,0])
    out['groups']=[out['groups'][i] for i in idx]
    out['entities']=[[es[i] for i in idx] for es in out['entities']]
    return out

def scene_transform(graph,desk,radiator):
    es={e['entity_id']:e for e in graph['entities']}
    o=np.array(es[desk]['geometry']['center_world']);d=np.array(es[radiator]['geometry']['center_world'])-o
    d[2]=0; L=np.linalg.norm(d);v=d/L;u=np.cross(v,[0,0,1]);R=np.array([u,v,[0,0,1.]])
    return 1/L,R,-R@o/L

def main():
    owned_compute_job()
    data=inputs('study2');full=read(HERE/'study2/fits.json');specs=read(HERE/'specs.json')
    # Gauge equivalence: same objective, still free s/yaw/t after establishing frames.
    f1=scene_transform(data['graphs'][0],'shot1/e5','shot1/e14')
    f3=scene_transform(data['graphs'][1],'shot3/e7','shot3/e18')
    x,y=reg.transform(data['x'],f3),reg.transform(data['y'],f1)
    dt=np.arctan2(f1[1][1,0],f1[1][0,0])-np.arctan2(f3[1][1,0],f3[1][0,0])
    gauge=[]
    for name in ['center_ls','center_huber','joint_0.01','joint_0.1','joint_1']:
        sp=specs[name];raw=model_from_record(full[name]['transform'])
        sf=reg.fit(x,y,data['deltas'][data['eligible']]+dt,axis_weight=sp.get('weight',0),delta=sp.get('delta',.05),target_baseline=data['baseline']*f1[0])
        back=reg.compose(reg.inverse(f1),reg.compose(sf['model'],f3))
        error=float(np.max(np.linalg.norm(reg.transform(data['x'],raw)-reg.transform(data['x'],back),axis=1))/data['baseline'])
        gauge.append(dict(method=name,back_transform=reg.record(back),max_normalized_prediction_difference=error,
                          objective_difference=sf['cost']-full[name]['fit']['cost']))
        assert error<1e-4
    save(HERE/'study2/coordinate_equivalence.json',gauge)
    # Scale from box diagonal ratios, independent of center alignment residuals.
    ratios=np.array([np.linalg.norm(es[0]['geometry']['size_xyz'])/np.linalg.norm(es[1]['geometry']['size_xyz'])
                     for es in zip(*data['entities'])])
    fixed_scale=float(np.median(ratios[data['anchor']]))
    extra={}
    for weight in [0,.01,.1,1.]:
        f=reg.fit(data['x'],data['y'],data['deltas'][data['eligible']],axis_weight=weight,
                  fixed_scale=fixed_scale,target_baseline=data['baseline'])
        m=f.pop('model');extra[f'fixed_box_scale_joint_{weight:g}']=dict(transform=reg.record(m),metrics=metric(data,m),fit=f)
    # Explicit frame-coincidence baseline and existing long-axis branch (not newly selected).
    old=read(ROOT/'EECBench/experiments/study2_scene_frames_20260915/summary.json')['equivalent_input_transform']
    oldm=(old['scale'],np.array(old['R_b_from_a']),np.array(old['translation_b']))
    m=reg.inverse(oldm);extra['scene_coincidence']=dict(transform=reg.record(m),metrics=metric(data,m))
    theta=float(np.angle(np.mean(np.exp(2j*data['deltas'][data['eligible']])))/2)
    for k,theta in enumerate([theta,theta+np.pi]):
        f=reg.fit(data['x'],data['y'],data['deltas'][data['eligible']],fixed_yaw=theta,fixed_scale=fixed_scale,target_baseline=data['baseline'])
        m=f.pop('model');extra[f'fixed_box_scale_axis_branch_{k}']=dict(transform=reg.record(m),metrics=metric(data,m),fit=f)
    save(HERE/'study2/scale_diagnostic.json',dict(fixed_scale=fixed_scale,box_scale_ratios=ratios,extra_fits=extra))
    # Actual frame-pair sensitivity, 6x6 combinations; missing observations excluded explicitly.
    sensitivity={}
    for name in ['center_huber','joint_0.1','axis_first']:
        rows=[]
        for fa,fb in itertools.product([0,24,48,72,96,120],repeat=2):
            fd=frame_data(data,fa,fb)
            fit=perform(fd,specs[name]);m=fit['model']
            rows.append(dict(frames=[fa,fb],fit_groups=fit['fit_groups'],axis_groups=fit['axis_groups'],
                             transform=reg.record(m),cost=fit['cost'],metrics_on_frozen_graphs=metric(data,m)))
        sensitivity[name]=rows
        print('FRAMES',name,'yaw range',min(r['transform']['yaw_deg'] for r in rows),max(r['transform']['yaw_deg'] for r in rows),flush=True)
    save(HERE/'study2/frame_sensitivity.json',sensitivity)
    # Baseline edge lengths/directions diagnose mutually incompatible center evidence.
    pairs=[]
    for i,j in itertools.combinations(range(len(data['x'])),2):
        dx,dy=data['x'][j]-data['x'][i],data['y'][j]-data['y'][i]
        yaw=float(np.degrees(reg.wrap(np.arctan2(dy[1],dy[0])-np.arctan2(dx[1],dx[0]))))
        pairs.append(dict(groups=[data['groups'][i]['group_id'],data['groups'][j]['group_id']],
                          horizontal_required_yaw=yaw,distance_scale=np.linalg.norm(dy)/np.linalg.norm(dx),
                          source_distance=np.linalg.norm(dx),target_distance=np.linalg.norm(dy),
                          both_anchors=bool(data['anchor'][i] and data['anchor'][j])))
    save(HERE/'study2/center_pair_requirements.json',pairs)
    # All boxes to actual Shot1 OpenCV coordinates for every main/extra candidate.
    r1=np.array(data['graphs'][0]['cameras'][0]['R_world_from_camera'])
    r3=np.array(data['graphs'][1]['cameras'][0]['R_world_from_camera'])
    exports={}
    for name,row in {**full,**extra}.items():
        if 'transform' not in row:continue
        s,r,t=model_from_record(row['transform'])
        rawcamera=(s,r1.T@r@r3,r1.T@t)
        boxes=[]
        for side,g in enumerate(data['graphs']):
            model=(1,r1.T,np.zeros(3)) if side==0 else (s,r1.T@r,r1.T@t)
            for e in g['entities']:
                geo=e['geometry'];c=reg.transform(geo['center_world'],model);corn=reg.transform(geo['corners_world'],model)
                boxes.append(dict(shot=g['shot_id'],id=e['entity_id'],name=e['name'],center=c,corners=corn,
                    size=np.array(geo['size_xyz'])*model[0],rotation=model[1]@np.array(geo['R_world_from_object'])))
                original_camera=np.asarray(geo['corners_world'])@(r1 if side==0 else r3)
                replay=original_camera if side==0 else reg.transform(original_camera,rawcamera)
                np.testing.assert_allclose(corn,replay,atol=1e-10)
        np.testing.assert_allclose(rawcamera[1]@(r3.T@[0,0,1]),r1.T@[0,0,1],atol=1e-10)
        assert len(boxes)==38
        exports[name]=dict(coordinate_system='Shot1 original OpenCV camera: X right, Y down, Z forward',
            source_to_target_camera_transform=dict(scale=rawcamera[0],rotation=rawcamera[1],translation=rawcamera[2]),
            physical_pose_accepted=False,boxes=boxes)
    save(HERE/'study2/all_boxes_in_shot1_camera.json',exports)
    save(HERE/'diagnostics_audit.json',dict(status='pass',coordinate_equivalence=gauge,all_box_count_per_method=38,
        exported_candidates=len(exports),camera_conversion_replayed=True,source_hashes_unchanged=all(sha(p)==h for p,h in data['source_hashes'].items())))

if __name__=='__main__': main()
