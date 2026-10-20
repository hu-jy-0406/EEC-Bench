#!/usr/bin/env python3
"""Frozen-entity GeoCalib/Boxer pilot. Run only on an allocated compute node."""
import argparse, hashlib, json, os, sys, time
from pathlib import Path
import numpy as np

BASE = Path(__file__).resolve().parents[1]
CASE = BASE / 'experiments/study_inconsistent_3'
DEFAULT_OUT = CASE / 'geocalib_boxer_20260913'

def load(p): return json.loads(Path(p).read_text())
def save(p, data):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def unit(v):
    v=np.asarray(v,float); n=np.linalg.norm(v)
    if n<1e-9: raise ValueError('Degenerate direction')
    return v/n

def world_from_camera(up_camera):
    """Choose a proper +Z-up gauge; camera center is origin, yaw is a gauge."""
    z=unit(up_camera); forward=np.array([0.,0.,1.]); y=forward-z*np.dot(forward,z)
    if np.linalg.norm(y)<1e-6: y=np.array([0.,1.,0.])-z*z[1]
    y=unit(y); x=unit(np.cross(y,z)); R=np.stack([x,y,z])
    if not np.allclose(R@R.T,np.eye(3),atol=1e-6) or np.linalg.det(R)<.999: raise ValueError('Improper rotation')
    return R

def frozen():
    root=CASE/'wedetect_shot_entities_20260912/run01'; manifest=load(root/'manifest.json')
    scenes={}
    for s in manifest['shots']:
        if s['shot_id'] not in ['shot1','shot3']:continue
        s=dict(s);s['entities']=load(root/'shots'/s['shot_id']/'entities.json')['entities']
        for f in s['frames']:
            if hashlib.sha256(Path(f['path']).read_bytes()).hexdigest()!=f['sha256']:raise ValueError('Image hash mismatch')
        scenes[s['shot_id']]=s
    return scenes

def calibrate(out,device):
    import torch
    from geocalib import GeoCalib
    torch.set_num_threads(4)
    model=GeoCalib(weights=str(out/'weights/geocalib-pinhole.tar')).to(device).eval()
    for sid,s in frozen().items():
        start=time.time();images=torch.stack([model.load_image(Path(f['path'])) for f in s['frames']]).to(device)
        result=model.calibrate(images,shared_intrinsics=True)
        # GeoCalib's zero roll/pitch vector is [0,-1,0]: physical UP in OpenCV.
        up=result['gravity'].vec3d.detach().cpu().numpy();cams=result['camera']
        fs=cams.f.detach().cpu().numpy();cs=cams.c.detach().cpu().numpy()
        records=[]
        for i,f in enumerate(s['frames']):
            records.append({'frame_id':f['frame_id'],'f_xy_px':fs[i].tolist(),'principal_point_px':cs[i].tolist(),'geocalib_gravity_raw':up[i].tolist(),'physical_down_camera':(-up[i]).tolist()})
        up_consensus=unit(up.mean(0));R=world_from_camera(up_consensus)
        K=np.array([[np.median(fs[:,0]),0,np.median(cs[:,0])],[0,np.median(fs[:,1]),np.median(cs[:,1])],[0,0,1.]])
        diag={k:v.detach().cpu().tolist() for k,v in result.items() if 'uncertainty' in k and hasattr(v,'detach')}
        data={'shot_id':sid,'records':records,'shared_intrinsics':True,'fixed_camera_consensus':{'K':K.tolist(),'physical_up_camera':up_consensus.tolist(),'physical_down_camera':(-up_consensus).tolist(),'R_world_from_camera':R.tolist(),'translation_world_from_camera':[0,0,0]},'uncertainties_raw':diag,'seconds':time.time()-start,'conventions':'camera x-right,y-down,z-forward; world z-up; GeoCalib raw gravity vector treated as physical up; yaw and translation are local gauges, not cross-shot registration','images':s['frames']}
        save(out/'calibration'/f'{sid}.json',data);print('CALIBRATION',sid,'focal',K[0,0],'up',up_consensus,'seconds',data['seconds'],flush=True)
    del model
    if device=='cuda':torch.cuda.empty_cache()

def baseline_camera(sid,fid):
    from sparse_scene_3d import camera_matrix,K
    scene=load(CASE/'sparse_scene_3d_20260913/run01'/('scene_'+sid)/'scene.json')
    c=next(c for c in scene['proposal']['cameras'] if c['frame_id']==fid)
    R,t=camera_matrix(c)
    return K(c),R.T

