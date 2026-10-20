import sys,json,py_compile,importlib.util
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path[:0]=[str(R),str(B/'scripts')]
for p in R.glob('*.py'):py_compile.compile(str(p),doraise=True)
import model_stages,optimize,analyze
from partial_scene_contract import schema_validate
from gs_consistency_contract import obj,arr,S,N,enum
from run_gs_integrated import read,sha
for r in read(R/'selection.json')['episodes']:
 d=R/'inputs'/r['name'];m=read(d/'manifest.json');assert len(m['shots'])==r['shots']
 assert all(sha(f['path'])==f['sha256'] for s in m['shots'] for f in s['frames'])
# Synthetic math: source -> reference, including direct arbitrary member-to-member inversion.
import numpy as np
from register_gs_codex import make_fit
f=make_fit(dict(scale=2.,yaw_deg=90.,translation=[1.,2.,3.],confidence='high',reasoning='synthetic',limitations='test'))
p=np.array([[1.,0.,0.],[0.,2.,1.]])
a=analyze.transform(f,p);assert np.allclose(a,[[1,4,3],[-3,2,5]])
assert np.allclose((a-f['translation'])@np.array(f['rotation'])/f['scale'],p)
glob={'groups':[dict(group_id='g01',entity_ids=['Shot1/e1','Shot3/e3'],identity_evidence='same structure',anchor_pairs=[dict(shot_a='Shot1',shot_b='Shot3',reason='stable')]),dict(group_id='g02',entity_ids=['Shot2/e2'],identity_evidence='unknown',anchor_pairs=[])]}
x=optimize.projected_matching(None,'Shot1','Shot3',glob);assert x['structural_anchor_group_ids']==['g01'];assert x['groups'][0]['a_ids']==['shot1/e1'];assert x['groups'][0]['b_ids']==['shot3/e3']
y=optimize.projected_matching(None,'Shot1','Shot2',glob);assert not y['structural_anchor_group_ids'] and all(g['identity']=='unmatched' for g in y['groups'])
(R/'preflight.json').write_text(json.dumps(dict(status='pass',tests=['all scripts compile/import','96 frame SHA256','3 manifests coverage','known transform and inverse','A/C direct identity projection','no speculative B occurrence'],production_changed=False),indent=2)+'\n')
# Real canonical geometry schema compatibility (CPU-only frozen historical fixture).
fixture=B/'experiments/identity_minimal_full_validation_20260922/runs/study3/selected/shot1_scene.json'
graph=read(fixture)
for e in graph['entities']:
 if e['geometry']:
  assert np.asarray(e['geometry']['center_world']).shape==(3,)
  assert np.asarray(e['geometry']['corners_world']).shape==(8,3)
  assert analyze.transform(None,e['geometry']['center_world']).shape==(3,)
print('PASS preflight',flush=True)
