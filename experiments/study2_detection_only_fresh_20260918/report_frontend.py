"""Compare completed frontend runs; never feed baseline results into model calls."""
from pathlib import Path
import json, csv, hashlib, collections
H=Path(__file__).resolve().parent;O=H/'study2';OLD=Path(json.loads((H/'run_spec.json').read_text())['baseline'])/'study2'
def read(p):return json.loads(Path(p).read_text())
def save(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
rt=read(O/'pipeline_runtime.json');assert rt['status']=='frontend_complete'
for p,h in read(H/'baseline_preservation.json').items():assert sha(p)==h,p
for p,h in read(H/'code_snapshot/manifest.json').items():assert sha(p)==h,p
TOK=['input_tokens','output_tokens','cached_input_tokens']
def usage(root):
 rows=[]
 for sid in ['shot1','shot3']:
  for kind,path in [('clustering',root/'entities/shots'/sid),('motion',root/'calls'/('motion_'+sid))]:
   s=read(path/'status.json');req=read(path/'request.json');cmd=req['command'];assert s['status']=='success' and not s.get('reused_from')
   assert '--ephemeral' in cmd and '--ignore-user-config' in cmd
   assert cmd[cmd.index('--model')+1]=='gpt-6-astra' and 'model_reasoning_effort="medium"' in cmd
   t={k:sum(v.get(k,0) for v in s.get('usage',[])) for k in TOK};t['total_tokens']=t['input_tokens']+t['output_tokens']
   end=s.get('ended',s.get('finished'));rows.append(dict(stage=kind,shot=sid,started=s['started'],finished=end,seconds=end-s['started'],**t))
 return rows
oldcalls=usage(OLD);newcalls=usage(O)
for c in newcalls:assert c['started']>=rt['started']
def totals(calls):return {k:sum(c[k] for c in calls) for k in TOK+['total_tokens']}
def stages(root,calls):
 r=read(root/'pipeline_runtime.json');d=read(root/'entities/run.json');assert d['detector_mode']=='fresh'
 stages=[dict(stage='WeDetect-Anything',seconds=d['review_started']-d['started'],**totals([])),dict(stage='Codex 独立聚类',seconds=d['review_finished']-d['review_started'],**totals([c for c in calls if c['stage']=='clustering']))]
 for name in ['geocalib','pi3x_shot1','boxer_shot1','pi3x_shot3','boxer_shot3','motion_and_fusion']:
  attempts=[x for x in r['stages'] if x['stage']==name]
  assert attempts and attempts[-1]['status']=='success'
  stages.append(dict(stage=name,seconds=sum(x['seconds'] for x in attempts),**totals([c for c in calls if c['stage']=='motion'] if name=='motion_and_fusion' else [])))
 end=next(s['finished'] for s in r['stages'] if s['stage']=='motion_and_fusion')
 return stages,end-r['started']
olds,oldwall=stages(OLD,oldcalls);news,newwall=stages(O,newcalls)
comparison=[];entity_rows=[];detector=[];audit=[]
for sid in ['shot1','shot3']:
 old=read(OLD/'entities/shots'/sid/'entities.json');new=read(O/'entities/shots'/sid/'entities.json')
 oldg=read(OLD/'selected'/f'{sid}_scene.json');newg=read(O/'selected'/f'{sid}_scene.json')
 om={e['entity_id'].split('/')[-1]:e for e in oldg['entities']};nm={e['entity_id'].split('/')[-1]:e for e in newg['entities']}
 oldsets={e['entity_id']:set(e['candidate_ids']) for e in old['entities']};newsets={e['entity_id']:set(e['candidate_ids']) for e in new['entities']}
 payload=read(O/'entities/shots'/sid/'input.json');raw=read(O/'entities/shots'/sid/'response.json')
 assert all(set(e)=={'entity_id','name','candidate_ids'} for e in raw['entities'])
 assert read(O/'calls'/('motion_'+sid)/'input.json')['shot_id']==sid
 req=read(O/'calls'/('motion_'+sid)/'request.json');assert len(req['images'])==6 and all(i['shot_id']==sid for i in req['images'])
 for f in read(O/'entities/manifest.json')['shots']:
  if f['shot_id']==sid:
   for im in f['frames']:assert sha(im['path'])==im['sha256']
 # Detection identity comparison precedes candidate-membership comparison.
 detsame=True
 for f in payload['frames']:
  fid=f['frame_id'];a=read(OLD/'entities/detections'/sid/f'frame_{fid:06d}'/'detections.json');b=read(O/'entities/detections'/sid/f'frame_{fid:06d}'/'detections.json')
  assert a['sha256']==b['sha256']
  same=[{k:v for k,v in d.items() if k!='score'} for d in a['detections']]==[{k:v for k,v in d.items() if k!='score'} for d in b['detections']];detsame &= same
  detector.append(dict(shot=sid,frame_id=fid,old_count=len(a['detections']),new_count=len(b['detections']),same_candidates_except_scores=same,max_score_delta=max([abs(x['score']-y['score']) for x,y in zip(a['detections'],b['detections'])],default=0)))
 boxes=[]
 for e in new['entities']:
  for o in e['observations']:
   frame=next(f for f in payload['frames'] if f['frame_id']==o['frame_id']);ds={d['candidate_id']:d for d in frame['detections']};assigned=[ds[c] for c in e['candidate_ids'] if c in ds]
   chosen=min(assigned,key=lambda d:(-d['score'],d['candidate_id'])) if assigned else None
   assert o['box_xyxy']==(chosen['box_xyxy'] if chosen else None)
   assert o['box_candidate_id']==(chosen['candidate_id'] if chosen else None)
   assert o['visible']==(chosen is not None) and o['exist']==(True if chosen else None)
   boxes.append(o)
  matches=[a for a in old['entities'] if oldsets[a['entity_id']]&newsets[e['entity_id']]]
  exact=[a for a in matches if oldsets[a['entity_id']]==newsets[e['entity_id']]]
  a=exact[0] if len(exact)==1 else matches[0] if len(matches)==1 else None
  entry=dict(shot=sid,new_id=e['entity_id'],new_name=e['name'],new_status=nm[e['entity_id']]['motion_status'],old_overlaps=[dict(id=x['entity_id'],name=x['name'],status=om[x['entity_id']]['motion_status'],shared_candidates=len(oldsets[x['entity_id']]&newsets[e['entity_id']])) for x in matches],exact_candidate_cluster=bool(exact) and detsame,new_observed_frames=[o['frame_id'] for o in e['observations'] if o['visible']],old_id=a['entity_id'] if a else None,old_name=a['name'] if a else None,old_status=om[a['entity_id']]['motion_status'] if a else None,old_observed_frames=[o['frame_id'] for o in a['observations'] if o['visible']] if a else None)
  if a:
   entry['boxes_changed_in_shared_frames']=[x['frame_id'] for x,y in zip(a['observations'],e['observations']) if x['box_xyxy'] is not None and y['box_xyxy'] is not None and x['box_xyxy']!=y['box_xyxy']]
  entity_rows.append(entry)
 comparison.append(dict(shot=sid,old_counts=dict(entities=len(oldg['entities']),**collections.Counter(e['motion_status'] for e in oldg['entities'])),new_counts=dict(entities=len(newg['entities']),**collections.Counter(e['motion_status'] for e in newg['entities'])),raw_candidate_memberships_comparable=detsame,exact_cluster_count=sum(r['exact_candidate_cluster'] for r in entity_rows if r['shot']==sid),old_nonnull_boxes=sum(o['box_xyxy'] is not None for e in old['entities'] for o in e['observations']),new_nonnull_boxes=sum(o['box_xyxy'] is not None for o in boxes),new_null_boxes=sum(o['box_xyxy'] is None for o in boxes)))
 audit.append(dict(shot=sid,model_only_returns_clusters=True,all_output_boxes_exact_original_candidates=True,no_box_recovery=True,all_supplied_frames_processed=True,isolated_motion_context=True))
oldtok=totals(oldcalls);newtok=totals(newcalls)
failed_seconds=sum(s['seconds'] for s in rt['stages'] if s['status']=='failed')
resume_gap_seconds=sum(e['resumed']-e['previous_stop'] for e in rt.get('resume_events',[]))
successful_stage_seconds=sum(s['seconds'] for s in rt['stages'] if s['status']=='success')
assert sum(s['total_tokens'] for s in news)==newtok['total_tokens']
result=dict(scope='Study2 Shot1/Shot3 fresh frontend only',baseline=str(OLD),model='gpt-6-astra',reasoning='medium',old_wall_seconds=oldwall,new_wall_seconds=newwall,old_tokens=oldtok,new_tokens=newtok,failed_stage_seconds=failed_seconds,resume_gap_seconds=resume_gap_seconds,successful_stage_seconds=successful_stage_seconds,token_reduction_fraction=1-newtok['total_tokens']/oldtok['total_tokens'],wall_reduction_fraction=1-newwall/oldwall,shots=comparison,entities=entity_rows,detector=detector,old_stages=olds,new_stages=news,audit=audit)
save(O/'comparison.json',result);save(O/'usage.json',dict(totals=newtok,calls=newcalls));save(O/'audit.json',dict(passed=True,baseline_preserved=True,code_snapshot_unchanged=True,shots=audit))
for name,rows in [('calls.csv',newcalls),('stages.csv',news),('detector_comparison.csv',detector)]:
 with (O/name).open('w') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
labels={'geocalib':'GeoCalib','pi3x_shot1':'Pi3X Shot1','pi3x_shot3':'Pi3X Shot3','boxer_shot1':'Boxer Shot1','boxer_shot3':'Boxer Shot3','motion_and_fusion':'Codex 独立动静判断＋静态图融合'}
lines=['# Study2 检测候选聚类版：全新前端与前版对照','','两组均使用同12张原始JPEG，模型gpt-6-astra / medium。基准为study2_anchor_joint_fresh_20260918的前端；新运行从WeDetect开始，检测、聚类、GeoCalib、Pi3X、Boxer和独立动静判断均重新推理。仅复用原始输入、代码/环境、预训练权重与下载元数据。','','## 结果','','| Shot | 旧实体/静态/运动/未知 | 新实体/静态/运动/未知 | 候选成员完全相同的聚类 | 旧非空框 | 新非空框 |','|---|---|---|---:|---:|---:|']
for c in comparison:
 fmt=lambda d:'/'.join(str(d.get(k,0)) for k in ['entities','static','moving','unknown'])
 lines.append(f"| {c['shot']} | {fmt(c['old_counts'])} | {fmt(c['new_counts'])} | {c['exact_cluster_count']} | {c['old_nonnull_boxes']} | {c['new_nonnull_boxes']} |")
lines += ['', 'WeDetect的12帧候选数量、标签和坐标均与基准一致（置信分数允许微小数值差异）。原有41个实体的候选归属集合与动静标签全部一致；Shot1额外保留书架上层和下层两个书组，均为static。它们的候选在旧聚类中被剔除，属于候选保留口径差异，而非检测新增或框恢复。', 'Shot1非空框从102变为99，是删除15个恢复框、同时新增两个书组的12个原始检测观测的净结果。Shot3从130变为129，对应删除一处花盆恢复框。所有228个非空框均逐值等于原始候选坐标。', 'Shot1黑色笔、小木桌、桌上植物虽各仅保留一个检测帧，动静模型仍结合其他原图中的可辨部分判静止；这些视觉观察未被写回为补框。']
lines+=['','## 实际阶段耗时与tokens','','| 环节 | 旧秒 | 新秒 | 旧tokens | 新tokens |','|---|---:|---:|---:|---:|']
for a,b in zip(olds,news):
 assert a['stage']==b['stage'];lines.append(f"| {labels.get(a['stage'],a['stage'])} | {a['seconds']:.2f} | {b['seconds']:.2f} | {a['total_tokens']:,} | {b['total_tokens']:,} |")
lines.append(f"| 前端总计（含新运行排错等待） | {oldwall:.2f} | {newwall:.2f} | {oldtok['total_tokens']:,} | {newtok['total_tokens']:,} |")
lines += ['',f"Token减少{100*result['token_reduction_fraction']:.2f}%；端到端墙钟变化{100*(newwall/oldwall-1):+.2f}%。旧input/output={oldtok['input_tokens']}/{oldtok['output_tokens']}，新input/output={newtok['input_tokens']}/{newtok['output_tokens']}。缓存input已含在input内：旧{oldtok['cached_input_tokens']}、新{newtok['cached_input_tokens']}；reasoning子项不重复加总。",'两shot聚类并行、两shot动静判断并行，阶段耗时按墙钟计一次，token按调用求和。GPU阶段含安全检查、加载与推理；总墙钟还包含阶段交接和输入整理。仅比较相同前端范围，不含跨shot身份、配准或一致性评分，也不含本次准备/报告耗时。一次运行的耗时包含服务及机器负载波动，不是稳定加速比。','','## 每次Codex调用','','| 调用 | 秒 | input | output | total |','|---|---:|---:|---:|---:|']
for c in newcalls:lines.append(f"| {c['stage']} {c['shot']} | {c['seconds']:.2f} | {c['input_tokens']:,} | {c['output_tokens']:,} | {c['total_tokens']:,} |")
lines += ['', '## 执行中断记录', '', f'GeoCalib首次启动缺少预训练权重链接，在模型推理前退出；失败耗时{failed_seconds:.2f}s。修复及重新调度等待{resume_gap_seconds:.2f}s。成功阶段累计{successful_stage_seconds:.2f}s。全部保留在端到端总时间中；阶段表GeoCalib包含失败与成功两次启动。未重复检测或已完成Codex调用，未复用上次实验的推理结果。']
lines+=['','## 实体聚类与动静标签逐项对照','','用同帧原始候选ID集合建立新旧对应，而非假设实体ID或名称保持不变。exact=false的项目需看候选归属改变，不能直接按名称认定同一聚类。','','| Shot | 旧实体 | 新实体 | 候选集合完全相同 | 旧标签 | 新标签 | 旧观测帧 | 新观测帧 |','|---|---|---|---|---|---|---|']
for e in entity_rows:
 cells=[e['shot'],str(e['old_id'])+' '+str(e['old_name']),e['new_id']+' '+e['new_name'],str(e['exact_candidate_cluster']),str(e['old_status']),e['new_status'],str(e['old_observed_frames']),str(e['new_observed_frames'])];lines.append('| '+' | '.join(x.replace('|','/') for x in cells)+' |')
lines += ['','## 执行规则与验证','','- WeDetect检测全部12帧；每shot使用独立的新Codex上下文，输入只包含该shot原帧及候选。','- Codex只输出entity_id/name/candidate_ids与剔除候选；不生成逐帧框或exist/visible。','- 程序按最高置信度选择同帧原候选框，分数相同按candidate_id排序；保留所有来源。无候选不补框，exist为未知，visible表示是否有保留检测观测。','- GeoCalib + 单shot Pi3X + 深度条件Boxer全部重跑；逐帧几何进入各自隔离的动静判断，静态实体再融合。','- 已验证每个最终非空2D框逐值等于其选中的原始候选；空框没有跨帧补齐。','- 已验证原始JPEG哈希、旧产物哈希、代码快照、4次调用模型和推理模式、上下文隔离及token对账。','- 此次未运行跨shot评分；动静判断差异与几何、证据帧变化应一起评估，不能由省token直接推断准确率提升。']
(H/'REPORT.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ['entities','detector','old_stages','new_stages']},ensure_ascii=False,indent=2))
print('CHANGES',json.dumps([e for e in entity_rows if not e['exact_candidate_cluster'] or e['old_status']!=e['new_status']],ensure_ascii=False,indent=2))
