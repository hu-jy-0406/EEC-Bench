#!/usr/bin/env python3
"""Compare every pair of seed trials, including class-aware box/mask matching."""
import argparse,hashlib,itertools,json
from collections import Counter
from functools import lru_cache
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.optimize import linear_sum_assignment
p=argparse.ArgumentParser();p.add_argument('--batch',type=Path,required=True);p.add_argument('--models',nargs='+',choices=['yoloe','florence'],default=['yoloe','florence']);a=p.parse_args();root=a.batch.resolve()
batch=json.loads((root/'batch.json').read_text())
@lru_cache(maxsize=None)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def iou(x,y):
 ix=max(0,min(x[2],y[2])-max(x[0],y[0]));iy=max(0,min(x[3],y[3])-max(x[1],y[1]));inter=ix*iy
 return inter/((x[2]-x[0])*(x[3]-x[1])+(y[2]-y[0])*(y[3]-y[1])-inter)
summary={};details=[];manifest=[]
for model in a.models:
 trials=[r for r in batch['runs'] if r['model']==model];loaded={};common=None
 assert len(trials)==5 and [r['seed'] for r in trials]==[0,1,42,2026,0]
 assert all(r['status']=='success' for r in trials)
 for t in trials:
  run=json.loads((root/t['name']/'run.json').read_text());assert run['status']=='success' and len(run['results'])==18
  sig={k:run[k] for k in ['frames','weight_hashes','script_sha256','packages','host','device_name']}
  config={k:v for k,v in run['config'].items() if k not in ['seed','output']};sig['config']=config
  assert common is None or sig==common;common=sig
  assert run['config']['seed']==t['seed']
  rows={}
  for fr in run['frames']:
   directory=root/t['name']/fr['shot']/f"frame_{fr['frame_id']:06d}"
   d=json.loads((directory/'detections.json').read_text());assert d['sha256']==fr['sha256']==sha(Path(fr['path']))
   assert d['shot']==fr['shot'] and d['frame_id']==fr['frame_id']
   w,h=d['image_size']
   for obj in d['detections']:
    x1,y1,x2,y2=obj['box_xyxy'];assert 0<=x1<x2<=w and 0<=y1<y2<=h
    if model=='yoloe':
     mask=Image.open(directory/obj['mask']);assert mask.size==(w,h) and mask.getbbox()
   if model=='florence':assert not json.loads((directory/'generation.json').read_text())['potentially_truncated']
   rows[(fr['shot'],fr['frame_id'])]=(d,directory)
  loaded[t['name']]=rows
  manifest.append(dict(name=t['name'],seed=t['seed'],model=model,frame_counts=[len(d['detections']) for d,_ in rows.values()],total=sum(len(d['detections']) for d,_ in rows.values()),run_sha256=sha(root/t['name']/'run.json')))
 pairs=[]
 for ta,tb in itertools.combinations(trials,2):
  namea,nameb=ta['name'],tb['name'];rows=[]
  for key,(da,pa) in loaded[namea].items():
   db,pb=loaded[nameb][key];aa,bb=da['detections'],db['detections']
   row=dict(model=model,a=namea,b=nameb,shot=key[0],frame_id=key[1],count_a=len(aa),count_b=len(bb),
            label_multiset_equal=Counter(x['label'] for x in aa)==Counter(x['label'] for x in bb),
            ordered_detections_exact=aa==bb,matched=0,unmatched_a=0,unmatched_b=0,min_matched_box_iou=1.,max_box_delta_px=0.,max_score_delta=0.,mask_changed_pairs=0,max_mask_pixel_difference=0,min_mask_iou=1.)
   for label in set(x['label'] for x in aa+bb):
    ca=[x for x in aa if x['label']==label];cb=[x for x in bb if x['label']==label]
    matrix=np.array([[iou(x['box_xyxy'],y['box_xyxy']) for y in cb] for x in ca]).reshape(len(ca),len(cb))
    ii,jj=linear_sum_assignment(-matrix);matches=[(i,j) for i,j in zip(ii,jj) if matrix[i,j]>=.5]
    row['matched']+=len(matches);row['unmatched_a']+=len(ca)-len(matches);row['unmatched_b']+=len(cb)-len(matches)
    for i,j in matches:
     x,y=ca[i],cb[j];row['min_matched_box_iou']=min(row['min_matched_box_iou'],float(matrix[i,j]));row['max_box_delta_px']=max(row['max_box_delta_px'],max(abs(u-v) for u,v in zip(x['box_xyxy'],y['box_xyxy'])))
     if x['score'] is not None:row['max_score_delta']=max(row['max_score_delta'],abs(x['score']-y['score']))
     if model=='yoloe' and sha(pa/x['mask'])!=sha(pb/y['mask']):
      mx=np.array(Image.open(pa/x['mask']))>0;my=np.array(Image.open(pb/y['mask']))>0;diff=int(np.count_nonzero(mx!=my));row['mask_changed_pairs']+=int(diff>0);row['max_mask_pixel_difference']=max(row['max_mask_pixel_difference'],diff);row['min_mask_iou']=min(row['min_mask_iou'],float(np.count_nonzero(mx&my)/np.count_nonzero(mx|my)))
   if model=='florence':row['raw_generation_exact']=(pa/'raw_generation.txt').read_text()==(pb/'raw_generation.txt').read_text()
   rows.append(row)
  details.extend(rows)
  pairs.append(dict(a=namea,b=nameb,frames=18,exact_detection_frames=sum(r['ordered_detections_exact'] for r in rows),label_equal_frames=sum(r['label_multiset_equal'] for r in rows),unmatched=sum(r['unmatched_a']+r['unmatched_b'] for r in rows),max_box_delta_px=max(r['max_box_delta_px'] for r in rows),min_box_iou=min(r['min_matched_box_iou'] for r in rows),max_score_delta=max(r['max_score_delta'] for r in rows),mask_changed_pairs=sum(r['mask_changed_pairs'] for r in rows),max_mask_pixel_difference=max(r['max_mask_pixel_difference'] for r in rows),raw_equal_frames=sum(r.get('raw_generation_exact',False) for r in rows) if model=='florence' else None))
 summary[model]=pairs