def run_boxer(out,device,variants,limit):
    import torch
    from PIL import Image
    sys.path.insert(0,str(BASE/'third_party/boxer'))
    from boxernet.boxernet import BoxerNet
    from loaders.base_loader import BaseLoader
    from utils.tw.pose import PoseTW
    torch.set_num_threads(4);torch.manual_seed(0)
    model=BoxerNet.load_from_checkpoint(str(BASE/'third_party/boxer/ckpts/boxernet_hw960in2x6d768-c88128f8.ckpt'),device=device)
    hw=int(model.hw);print('BOXER_SIZE',hw,flush=True)
    for sid,s in frozen().items():
        calibration=load(out/'calibration'/f'{sid}.json')['fixed_camera_consensus']
        for f in s['frames'][:limit or None]:
            im=Image.open(f['path']).convert('RGB');W,H=im.size
            image=torch.from_numpy(np.asarray(im.resize((hw,hw),Image.Resampling.BILINEAR)).copy()).permute(2,0,1).float()/255
            selected=[]
            for e in s['entities']:
                o=next(o for o in e['observations'] if o['frame_id']==f['frame_id'])
                if o['visible'] and o['box_xyxy'] is not None:selected.append((e,o))
            original=np.array([o['box_xyxy'] for e,o in selected],float)
            bb=original[:,[0,2,1,3]]*np.array([hw/W,hw/W,hw/H,hw/H])
            for variant in variants:
                dest=out/'predictions'/variant/sid/f"frame_{f['frame_id']:06d}.json"
                if dest.exists():continue
                if variant.startswith('geocalib'):
                    K=np.array(calibration['K']);R=np.array(calibration['R_world_from_camera'])
                    if variant=='geocalib_focal_low':K[0,0]*=.9;K[1,1]*=.9
                    elif variant=='geocalib_focal_high':K[0,0]*=1.1;K[1,1]*=1.1
                    elif variant in ['geocalib_pitch_low','geocalib_pitch_high']:
                        angle=np.deg2rad(-3 if variant.endswith('low') else 3);c,sn=np.cos(angle),np.sin(angle)
                        perturb=np.array([[1,0,0],[0,c,-sn],[0,sn,c]])
                        R=world_from_camera(perturb@np.array(calibration['physical_up_camera']))
                    elif variant!='geocalib':raise ValueError(variant)
                elif variant=='codex_camera':K,R=baseline_camera(sid,f['frame_id'])
                else:raise ValueError(variant)
                # Match official OmniLoader resize convention and xxyy prompt ordering.
                cam=BaseLoader.pinhole_from_K(hw,hw,K[0,0]*hw/W,K[1,1]*hw/H,K[0,2]*hw/W,K[1,2]*hw/H)
                pose=PoseTW.from_Rt(torch.tensor(R,dtype=torch.float32),torch.zeros(3))
                datum={'img0':image,'cam0':cam,'T_world_rig0':pose,'sdp_w':torch.zeros(0,3),'bb2d':torch.tensor(bb,dtype=torch.float32)}
                start=time.time()
                with torch.inference_mode():res=model(datum)
                obb=res['obbs_pr_w'][0]; corners=obb.bb3corners_world.detach().cpu().numpy();centers=obb.bb3_center_world.detach().cpu().numpy();sizes=obb.bb3_diagonal.detach().cpu().numpy();rot=obb.T_world_object.R.detach().cpu().numpy();probs=obb.prob.detach().cpu().numpy()
                records=[]
                if len(corners)!=len(selected):raise ValueError('Entity output count mismatch')
                for i,(e,o) in enumerate(selected):
                    cc=corners[i]@R; uvh=cc@K.T
                    front=bool(np.all(cc[:,2]>1e-5));uv=uvh[:,:2]/uvh[:,2:]
                    records.append({'entity_id':e['entity_id'],'name':e['name'],'grounding_box_xyxy':o['box_xyxy'],'center_world':centers[i].tolist(),'size_xyz':sizes[i].tolist(),'R_world_from_object':rot[i].tolist(),'corners_world':corners[i].tolist(),'corners_camera':cc.tolist(),'projected_corners_xy':uv.tolist(),'projected_envelope_xyxy':[float(uv[:,0].min()),float(uv[:,1].min()),float(uv[:,0].max()),float(uv[:,1].max())],'all_corners_in_front':front,'model_score':float(np.asarray(probs[i]).reshape(-1)[0])})
                save(dest,{'shot_id':sid,'frame_id':f['frame_id'],'variant':variant,'image':f,'image_size':[W,H],'model_input_size':[hw,hw],'K_original':K.tolist(),'R_world_from_camera':R.tolist(),'translation_world_from_camera':[0,0,0],'unit':'model_predicted_metric_scale_not_measured','depth_input':False,'entities':records,'seconds':time.time()-start})
                print('BOXER',variant,sid,f['frame_id'],len(records),'seconds',time.time()-start,flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=DEFAULT_OUT);p.add_argument('--stage',choices=['calibrate','boxer','all'],default='all');p.add_argument('--device',default='cuda');p.add_argument('--variants',nargs='+',default=['geocalib','codex_camera']);p.add_argument('--limit-frames',type=int,default=0);a=p.parse_args()
    if a.stage in ['calibrate','all']:calibrate(a.out,a.device)
    if a.stage in ['boxer','all']:run_boxer(a.out,a.device,a.variants,a.limit_frames)
if __name__=='__main__':main()
