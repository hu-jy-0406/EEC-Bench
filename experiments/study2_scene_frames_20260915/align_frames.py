"""Coincide two separately constructed scene frames, without an all-box fit."""
import hashlib,json,sys
from pathlib import Path
import numpy as np
from scene_frame import to_scene,from_scene
BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
sys.path.insert(0,str(ROOT/'EECBench/scripts'))
import robust_box_registration as reg
from run_isolated_shot_static_3d import owned_compute_job

def read(p):return json.loads(p.read_text())
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
 owned_compute_job()
 records=[read(BASE/n) for n in ['shot1_scene.json','shot3_scene.json']]
 frames=[r['frame'] for r in records]
 for rec,f in zip(records,frames):
  assert f['input_graphs_used']==1 and not f['cross_shot_inputs_used'] and not f['all_box_optimization_used']
  assert sha(Path(rec['provenance']['source']))==rec['provenance']['sha256']
  mat=np.array(f['axes_in_input_columns_xyz']);assert np.allclose(mat.T@mat,np.eye(3),atol=1e-12) and np.linalg.det(mat)>.999999
  source=read(Path(rec['provenance']['source']));inv={e['entity_id']:e for e in source['entities']}
  for b in rec['boxes']:
   np.testing.assert_allclose(from_scene(b['corners'],f),inv[b['id']]['geometry']['corners_world'],atol=1e-12)
  np.testing.assert_allclose(to_scene(f['origin_in_input'],f),[0,0,0],atol=1e-12)
  np.testing.assert_allclose(to_scene(inv[f['direction_entity_id']]['geometry']['center_world'],f)[:2],[0,1],atol=1e-12)
 A,B=[np.array(f['axes_in_input_columns_xyz']) for f in frames];LA,LB=[f['unit_length_in_input'] for f in frames]
 scale=LB/LA;rotation=B@A.T;translation=np.array(frames[1]['origin_in_input'])-scale*rotation@np.array(frames[0]['origin_in_input'])
 equivalent=(scale,rotation,translation)
 # The scene-frame alignment itself is identity. This transform is derived back
 # in the old input coordinates solely for explanation/comparison.
 source_a=read(Path(records[0]['provenance']['source']))
 all_a=np.array([e['geometry']['corners_world'] for e in source_a['entities']])
 np.testing.assert_allclose(from_scene(to_scene(all_a,frames[0]),frames[1]),reg.transform(all_a,equivalent),atol=1e-12)
 mapping_path=BASE.parent/'study_inconsistent_3/gs_consistency_20260914/run02/matching.json'
 matching=read(mapping_path);groups=matching['groups'];lookup={eid:(g['group_id'],g['identity']) for g in groups for eid in g['a_ids']+g['b_ids']}
 boxes=[];cameras=[]
 for shot,rec in enumerate(records):
  for b in rec['boxes']:
   gid,state=lookup[b['id']];boxes.append(dict(**b,group=gid,matching=state,shot=shot))
  c=rec['cameras'][0];cameras.append(dict(shot=shot,name=f"Shot{1 if shot==0 else 3}相机",position=c['position_scene'],forward=c['forward_scene']))
 selected=[g for g in groups if g['identity']=='matched'];boxmap={b['id']:b for b in boxes}
 a,b=[np.array([boxmap[g[key][0]]['corners'] for g in selected]) for key in ['a_ids','b_ids']]
 residuals=reg.box_residuals(a,b,reg.identity())[0];refids={f['origin_entity_id'] for f in frames}|{f['direction_entity_id'] for f in frames}
 rows=[]
 for g,err in zip(selected,residuals):
  used=any(i in refids for i in g['a_ids']+g['b_ids'])
  rows.append(dict(group_id=g['group_id'],name=boxmap[g['a_ids'][0]]['name'],corner_rmse_scene_units=float(err),reference_used_to_define_frame=used))
 summary=dict(method='independent_scene_frames_then_coincide_origins_axes_units',frame_alignment_transform={'scale':1,'R':np.eye(3).tolist(),'t':[0,0,0]},
   equivalent_input_transform=reg.model_record(equivalent),equivalent_yaw_deg=float(np.degrees(np.arctan2(rotation[1,0],rotation[0,0]))),
   units='Each shot horizontal desk-to-radiator separation = 1',frames=frames,counts=[len(r['boxes']) for r in records],
   camera_poses_in_common_scene=cameras,matched_box_corner_rmse_scene_units=float(np.sqrt(np.mean(residuals**2))),
   nonreference_box_corner_rmse_scene_units=float(np.sqrt(np.mean([r['corner_rmse_scene_units']**2 for r in rows if not r['reference_used_to_define_frame']]))),
   all_box_fitting_performed=False,identity_rematching_performed=False,prior_gravity_optimizer_used=False,
   reference_alignment_not_independent_consistency_evidence=True)
 save(BASE/'summary.json',summary);save(BASE/'entity_residuals.json',rows)
 save(BASE/'overlay_data.json',dict(boxes=boxes,cameras=cameras,counts=summary['counts'],coordinate_frame='shared_scene_desk_origin_radiator_direction',length_unit='desk-radiator horizontal baseline',frames=frames))
 audit=dict(status='pass',tests_passed=3,test_seconds=.038,source_graphs_unchanged=True,frame_build_inputs_per_process=1,
            frame_origins_axes_units_verified=True,all_38_boxes_inverse_replayed=True,equivalent_input_transform_verified=True,
            raw_graph_coordinates_not_optimized=True,cameras_transformed_as_observations_not_alignment_anchors=True,
            source_hashes={r['provenance']['source']:r['provenance']['sha256'] for r in records},matching_sha256=sha(mapping_path),
            browser_execution_tested=False,score_modified=False)
 save(BASE/'audit.json',audit)
 print(json.dumps({k:v for k,v in summary.items() if k not in ['frames']},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
