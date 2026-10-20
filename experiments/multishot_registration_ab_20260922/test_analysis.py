"""CPU regression for common-frame inverses, endpoint metric and grouping coverage."""
import sys,tempfile,json
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path[:0]=[str(R),str(B/'scripts')]
import analyze
from run_gs_integrated import save,sha,read
from register_gs_codex import make_fit
f=make_fit(dict(scale=2.,yaw_deg=90.,translation=[1.,2.,3.],confidence='high',reasoning='synthetic',limitations='test'))
signs=np.array(list(__import__('itertools').product([-1,1],repeat=3)))
def box(center):return dict(center_world=list(center),size_xyz=[.2,.2,.2],R_world_from_object=np.eye(3).tolist(),corners_world=(np.asarray(center)+signs*.1).tolist())
with tempfile.TemporaryDirectory(prefix='eec-registration-math-') as d:
 analyze.R=Path(d)
 for name in ['parking4','bedroom4','diner8']:
  c=Path(d)/'shared'/name;shots=['Shot1','Shot2'];groups=[]
  save(c/'raw_manifest.json',dict(shots=[dict(shot_id=s) for s in shots]));save(c/'frozen_frontend.json',dict(hashes={},original_frames={}))
  cloud=np.array([[0,0,0],[1,0,0],[0,1,1],[2,2,0]],dtype=float);target=analyze.transform(f,cloud)
  for s,points in zip(shots,[target,cloud]):
   nodes=[]
   for i,point in enumerate(points):
    eid=s+f'/e{i}';g=box(point);nodes.append(dict(entity_id=eid,name=eid,motion_status='static',geometry=g,frame_evidence=[dict(frame_id=j,geometry=g) for j in [0,80]]))
   save(c/'selected'/f'{s}_scene.json',dict(entities=nodes))
  groups=[dict(group_id=f'g{i}',entity_ids=[s+f'/e{i}' for s in shots]) for i in range(len(cloud))];save(c/'global_initial/results.json',dict(groups=groups))
  pair=c/'pairs/Shot1_Shot2';save(pair/'registration/roma_geometry/registration.json',dict(fits=dict(all_structures=f)));data=np.zeros((4,19));data[:,7:10]=target;data[:,10:13]=cloud;np.savez(pair/'registration/roma_geometry/correspondences.npz',data=data)
  rows=[dict(shot_id='Shot1',prototype='Shot1',status='root',fit=None),dict(shot_id='Shot2',prototype='Shot1',status='numeric_candidate',fit=f)]
  for m in ['optimization','direct']:save(c/m/'results.json',dict(roots=['Shot1'],shots=rows,seconds=1.,attempts=[dict(root='Shot1',shot='Shot2',case=str(pair))]))
 analyze.run();result=read(Path(d)/'comparison.json')
 for e in result['episodes']:
  assert all(x['mean_distance']<1e-12 for x in e['point_diagnostics'])
  for m in e['metrics'].values():
   assert m['comparable_shot_pairs']==m['possible_shot_pairs']==1
   assert m['pairs'][0]['negative_cosine_proposals']==0
  comp=read(Path(d)/'shared'/e['name']/'comparison.json');assert len(comp['entity_endpoint_records'])==8
  assert all(x['center_distance']<1e-12 for x in comp['entity_endpoint_records'])
print('PASS synthetic analysis: exact registration residuals, inverse transform, 3D centers, cosines, common coverage, plot generation',flush=True)
(R/'analysis_test.json').write_text(json.dumps(dict(status='pass',synthetic_only=True,real_inference=False))+'\n')
