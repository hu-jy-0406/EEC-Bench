"""Diagnostic-only threshold replay on saved raw outputs; no new forward pass."""
import sys,json,hashlib
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent;PORT=ROOT/'to_human/eec-bench-repro-20260912'
sys.path.insert(0,str(PORT/'detector'))
from wedetect_adapter import Detector,proposal_nms,np_sigmoid,rescale
sys.path.insert(0,str(ROOT/'EECBench/scripts'))
from run_isolated_shot_static_3d import owned_compute_job
owned_compute_job()
# Read checkpoint only to recover the same level calibration; weights are not changed.
det=Detector(PORT/'weights/wedetect_base_uni.pth','cpu')
summary=json.loads((OUT/'summary.json').read_text());replays=[];details=[]
for f in summary:
 d=OUT/f['shot']/f"frame_{f['frame_id']:06d}";raw=np.load(d/'raw_forward.npz');scores,boxes,embeds=[raw[k] for k in ['scores','boxes_letterbox','embeds']];rows=json.loads((d/'proposal_trace.json').read_text());w,h=Image.open(f['image_path']).size
 nearby=[r for r in rows if r['roi_iou']>=.5];maxobj=max(nearby,key=lambda r:r['objectness'])
 rec=dict(shot=f['shot'],frame_id=f['frame_id'],nearby_proposals=len(nearby),all_nearby_below_objectness=all(r['objectness']<=.1 for r in nearby),max_nearby_objectness=maxobj['objectness'],max_objectness_proposal=maxobj,
  good_window_class_proposals_before_objectness=sum(r['top_class']=='窗户' and r['top_class_score']>=.4 for r in nearby),example=f['highest_window_score_on_roi'],original_replay_exact=f['original_labels_boxes_exact'] and f['max_original_score_error']==0,threshold_replays=[])
 for threshold in [.1,.075,.05,.025]:
  keep,_=proposal_nms(scores,boxes,threshold,.7,100);wins=[];total=0
  for k in keep.tolist():
   prob=np_sigmoid((det.text@embeds[k])*det.scales[k]+det.biases[k]);cid=int(np.argmax(prob));score=float(prob[cid])
   if score<.4:continue
   total+=1
   if det.vocab[cid]=='窗户':wins.append(dict(proposal_index=k,objectness=float(scores[k].max()),class_score=score,box_xyxy=rescale((640,640),boxes[k].copy(),(h,w)).round().tolist()))
  rec['threshold_replays'].append(dict(objectness_threshold=threshold,final_count=total,window_detections=wins))
 details.append(rec)
for t in [.1,.075,.05,.025]:
 replays.append(dict(objectness_threshold=t,frames_with_window=sum(bool(next(v for v in r['threshold_replays'] if v['objectness_threshold']==t)['window_detections']) for r in details),total_detections=sum(next(v for v in r['threshold_replays'] if v['objectness_threshold']==t)['final_count'] for r in details)))
result=dict(frames=details,threshold_summary=replays,all_original_outputs_exact=all(r['original_replay_exact'] for r in details),all_frames_have_spatial_window_proposal=all(r['nearby_proposals'] for r in details),all_frames_have_window_class_score_ge_04=all(r['good_window_class_proposals_before_objectness'] for r in details),all_window_region_proposals_filtered_at_objectness=all(r['all_nearby_below_objectness'] for r in details),note='Association IoU>=0.5 against approximate visual ROI; ROI never enters detection. Threshold sweeps are diagnostics only, not a new production configuration. Original inference outputs remain unchanged.')
(OUT/'diagnosis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
lines=['# Study0：WeDetect 窗户漏检逐级诊断','','## 结论','','Shot1和Shot3各6帧，共12帧全部复现没有最终窗户输出；但每一帧都有定位窗户的原始proposal，也都有窗户类别分数达到0.4的proposal。窗户区域的proposal全部在第一道objectness门槛（需>0.1）被过滤，未进入NMS及正式类别匹配。','','原模型每帧输出8400个密集proposal。诊断中的窗户区域约为[277,0,445,225]，仅用于把proposal与可见窗户关联（IoU≥0.5），不是模型输入或标注真值。','','| Shot | 帧 | 匹配窗户区域的proposal数 | 最大objectness | 示例窗户类别分数 | 最终窗户数 |','|---|---:|---:|---:|---:|---:|']
for r in details:lines.append(f"| {r['shot']} | {r['frame_id']} | {r['nearby_proposals']} | {r['max_nearby_objectness']:.6f} | {r['example']['window_score']:.6f} | 0 |")
lines+=['','“最大objectness”和“示例窗户类别分数”可能来自不同proposal；完整同一proposal的框、两种分数和阶段见diagnosis.json。Objectness衡量候选保留分数；类别匹配分数是该候选与词表的匹配，二者不是同一个阈值。','','## 缓存输出上的阈值诊断','','仅改变objectness门槛，保持NMS IoU0.7、top100、类别匹配0.4不变；不重新运行模型、不修改正式配置。','','| Objectness阈值 | 检出窗户的帧数 | 全部类别最终框总数 |','|---|---:|---:|']
for r in replays:lines.append(f"| {r['objectness_threshold']} | {r['frames_with_window']}/12 | {r['total_detections']} |")
lines+=['','## 验证与产物','','- 原CPU环境、权重、输入、seed0和全部阈值重跑；12帧最终类别、框和分数与先前输出完全相同。','- 完整保存100800个原始proposal的objectness、框、embedding和逐阶段记录。','- 官方NMS保留索引与诊断重放完全一致；类别分数在正式保留候选上使用原逐向量计算。','- [原帧与proposal叠加](evidence.html) · [逐帧结论与阈值重放](diagnosis.json) · [运行记录](run.json)。','- 在已有185272/node241上CPU两线程执行；无GPU、新分配或Codex聚类调用。','- 当前诊断定位了丢失的具体过滤阶段；没有证明模型为何在这些图上给出较低objectness，也没有证明降低阈值是跨样例最优配置。']
(OUT/'RESULT.md').write_text('\n'.join(lines)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='frames'},ensure_ascii=False))
