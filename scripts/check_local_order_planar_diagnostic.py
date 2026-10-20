#!/usr/bin/env python3
"""Optional 2D diagnostic with explicit caller-supplied corners, never ground truth."""
import argparse
from itertools import product
import json
from pathlib import Path
import numpy as np


def homography(points):
    target=[(0,0),(1,0),(1,1),(0,1)]
    a=[];b=[]
    for (x,y),(u,v) in zip(points,target):
        a += [[x,y,1,0,0,0,-u*x,-u*y],[0,0,0,x,y,1,-v*x,-v*y]];b += [u,v]
    return np.r_[np.linalg.solve(np.array(a,float),np.array(b,float)),1].reshape(3,3)


def project_bounds(h,box):
    xy=np.array([[x,y,1] for x in (box[0],box[2]) for y in (box[1],box[3])]);p=xy@h.T
    if np.any(np.abs(p[:,2])<1e-10) or (np.any(p[:,2]<0) and np.any(p[:,2]>0)):raise ValueError('Invalid projective domain')
    p=p[:,:2]/p[:,2,None]
    return p.min(axis=0),p.max(axis=0)


def audit(root,corners,out):
    marks=json.loads(corners.read_text());result=json.loads((root/'comparison.json').read_text());records=[]
    for item in result['items']:
        if item['query']['reference']!=marks['reference']:continue
        for side,sid in zip(('a','b'),result['source_shots']):
            mark=marks['shots'][sid];quad=np.array(mark['quad_pixels'],float);eps=mark['corner_uncertainty_pixels']
            for o in item['evidence'][side]['raw_review']:
                aa=o['subject_center_bounds_xyxy'];bb=o['object_center_bounds_xyxy']
                if not aa or not bb:continue
                lo=np.array([float('inf')]*2);hi=-lo
                # Corner perturbations are a finite sensitivity check, not proof over a continuum.
                for signs in product((-1,1),repeat=8):
                    h=homography(quad+eps*np.array(signs).reshape(4,2));al,ah=project_bounds(h,aa);bl,bh=project_bounds(h,bb)
                    lo=np.minimum(lo,al-bh);hi=np.maximum(hi,ah-bl)
                records.append(dict(shot_id=sid,frame_id=o['frame_id'],delta_u_range=lo[[0]].tolist()+hi[[0]].tolist(),
                    delta_v_range=lo[[1]].tolist()+hi[[1]].tolist(),physical_order=['less' if hi[k]<0 else 'greater' if lo[k]>0 else 'unresolved' for k in range(2)]))
    data=dict(method='2D homography sensitivity diagnostic',corner_provenance=marks,
        limitations='Manually marked approximate support corners; model-inferred center bounds. Assumes a planar rectangular tabletop. Finite corner perturbations are not exhaustive uncertainty certification or independent GT. Not fed to extraction/review.',records=records)
    out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');print(json.dumps(records,ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--corners',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();audit(a.run,a.corners,a.out)
