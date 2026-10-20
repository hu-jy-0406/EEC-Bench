import collections,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'EECBench/scripts'))
import run_wedetect_shot_entities as io
def read(p):return json.loads(Path(p).read_text())
assert read(OUT/'run.json')['status']=='success'
summary=[];frames=[]
oldroot=ROOT/'EECBench/experiments/study_inconsistent_2/wedetect_shot_entities_20260911/parallel_run01/shots'
for sid,oldid in [('shot1','inconsistent_study_shot1'),('shot3','inconsitent_study_shot3')]:
 old={f['frame_id']:f['detections'] for f in read(oldroot/oldid/'input.json')['frames']}
 pairs=[];totals=[collections.Counter(),collections.Counter()]
 for variant in ['original','resized']:
  er=OUT/(variant+'_'+sid)/'entities';shot=read(er/'manifest.json')['shots'][0]
  for f in shot['frames']:assert io.sha(f['path'])==f['sha256']
  ds=io.load_detections(er/'detections',[shot]);pairs.append({fid:d['detections'] for (shotid,fid),d in ds.items()})
 for fid,a in pairs[0].items():
  b=pairs[1][fid];counts=[collections.Counter(x['label'] for x in ds) for ds in [a,b]]
  for t,c in zip(totals,counts):t.update(c)
  previous=old[fid];same=len(previous)==len(a) and all((x['name'],x['box_xyxy'])==(y['label'],y['box_xyxy']) for x,y in zip(previous,a))
  delta=max(abs(x['score']-y['score']) for x,y in zip(previous,a)) if same else None
  frames.append(dict(shot=sid,frame_id=fid,original_count=len(a),resized_count=len(b),original_window=counts[0]['窗户'],resized_window=counts[1]['窗户'],original_door=counts[0]['门'],resized_door=counts[1]['门'],lost_label_counts=dict(counts[0]-counts[1]),gained_label_counts=dict(counts[1]-counts[0]),original_matches_historical_labels_boxes=same,max_historical_score_delta=delta))
  assert same,'Original control did not reproduce previous labels/boxes'
 selected=[f for f in frames if f['shot']==sid]
 summary.append(dict(shot=sid,original_candidates=sum(totals[0].values()),resized_candidates=sum(totals[1].values()),original_window_frames=[f['frame_id'] for f in selected if f['original_window']],resized_window_frames=[f['frame_id'] for f in selected if f['resized_window']],original_door_frames=[f['frame_id'] for f in selected if f['original_door']],resized_door_frames=[f['frame_id'] for f in selected if f['resized_door']],original_label_totals=dict(totals[0]),resized_label_totals=dict(totals[1])))
io.dump(OUT/'comparison.json',dict(summary=summary,frames=frames))
print(json.dumps(dict(summary=summary,frames=frames),ensure_ascii=False,indent=2))
