"""Compare complete independently reconstructed scenes with frozen static matches."""
import argparse,hashlib,json,sys,time
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;BASE=HERE.parents[1]
sys.path.insert(0,str(BASE/'scripts'))
from global_corner_mse import fit
from robust_box_registration import corners,transform
from run_isolated_shot_static_3d import owned_compute_job

def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--methods',nargs='+',default=['pi3x','da3nested']);p.add_argument('--variant',default='boxer_depth');a=p.parse_args()
 job=owned_compute_job();match=BASE/'experiments/study2_static_set_consistency_20260916/run01/matching.json'
 groups=[g for g in read(match)['groups'] if g['identity']=='matched'];assert len(groups)==11
 results={}
 for method in a.methods:
  paths=[HERE/method/s/a.variant/'scene_graph.json' for s in ['shot1','shot3']];graphs=[read(p) for p in paths]
  maps=[{e['entity_id']:e for e in g['entities']} for g in graphs]
  assert [len(m) for m in maps]==[19,22]
  for side,m in zip(['a','b'],maps):
   assert all(m[g[side+'_ids'][0]]['motion_status']=='static' for g in groups)
  target,source=[np.array([corners(m[g[side+'_ids'][0]]['geometry']) for g in groups]) for m,side in zip(maps,['a','b'])]
  start=time.time();r=fit(source,target);rev=fit(target,source);assert abs(r['normalized_mse']-rev['normalized_mse'])<1e-10
  r.update(reverse=rev,seconds=time.time()-start,groups=[g['group_id'] for g in groups],sources={str(p):sha(p) for p in paths},matching_sha256=sha(match),allocation=job)
  r['coverage']=[g['counts'] for g in graphs]
  r['reprojection']=[{'static_fused_mean_iou':float(np.mean([e['fused_projection_mean_iou'] for e in g['entities'] if e['motion_status']=='static'])),
   'per_frame_mean_iou':float(np.mean([f['projection_iou'] for e in g['entities'] for f in e['frame_evidence'] if 'projection_iou' in f])),
   'representative_fallback_entities':[e['entity_id'] for e in g['entities'] if e['aggregation']['status']!='fused']} for g in graphs]
  r['geometry_seconds']=[read(HERE/method/s/'complete.json')['seconds'] for s in ['shot1','shot3']]
  r['boxer_seconds']=[read(HERE/method/s/a.variant/'complete.json')['seconds'] for s in ['shot1','shot3']]
  pred=transform(source,(r['scale'],np.array(r['rotation']),np.array(r['translation']))).mean(1);centers=target.mean(1);relations=[]
  for i in range(len(groups)):
   for j in range(i+1,len(groups)):
    v=centers[j]-centers[i];w=pred[j]-pred[i];den=np.linalg.norm(v)*np.linalg.norm(w)
    relations.append({'group_a':groups[i]['group_id'],'group_b':groups[j]['group_id'],'cosine':float(v@w/den) if den>1e-10 else None})
  r['relations']=sorted(relations,key=lambda q:q['cosine'] if q['cosine'] is not None else -2)
  results[method+'_'+a.variant]=r
  print(method,a.variant,'normMSE',r['normalized_mse'],'rawMSE',r['mse_xyz'],'yaw',r['yaw_deg'],'scale',r['scale'],'projection',r['reprojection'],flush=True)
 dest=HERE/f'comparison_{a.variant}.json';dest.write_text(json.dumps(results,indent=2,allow_nan=False)+'\n')
if __name__=='__main__':main()
