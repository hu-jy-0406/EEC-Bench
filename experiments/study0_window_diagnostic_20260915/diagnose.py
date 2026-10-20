#!/usr/bin/env python3
"""Instrument the unchanged WeDetect CPU forward pass and postprocessing on all study0 frames."""
import os,sys,json,time,hashlib,base64,html
from pathlib import Path
import numpy as np
import torch
from PIL import Image
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
PORT=ROOT/'to_human/eec-bench-repro-20260912'
sys.path.insert(0,str(PORT/'detector'))
from wedetect_adapter import Detector,letterbox,proposal_nms,rescale,np_sigmoid
from torchvision.ops import batched_nms
sys.path.insert(0,str(ROOT/'EECBench/scripts'))
from run_isolated_shot_static_3d import owned_compute_job

def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def iou_many(boxes,box):
    inter=np.maximum(0,np.minimum(boxes[:,2:],box[2:])-np.maximum(boxes[:,:2],box[:2])).prod(1)
    union=np.maximum(0,boxes[:,2:]-boxes[:,:2]).prod(1)+np.maximum(0,box[2:]-box[:2]).prod()-inter
    return inter/np.maximum(union,1e-12)
job=owned_compute_job();assert os.getloadavg()[0]<8
for name in ['OMP_NUM_THREADS','MKL_NUM_THREADS']:assert int(os.environ.get(name,'2'))<=2
# Exact original settings; extra classification tracing never alters the output path.
torch.set_num_threads(2);torch.manual_seed(0);np.random.seed(0)
weights=PORT/'weights/wedetect_base_uni.pth';det=Detector(weights,'cpu')
window_ids=[i for i,n in enumerate(det.vocab) if n=='窗户'];assert len(window_ids)==1;wid=window_ids[0]
source=ROOT/'EECBench/experiments/study01_gs_v12_20260915/study0/entities'
manifest=json.loads((source/'manifest.json').read_text())
# Approximate, visually checked full visible window region; diagnostic association only, never model input.
roi=np.array([277.,0.,445.,225.])
state=dict(status='running',job=job,device='cpu',seed=0,source_manifest=str(source/'manifest.json'),source_manifest_sha256=sha(source/'manifest.json'),weight_sha256=sha(weights),window_class_id=wid,
    policy=dict(objectness_threshold=.1,nms_iou=.7,top_k=100,match_threshold=.4),diagnostic_roi=roi.tolist(),roi_scope='Approximate image-space window localization, not annotation ground truth and never a detector input',frames=[])
