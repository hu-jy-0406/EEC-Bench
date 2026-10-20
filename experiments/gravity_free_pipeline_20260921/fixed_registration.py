import json,os,subprocess,sys,time
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
root=Path(__file__).resolve().parent;workspace=root.parents[2];scripts=workspace/'EECBench/scripts'
sys.path.insert(0,str(scripts));from gs_registration_3d import distance_summary
from register_gs_3d import fitting_rows
from gs_registration_so3 import fit_all_pairs,distances
bases=json.loads((root/'baselines.json').read_text());results={}
for name,base in bases.items():
 case=Path(base)/'pairs/pair_000';out=root/name/'fixed_registration_so3.json'
 cmd=[sys.executable,str(scripts/'register_gs_3d.py'),'--method','roma','--case',str(case),'--output',str(out),'--rotation-model','so3']
 r=subprocess.run(cmd);r.check_returncode()
 old=json.loads((case/'registration/roma_geometry/registration.json').read_text());new=json.loads(out.read_text());a=old['fits']['all_structures'];b=new['fits']['all_structures']
 data=np.load(case/'registration/roma_geometry/correspondences.npz')['data'];indices=np.array(old['sampling']['selected_rows'])
 assert np.array_equal(indices,new['sampling']['selected_rows'])
 def error(f):return np.linalg.norm(f['scale']*data[:,10:13]@np.array(f['rotation']).T+f['translation']-data[:,7:10],axis=1)
 ea,eb=error(a),error(b);delta=np.array(b['rotation'])@np.array(a['rotation']).T
 item=dict(same_correspondence_rows=True,same_selected_rows=True,fitted_pairs=len(indices),candidate_pairs=len(data),
  before_selected_sum=float(ea[indices].sum()),after_selected_sum=float(eb[indices].sum()),
  before_full=distance_summary(ea,data[:,2]),after_full=distance_summary(eb,data[:,2]),
  before_reprojection=a['all_correspondences'],after_reprojection=b['all_correspondences'],
  rotation_change_degrees=float(np.degrees(Rotation.from_matrix(delta).magnitude())),
  tilt_from_previous_up_degrees=float(np.degrees(np.arccos(np.clip(np.array(b['rotation'])[2,2],-1,1)))),
  before_scale=a['scale'],after_scale=b['scale'],role='fixed upstream ablation, NOT a fresh pipeline or independent heldout truth')
 # Change independent coordinate gauges; require identical full-rotation fit quality
 # and FPS selection (within floating-point tolerances), no gravity information.
 GA=Rotation.from_rotvec([.3,-.7,.4]).as_matrix();GB=Rotation.from_rotvec([-.5,.2,.8]).as_matrix();rotated=data.copy()
 rotated[:,7:10]=data[:,7:10]@GA.T;rotated[:,10:13]=data[:,10:13]@GB.T
 rows=fitting_rows(rotated);item['fps_rows_invariant_under_independent_rotation']=bool(np.array_equal(rows,indices))
 f=fit_all_pairs(rotated[indices,7:10],rotated[indices,10:13]);item['gauge_objective_difference']=float(abs(f['objective_value']-b['objective_value']))
 results[name]=item
(root/'fixed_comparison.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2),flush=True)
