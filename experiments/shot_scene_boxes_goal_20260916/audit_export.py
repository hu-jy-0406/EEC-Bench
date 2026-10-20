import csv,json,sys
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parents[1]/'scripts'))
from robust_box_registration import corners,transform
from run_isolated_shot_static_3d import owned_compute_job
job=owned_compute_job();b=json.loads((HERE/'selected/all_entities_in_shot1_scene.json').read_text());p=b['transform_shot3_to_shot1'];T=(p['scale'],np.array(p['rotation']),np.array(p['translation']));mx=0
assert len(b['entities'])==41 and len({e['entity_id'] for e in b['entities']})==41
for sid,n in [('shot1',19),('shot3',22)]:
 g=json.loads((HERE/'selected'/f'{sid}_scene.json').read_text());m={e['entity_id']:e for e in g['entities']};assert len(m)==n
 for e in [x for x in b['entities'] if x['shot_id']==sid]:
  src=m[e['entity_id']];expected=corners(src['geometry']);expected=transform(expected,T) if sid=='shot3' else expected
  error=np.max(abs(expected-corners(e['geometry'])));mx=max(mx,float(error));assert error<1e-10
  rows={r['frame_id']:r for r in src['frame_evidence']};assert len(e['estimated_observation_trajectory'])==6
  for r in e['estimated_observation_trajectory']:
   source=rows[r['frame_id']].get('geometry');assert (source is None)==(r['geometry'] is None)
   if source:
    expected=corners(source);expected=transform(expected,T) if sid=='shot3' else expected
    np.testing.assert_allclose(corners(r['geometry']),expected,atol=1e-10)
rows=list(csv.DictReader((HERE/'selected/entity_boxes.csv').open()));assert len(rows)==41
r={'status':'pass','entity_count':41,'moving_entities':[e['entity_id'] for e in b['entities'] if e['motion_status']!='static'],'all_trajectories_exported':True,'max_corner_export_error':mx,'allocation':job}
(HERE/'selected/export_audit.json').write_text(json.dumps(r,indent=2)+'\n');print(r)