save(OUT/'run.json',state);summaries=[];cards=[]
for shot in manifest['shots']:
 sid=shot['shot_id']
 for frame in shot['frames']:
  start=time.time();fid=frame['frame_id'];dest=OUT/sid/f'frame_{fid:06d}';dest.mkdir(parents=True,exist_ok=False)
  assert sha(frame['path'])==frame['sha256'];im=Image.open(frame['path']).convert('RGB');w,h=im.size
  lb,_,_=letterbox(np.asarray(im).copy(),(640,640));inp=np.ascontiguousarray((lb/255.).transpose(2,0,1)[None].astype(np.float32))
  with torch.inference_mode():scores,boxes,embeds=[x[0].cpu().numpy() for x in det.model(torch.from_numpy(inp))]
  np.savez_compressed(dest/'raw_forward.npz',scores=scores,boxes_letterbox=boxes,embeds=embeds)
  obj=scores.max(1);valid=np.flatnonzero(obj>.1)
  allkeep=valid[batched_nms(torch.from_numpy(boxes[valid]).float(),torch.from_numpy(obj[valid]).float(),torch.zeros(len(valid),dtype=torch.long),.7).numpy()]
  keep,keepscores=proposal_nms(scores,boxes,.1,.7,100);keep=keep.numpy();assert np.array_equal(keep,allkeep[:100])
  # All 8400 proposal window scores and top category; bounded batches limit RAM.
  topids=np.empty(len(boxes),int);topscores=np.empty(len(boxes),np.float32);window=np.empty(len(boxes),np.float32)
  for j in range(0,len(boxes),128):
   logits=(det.text@embeds[j:j+128].T)*det.scales[None,j:j+128]+det.biases[None,j:j+128]
   ids=np.argmax(logits,axis=0);topids[j:j+128]=ids;topscores[j:j+128]=np_sigmoid(logits[ids,np.arange(len(ids))]);window[j:j+128]=np_sigmoid(logits[wid])
  final=[]
  for k in keep.tolist():
   prob=np_sigmoid((det.text@embeds[k])*det.scales[k]+det.biases[k]);cls=int(np.argmax(prob));score=float(prob[cls]);topids[k]=cls;topscores[k]=score;window[k]=prob[wid]
   if score<.4:continue
   box=rescale((640,640),boxes[k].copy(),(h,w)).round().tolist();assert box[2]>box[0] and box[3]>box[1]
   final.append(dict(id=len(final)+1,label=det.vocab[cls],class_id=cls,box_xyxy=box,score=score,raw_proposal_index=k))
  old=json.loads((source/'detections'/sid/f'frame_{fid:06d}'/'detections.json').read_text())['detections']
  shape_match=len(old)==len(final) and all((a['label'],a['class_id'],a['box_xyxy'])==(b['label'],b['class_id'],b['box_xyxy']) for a,b in zip(old,final))
  delta=max((abs(a['score']-b['score']) for a,b in zip(old,final)),default=0) if shape_match else None
  pix=np.array([rescale((640,640),b.copy(),(h,w)) for b in boxes]);overlap=iou_many(pix,roi)
  allset=set(allkeep.tolist());keepset=set(keep.tolist());validset=set(valid.tolist());ranks={k:i+1 for i,k in enumerate(allkeep.tolist())}
  # Record exactly which earlier retained proposal suppresses every objectness-qualified loser.
  blockers={}
  for k in valid:
   if k not in allset:
    ovs=iou_many(boxes[allkeep],boxes[k]);cand=[int(z) for z,v in zip(allkeep,ovs) if v>.7 and obj[z]>=obj[k]]
    assert cand;blockers[int(k)]=cand[0]
  def record(k):
   k=int(k)
   if k not in validset:stage='objectness_below_threshold'
   elif k not in allset:stage='suppressed_by_nms'
   elif k not in keepset:stage='outside_top100'
   elif topscores[k]<.4:stage='class_score_below_threshold'
   elif topids[k]!=wid:stage='output_as_other_class'
   else:stage='output_as_window'
   return dict(proposal_index=k,box_xyxy=pix[k].tolist(),roi_iou=float(overlap[k]),objectness=float(obj[k]),window_score=float(window[k]),top_class=det.vocab[int(topids[k])],top_class_id=int(topids[k]),top_class_score=float(topscores[k]),stage=stage,nms_blocker=blockers.get(k),nms_rank=ranks.get(k))
  records=[record(k) for k in range(len(boxes))]
  save(dest/'proposal_trace.json',records);save(dest/'final_detections.json',final)
  save(dest/'postprocessing.json',dict(valid_objectness_indices=valid.tolist(),all_nms_survivors=allkeep.tolist(),top100_indices=keep.tolist()))
  near=np.flatnonzero(overlap>=.5);near03=np.flatnonzero(overlap>=.3)
  best_raw=record(int(np.argmax(overlap)));best_kept=record(max(keep,key=lambda k:overlap[k])) if len(keep) else None
  candidates=sorted(near.tolist(),key=lambda k:float(window[k]),reverse=True)
  selected=set(candidates[:15]);selected.update([int(np.argmax(overlap))]);selected.update(k for k in keep if overlap[k]>=.3)
  selected.update(blockers[k] for k in list(selected) if k in blockers)
  diag=[record(k) for k in sorted(selected)];save(dest/'window_candidates.json',diag)
  stages={stage:sum(records[k]['stage']==stage for k in near) for stage in sorted({x['stage'] for x in records})}
  summary=dict(shot=sid,frame_id=fid,image_path=frame['path'],image_sha256=frame['sha256'],raw_proposals=len(boxes),objectness_pass=len(valid),nms_survivors=len(allkeep),top100=len(keep),final_count=len(final),final_windows=sum(x['label']=='窗户' for x in final),
      spatial_window_proposals_iou05=len(near),spatial_window_proposals_iou03=len(near03),window_proposal_stages=stages,best_raw_roi=best_raw,best_post_nms_roi=best_kept,highest_window_score_on_roi=record(candidates[0]) if candidates else None,
      original_labels_boxes_exact=shape_match,max_original_score_error=delta,seconds=time.time()-start)
  save(dest/'summary.json',summary);summaries.append(summary);state['frames']=summaries;save(OUT/'run.json',state)
  print(json.dumps(summary,ensure_ascii=False),flush=True)
  # Interactive SVG evidence overlay: original JPEG bytes remain unchanged.
  bg='data:image/jpeg;base64,'+base64.b64encode(Path(frame['path']).read_bytes()).decode();show=[best_raw]+([best_kept] if best_kept else [])
  svg=f'<svg viewBox="0 0 {w} {h}"><image href="{bg}" width="{w}" height="{h}"/>'
  for box,color in [(roi,'lime')]+[(np.array(z['box_xyxy']),c) for z,c in zip(show,['red','cyan'])]:
   x1,y1,x2,y2=box;svg+=f'<rect x="{x1}" y="{y1}" width="{x2-x1}" height="{y2-y1}" fill="none" stroke="{color}" stroke-width="2"/>'
  svg+='</svg>';cards.append(f'<section><h2>{sid} frame {fid}</h2>{svg}<pre>{html.escape(json.dumps(summary,ensure_ascii=False,indent=2))}</pre><details><summary>Window candidate details</summary><pre>{html.escape(json.dumps(diag,ensure_ascii=False,indent=2))}</pre></details></section>')
state.update(status='success',all_original_labels_boxes_exact=all(s['original_labels_boxes_exact'] for s in summaries),max_original_score_error=max(s['max_original_score_error'] or 0 for s in summaries));save(OUT/'run.json',state)
save(OUT/'summary.json',summaries)
(OUT/'evidence.html').write_text('<!doctype html><meta charset="utf-8"><title>WeDetect window diagnostic</title><style>body{font:15px system-ui;margin:24px}main{display:grid;grid-template-columns:1fr 1fr;gap:20px}svg{width:100%}pre{white-space:pre-wrap}section{border:1px solid #aaa;padding:12px}</style><h1>WeDetect window proposals: study0</h1><p>Green: approximate diagnostic window ROI; red: best raw proposal by IoU; cyan: best proposal after NMS/top100. ROI is not detector input.</p><main>'+''.join(cards)+'</main>')
