"""Read-only frozen frontend coverage audit; no model calls or GPU work."""
from pathlib import Path
import sys,json,hashlib
B=Path(__file__).resolve().parents[2];sys.path.insert(0,str(B/'scripts'))
from gs_flow1_evaluator import Eval
from gs_flow1_compact_payload import pack,unpack,equivalent
case=B/'experiments/study2_integrated_full_fresh_20260919/study2'
if not (case/'selected').exists():
 case=B/'experiments/study2_integrated_full_fresh_20260919'
e=Eval(str(case));rows=[]
for graph,src,static in zip(e.identity_graphs,e.sources,e.graphs):
 original={src['shot_id']+'/'+x['entity_id']:x for x in src['entities']}
 assert set(original)=={x['entity_id'] for x in graph['entities']}
 for ent in graph['entities']:assert ent['observations']==original[ent['entity_id']]['observations']
 equivalent(graph,unpack(pack(graph)))
 rows.append(dict(shot_id=graph['shot_id'],all_entities=len(graph['entities']),static_scoring_entities=len(static['entities']),motion_counts={status:sum(x['motion_status']==status for x in graph['entities']) for status in ['static','moving','unknown']},observations_preserved=True,compact_roundtrip=True))
result=dict(fixture=str(case),mode='offline_input_audit_no_model_inference',shots=rows,source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [case/'inputs/shot1.json',case/'inputs/shot3.json',case/'selected/shot1_scene.json',case/'selected/shot3_scene.json']})
Path(__file__).with_name('audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
