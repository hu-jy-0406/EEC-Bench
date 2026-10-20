from pathlib import Path
import sys,json,numpy as np
r=Path(__file__).resolve().parent;root=r.parents[2];sys.path.insert(0,str(root/'to_human/eec-bench-repro-20260912/third_party/WeDetect/wedetect_anything'))
from infer_anything import proposal_nms
x=json.loads((r/'diagnosis.json').read_text());rows=[]
for f in x['frames']:
 d=r/f['shot']/f"frame_{f['frame_id']:06d}";raw=np.load(d/'raw_forward.npz');trace=json.loads((d/'proposal_trace.json').read_text());keep,_=proposal_nms(raw['scores'],raw['boxes_letterbox'],.025,.7,100)
 candidates=[trace[i] for i in keep.tolist() if trace[i]['roi_iou']>=.5]
 rows.append(dict(shot=f['shot'],frame_id=f['frame_id'],window_region_candidates_after_nms_at_0025=candidates))
 print(f['shot'],f['frame_id'],'maxobj',round(f['max_nearby_objectness'],6),'survivors',[(c['proposal_index'],c['top_class'],round(c['top_class_score'],6),round(c['objectness'],6)) for c in candidates])
(r/'lower_threshold_survivors.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
