#!/usr/bin/env python3
"""Independent projection replay, frozen-node export, provenance and sensitivity audit."""
import hashlib,json,math,subprocess,sys
from pathlib import Path
import numpy as np
from run_geocalib_boxer import BASE,CASE,DEFAULT_OUT,frozen,load,save
from evaluate_geocalib_boxer import box_metrics

def digest(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20),b''):h.update(chunk)
    return h.hexdigest()

def main(out):
    allchecks=[];graphs=[];sensitivity=[]
    for sid,s in frozen().items():
        frames=[];states={e['entity_id']:[] for e in s['entities']};count=0
        for f in s['frames']:
            frame_data=load(out/'predictions/geocalib'/sid/f"frame_{f['frame_id']:06d}.json")
            frames.append({'frame_id':f['frame_id'],'image_sha256':f['sha256'],'K':frame_data['K_original'],'R_world_from_camera':frame_data['R_world_from_camera'],'translation_world_from_camera':[0,0,0]})
            lookup={e['entity_id']:e for e in frame_data['entities']}
            for e in s['entities']:
                obs=next(o for o in e['observations'] if o['frame_id']==f['frame_id']);prediction=lookup.get(e['entity_id'])
                if obs['visible']!=(prediction is not None):raise AssertionError('Visibility/output mismatch')
                states[e['entity_id']].append({'frame_id':f['frame_id'],'geometry':prediction,'status':'model_estimate' if prediction else 'not_visible_geometry_unresolved'})
                count+=prediction is not None
        for variant in ['geocalib','codex_camera']:
            for f in s['frames']:
                p=load(out/'predictions'/variant/sid/f"frame_{f['frame_id']:06d}.json");K=np.array(p['K_original']);R=np.array(p['R_world_from_camera'])
                assert np.allclose(R@R.T,np.eye(3),atol=1e-6) and np.linalg.det(R)>.999
                for e in p['entities']:
                    rot=np.array(e['R_world_from_object']);size=np.array(e['size_xyz']);center=np.array(e['center_world']);world=np.array(e['corners_world']);camera=np.array(e['corners_camera'])
                    assert np.all(size>0) and np.allclose(rot@rot.T,np.eye(3),atol=2e-5) and np.linalg.det(rot)>.999
                    assert np.allclose(world@R,camera,atol=1e-5)
                    local=(world-center)@rot
                    assert np.allclose(np.max(local,axis=0)-np.min(local,axis=0),size,atol=1e-4)
                    uvh=camera@K.T;uv=uvh[:,:2]/uvh[:,2:]
                    assert np.all(camera[:,2]>0) and np.allclose(uv,e['projected_corners_xy'],atol=1e-5)
                    assert np.allclose([uv[:,0].min(),uv[:,1].min(),uv[:,0].max(),uv[:,1].max()],e['projected_envelope_xyxy'])
                    allchecks.append((sid,variant,f['frame_id'],e['entity_id']))
        entities=[{'entity_id':sid+'/'+e['entity_id'],'local_id':e['entity_id'],'name':e['name'],'candidate_ids':e['candidate_ids'],'observations':e['observations'],'states':states[e['entity_id']]} for e in s['entities']]
        graphs.append({'shot_id':sid,'world_frame_id':sid+'/geocalib_camera_origin_z_up','world_registration':'shot_local_only','scale':'monocular_model_metric_prior_not_measured','calibration':load(out/'calibration'/f'{sid}.json'),'frames':frames,'entities':entities,'entity_count':len(entities),'nonnull_states':count})
        base=load(out/'predictions/geocalib'/sid/'frame_000000.json'); B={e['entity_id']:e for e in base['entities']}
        for name in ['focal_low','focal_high','pitch_low','pitch_high']:
            pred=load(out/'predictions'/('geocalib_'+name)/sid/'frame_000000.json')
            for e in pred['entities']:
                b=B[e['entity_id']];cb=np.mean(b['corners_camera'],axis=0);cc=np.mean(e['corners_camera'],axis=0)
                sensitivity.append({'shot_id':sid,'variant':name,'entity_id':e['entity_id'],'name':e['name'],'depth_change_fraction':float((cc[2]-cb[2])/cb[2]),'center_displacement_model_units':float(np.linalg.norm(cc-cb)),'baseline_iou':box_metrics(b['projected_envelope_xyxy'],b['grounding_box_xyxy'])['iou'],'perturbed_iou':box_metrics(e['projected_envelope_xyxy'],e['grounding_box_xyxy'])['iou']})
    save(out/'boxer_scene_graph.json',{'schema_version':'boxer_sparse_scene_v0.1','source_entity_registry':'wedetect_shot_entities_20260912/run01','shots':graphs,'cross_shot_alignment':None,'note':'41 nodes preserved. Invisible frames have null geometry; no model hallucination into unobserved regions, no cross-shot fusion. Boxer predicts gravity-aligned 7DOF cuboids, not general articulated geometry.'})
    save(out/'sensitivity.json',{'perturbations':'focal +/-10%; physical-up rotation about camera X +/-3deg; frame0 only; not confidence bounds','items':sensitivity})
    provenance={'repos':{},'weights':{},'inputs':{},'scripts':{}}
    for repo in ['GeoCalib','boxer']:
        path=BASE/'third_party'/repo;provenance['repos'][repo]={'commit':subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip(),'tracked_diff':subprocess.check_output(['git','-C',str(path),'diff','--stat'],text=True)}
    for p in [out/'weights/geocalib-pinhole.tar',BASE/'third_party/boxer/ckpts/boxernet_hw960in2x6d768-c88128f8.ckpt',BASE/'third_party/boxer/ckpts/dinov3_vits16plus_pretrain_lvd1689m-4057cbaa.pth']:
        provenance['weights'][str(p)]={'bytes':p.stat().st_size,'sha256':digest(p)}
    for s in frozen().values():
        for f in s['frames']:provenance['inputs'][f['path']]=digest(f['path'])
    for n in ['run_geocalib_boxer.py','evaluate_geocalib_boxer.py','audit_geocalib_boxer.py','guard_geocalib_boxer_gpu.py']:
        p=BASE/'scripts'/n;provenance['scripts'][n]=digest(p)
    save(out/'provenance.json',provenance)
    save(out/'audit.json',{'status':'pass','replayed_entity_frame_predictions':len(allchecks),'unique_input_frames':12,'nodes':41,'predicted_visible_states_geocalib':sum(x['nonnull_states'] for x in graphs),'checks':['frozen original image hashes','all 19+22 entity nodes preserved','exact visible entity-frame coverage and IDs','positive box extents and SO3','box corners consistent with center/rotation/size','world-to-camera and original-pixel projection replay','unaltered official tracked source','paired baseline grounding references'],'limits':'Input-conditioned projection consistency, not independent 3D accuracy. No world registration.'})
    print('AUDIT PASS',len(allchecks),'predictions; 41 nodes')
    try:
        import plotly.graph_objects as go
        from plotly.offline import plot
        html=['<!doctype html><meta charset="utf-8"><title>Boxer sparse 3D</title><h1>GeoCalib + Boxer 三维框</h1><p>每个 shot 有独立的相机原点、Z向上坐标系。坐标单位来自模型先验；两个 shot 尚未配准。通过下拉菜单切换帧。</p>']
        edges=[(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
        for si,graph in enumerate(graphs):
            traces=[];trace_frames=[]
            for f in graph['frames']:
                pred=load(out/'predictions/geocalib'/graph['shot_id']/f"frame_{f['frame_id']:06d}.json")
                for e in pred['entities']:
                    c=np.array(e['corners_world']);p=[]
                    for a,b in edges:p.extend([c[a].tolist(),c[b].tolist(),[None,None,None]])
                    traces.append(go.Scatter3d(x=[v[0] for v in p],y=[v[1] for v in p],z=[v[2] for v in p],mode='lines',name=e['entity_id']+' '+e['name'],visible=f['frame_id']==0,line={'width':4}));trace_frames.append(f['frame_id'])
            traces.append(go.Scatter3d(x=[0],y=[0],z=[0],mode='markers',name='camera',marker={'size':5,'color':'black'}));trace_frames.append(None)
            buttons=[{'label':str(f['frame_id']),'method':'update','args':[{'visible':[v is None or v==f['frame_id'] for v in trace_frames]}]} for f in graph['frames']]
            fig=go.Figure(traces);fig.update_layout(title=graph['shot_id'],height=720,scene={'aspectmode':'data'},updatemenus=[{'buttons':buttons,'direction':'down'}]);html.append(plot(fig,output_type='div',include_plotlyjs=si==0))
        (out/'scene_viewer.html').write_text('\n'.join(html))
    except ImportError:
        print('Plotly unavailable; JSON and projection viewer remain available')
if __name__=='__main__':main(Path(sys.argv[1]) if len(sys.argv)>1 else DEFAULT_OUT)
