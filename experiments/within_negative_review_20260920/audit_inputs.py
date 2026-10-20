import json,sys
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from gs_flow1_compact_payload import unpack,equivalent
rows=[]
for mode in ['screen','full']:
 for p in (R/mode).glob('*/calls/within_*/input.json'):
  d=json.loads(p.read_text());wire=json.loads((p.parent/'wire_input.json').read_text());equivalent(d,unpack(wire))
  canonical=json.loads((p.parents[2]/'within'/d['shot_id']/'canonical_review_input.json').read_text())
  original={e['entity_id']:e for e in canonical['graph']['entities']}
  assert len(original)==len(d['entities']);assert d['cameras']==canonical['graph']['cameras']
  for e in d['entities']:
   old=original[e['entity_id']];assert [f['frame_id'] for f in e['frame_evidence']]==[f['frame_id'] for f in old['frame_evidence']]
   for a,b in zip(e['frame_evidence'],old['frame_evidence']):
    assert a['visible']==b['visible'] and a['box_xyxy']==b['box_xyxy']
    if b.get('geometry'):
     for k in ['center_world','size_xyz','R_world_from_object']:assert a['geometry'][k]==b['geometry'][k]
    else:assert a['geometry'] is None
  assert d['events']==canonical['events'];assert len(d['images'])==6
  rows.append(dict(call=str(p.parent),all_entities_frames_boxes_defining_geometry_cameras_events_preserved=True,compact_roundtrip=True))
(R/'input_audit.json').write_text(json.dumps(rows,indent=2)+'\n');print('Validated',len(rows),'actual model inputs')
