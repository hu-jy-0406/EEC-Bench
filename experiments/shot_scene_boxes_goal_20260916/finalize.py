"""Materialize tested best candidate, full trajectories and comparison artifacts."""
import copy,csv,hashlib,json,sys
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;BASE=HERE.parents[1];sys.path.insert(0,str(BASE/'scripts'))
from robust_box_registration import corners,transform
from run_isolated_shot_static_3d import owned_compute_job

def read(p):return json.loads(p.read_text())
def save(p,v):p.parent.mkdir(exist_ok=True,parents=True);p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
job=owned_compute_job();results={}
for name in ['comparison_boxer_depth.json','comparison_boxer_no_depth.json','comparison_boxer_refined.json']:results.update(read(HERE/name))
best=min(results,key=lambda k:results[k]['normalized_mse']);fit=results[best];method,variant=best.split('_boxer_',1);variant='boxer_'+variant
out=HERE/'selected';out.mkdir(exist_ok=True)
selection={'method':method,'variant':variant,'criterion':'minimum_normalized_plain_corner_MSE_among_tested_complete_new_scene_routes','fit':fit,'status':'tested_best_not_certified_true_3D_or_physical_alignment','uses_known_anomaly_as_target':False,'allocation':job}
save(out/'selection.json',selection)
R=np.array(fit['rotation']);t=np.array(fit['translation']);s=fit['scale'];bundle={'coordinate_frame':'shot1_scene','transform_shot3_to_shot1':{'scale':s,'rotation':R.tolist(),'translation':t.tolist()},'entities':[],'cameras':{},'motion_representation':'best_visible_frame_representative_plus_estimated_per_frame_trajectory','comparison_scope':'11 matched static entities only','geometry_is_ground_truth':False}
for shot in ['shot1','shot3']:
 graph=read(HERE/method/shot/variant/'scene_graph.json');manifest=read(HERE/'inputs'/f'{shot}.json');source={shot+'/'+e['entity_id']:e for e in manifest['entities']}
 save(out/f'{shot}_scene.json',graph)
 def box_to_common(b):
  b=copy.deepcopy(b)
  if shot=='shot3':
   b['center_world']=(s*R@np.array(b['center_world'])+t).tolist();b['R_world_from_object']=(R@np.array(b['R_world_from_object'])).tolist();b['size_xyz']=(s*np.array(b['size_xyz'])).tolist()
  b['corners_world']=corners(b).tolist();return b
 for e in graph['entities']:
  obs={o['frame_id']:o for o in source[e['entity_id']]['observations']};entity={'shot_id':shot,'entity_id':e['entity_id'],'name':e['name'],'motion_status':e['motion_status'],'geometry':box_to_common(e['geometry']),'representative_frame_id':e['aggregation'].get('frame_id'),'estimated_observation_trajectory':[]}
  for row in e['frame_evidence']:
   o=obs[row['frame_id']];entity['estimated_observation_trajectory'].append({'frame_id':row['frame_id'],'exist':o['exist'],'visible':o['visible'],'geometry':box_to_common(row['geometry']) if row.get('geometry') else None})
  bundle['entities'].append(entity)
 cams=copy.deepcopy(graph['cameras'])
 if shot=='shot3':
  for c in cams:
   c['position_world']=(s*R@np.array(c['position_world'])+t).tolist();c['R_world_from_camera']=(R@np.array(c['R_world_from_camera'])).tolist()
   for key in ['forward_world','up_world']:c[key]=(R@np.array(c[key])).tolist()
 bundle['cameras'][shot]=cams
save(out/'all_entities_in_shot1_scene.json',bundle)
with (out/'entity_boxes.csv').open('w') as f:
 w=csv.writer(f);w.writerow(['shot','entity','name','motion_status','representative_frame','cx','cy','cz','sx','sy','sz'])
 for e in bundle['entities']:w.writerow([e['shot_id'],e['entity_id'],e['name'],e['motion_status'],e['representative_frame_id'],*e['geometry']['center_world'],*e['geometry']['size_xyz']])
all_results={**{k:{**v,'role':'historical_fixed_camera'} for k,v in read(HERE/'baseline_corner_mse.json').items()},**{k:{**v,'role':'new_fixed_scene'} for k,v in results.items()}}
with (HERE/'method_comparison.csv').open('w') as f:
 w=csv.writer(f);w.writerow(['method','role','normalized_MSE','raw_MSE','scale','yaw_degrees','shot1_static_projection_IoU','shot3_static_projection_IoU','inference_and_box_seconds'])
 for key,v in all_results.items():
  proj=v.get('reprojection',[]);w.writerow([key,v['role'],v['normalized_mse'],v['mse_xyz'],v['scale'],v['yaw_deg'],*([p['static_fused_mean_iou'] for p in proj] if proj else [None,None]),sum(v.get('geometry_seconds',[])+v.get('boxer_seconds',[])) if 'geometry_seconds' in v else None])
with (out/'relations.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=['group_a','group_b','cosine']);w.writeheader();w.writerows(fit['relations'])
print('SELECTED',best,fit['normalized_mse'],'full entities',len(bundle['entities']),out)