(root/'comparison.json').write_text(json.dumps(dict(trials=manifest,pairs=summary,frames=details),indent=2))
md=['# 随机 seed 敏感性测试','', '固定模型、18 张原始帧和参数；seed=0/1/42/2026，另重复 seed=0。每次独立进程。', 'Florence 保持 do_sample=False / num_beams=3；本实验不测试随机采样解码。', '', '| 模型 | 对照 | 完全相同的检测帧 | 最大框坐标差/px | 最大分数差 | 掩码变化对数 | 未匹配条目 |','|---|---|---:|---:|---:|---:|---:|']
for model,pairs in summary.items():
 for r in pairs:md.append(f"| {model} | {r['a']} vs {r['b']} | {r['exact_detection_frames']}/18 | {r['max_box_delta_px']:.9g} | {r['max_score_delta']:.9g} | {r['mask_changed_pairs']} | {r['unmatched']} |")
md.extend(['','精确比较使用完整有序检测列表（名称、坐标、分数、局部编号）。另外以同类别最大 IoU 匹配，IoU≥0.5 计为对应；掩码先比较 PNG 哈希，哈希不同时比较实际像素。时间、输出路径等运行元数据不计入预测差异。','', '所有 trial 校验成功状态、18帧覆盖、输入SHA256、相同模型/代码/依赖/配置、框范围、非空原尺寸掩码及 Florence 未截断。没有人工真值，此测试衡量复现稳定性，不衡量检测正确率。'])
(root/'comparison.md').write_text('\n'.join(md)+'\n')
print(json.dumps(dict(trials=manifest,pairs=summary),indent=2))
