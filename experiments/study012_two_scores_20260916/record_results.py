import json,csv,time,hashlib,math
from pathlib import Path
H=Path(__file__).resolve().parent

def read(p):return json.loads(p.read_text())
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def union_length(intervals):
 total=0;end=-math.inf
 for a,b in sorted(intervals):
  if b>end:total+=b-max(a,end);end=b
 return total
allresults=[]
for case in ['study0','study1','study2']:
 o=H/case
 if not (o/'spatial.json').exists():continue
 p=read(o/'presence.json');s=read(o/'spatial.json');m=read(o/'matching.json');inputs=[read(o/'inputs'/f'{sid}.json') for sid in ['shot1','shot3']];graphs=[read(o/'selected'/f'{sid}_scene.json') for sid in ['shot1','shot3']];names={e['entity_id']:e['name'] for g in graphs for e in g['entities']};groups={g['group_id']:g for g in m['groups']}
 expected_population=[r['group_id'] for r in p['groups'] if r['partition']=='common_static' and r['joint_presence_reasonable']]
 if s['population_group_ids']!=expected_population:continue
 def label(gid):return ' / '.join(dict.fromkeys(names[eid] for eid in groups[gid]['a_ids']+groups[gid]['b_ids']))
 calls=[];sums=dict(input_tokens=0,cached_input_tokens=0,cache_write_input_tokens=0,output_tokens=0,reasoning_output_tokens=0)
 for q in sorted((o/'calls').glob('*/status.json')):
  d=read(q);usage=d.get('usage',d.get('known_usage',[]));tot={k:sum(u.get(k,0) for u in usage) for k in sums}
  for k in sums:sums[k]+=tot[k]
  calls.append(dict(stage=q.parent.name,status=d['status'],started=d['started'],seconds=d['seconds'],**tot))
 sums['total_tokens']=sums['input_tokens']+sums['output_tokens'];stages=[]
 for d in read(o/'gpu_runtime.json')['stages']:stages.append(dict(stage=d['shot']+'_'+d['script'],started=d['started'],seconds=d['seconds'],success=d['returncode']==0,kind='gpu_geometry_or_boxer'))
 d=read(o/'matching_gpu_runtime.json');stages.append(dict(stage='RoMaV2_all_36_frame_pairs',started=d['started'],seconds=d['seconds'],success=d['returncode']==0,kind='gpu_keypoints'))
 for d in calls:stages.append(dict(stage=d['stage'],started=d['started'],seconds=d['seconds'],success=d['status']=='success',kind='codex_cli'))
 # CPU parent wrappers include API calls, so count only pure lift/fit here.
 for d in read(o/'cpu_runtime.json')['stages']:
  if d['stage'] in ['lift','registration']:stages.append(dict(stage=d['stage'],started=d['started'],seconds=d['seconds'],success=d['returncode']==0,kind='cpu_geometry'))
 successful=[d for d in stages if d['success']];intervals=[(d['started'],d['started']+d['seconds']) for d in successful]
 runtime=dict(successful_stage_seconds_sum=sum(d['seconds'] for d in successful),parallel_aware_active_seconds=union_length(intervals),case_wall_span_seconds=s.get('evaluation_completed_at',(o/'spatial.json').stat().st_mtime)-min(a for a,b in intervals),definition='successful new stages only; wall span includes scheduling/development gaps; stage sum double-counts overlapping stages; reused stages excluded',stages=stages)
 failures=[]
 for q in sorted(set(o.glob('attempt*_runtime.json'))|set(o.glob('attempt*_gpu_runtime.json'))):
  d=read(q)
  if d.get('returncode',1)!=0:failures.append(dict(path=str(q),record=d))
 runtime['archived_attempts']=failures
 audit=dict(frame_sha256_unchanged=True,all_6_frames_each_shot=True,isolated_motion_and_relation_calls=True,all_unordered_pairs_once=True,negative_only_cross_review=True,prompt_review_required_for_every_conflict=True)
 for src in inputs:
  assert len(src['frames'])==6
  for f in src['frames']:assert sha(Path(f['path']))==f['sha256']
 for d in calls:
  req=read(o/'calls'/d['stage']/'request.json');stage=d['stage']
  if stage.startswith(('motion_','observe_')):
   sid=stage.split('_',1)[1];assert len(req['images'])==6 and all(f['shot_id']==sid for f in req['images'])
  else:assert len(req['images'])==12
 n=len(s['population_group_ids']);assert set(s['population_group_ids'])==set(expected_population);assert len(s['relations'])==n*(n-1)//2;assert len({tuple(sorted(r['endpoint_groups'])) for r in s['relations']})==len(s['relations'])
 for r in s['relations']:
  if r['status']=='conflict':assert r['cosine']<0 and r['visual_gate_pass'] and r['prompt_gate_pass'] and r['verification']['prompt_motion_review']['verdict']=='does_not_explain_change'
  if r['cosine'] is None or r['cosine']>=0:assert 'verification' not in r and r['status']=='unknown'
 presence_conflicts=[dict(group_id=r['group_id'],entity=label(r['group_id']),kind=r['conflict_kind'],reasons=r['reason']) for r in p['groups'] if r['status']=='conflict']
 spatial_conflicts=[dict(relation_id=r['relation_id'],entities=[label(k) for k in r['endpoint_groups']],cosine=r['cosine'],reason=r['verification']['reason'],prompt_motion_review=r['verification']['prompt_motion_review']) for r in s['relations'] if r['status']=='conflict']
 result=dict(case=case,static_counts={g['shot_id']:g['counts']['static'] for g in graphs},presence=p['summary'],spatial=s['summary'],presence_conflicts=presence_conflicts,spatial_conflicts=spatial_conflicts,negative_proposals=s['negative_proposals'],cross_reviewed=s['support_pass'],tokens=sums,runtime=runtime,audit=audit,reuse=read(o/'reuse.json'));save(o/'result.json',result);save(o/'usage.json',dict(totals=sums,calls=calls));save(o/'audit.json',audit);allresults.append(result)
 with (o/'all_pairs.csv').open('w') as f:
  w=csv.writer(f);w.writerow(['relation_id','entity_a','entity_b','cosine','angle_deg','status','reason'])
  for r in s['relations']:w.writerow([r['relation_id'],*[label(k) for k in r['endpoint_groups']],r['cosine'],r['angle_deg'],r['status'],r['reason']])
 lines=[f'# {case}: Shot1–Shot3 双分数评测','',f"静止实体一致性：{p['summary']}。",f"空间关系一致性：{s['summary']}。",'',f"实际新调用 token：{sums}。",f"成功阶段累计耗时 {runtime['successful_stage_seconds_sum']:.1f} 秒；并行去重活跃耗时 {runtime['parallel_aware_active_seconds']:.1f} 秒；整组墙钟跨度 {runtime['case_wall_span_seconds']:.1f} 秒。",'检测、聚类、GeoCalib 重力复用；上述时间和 token 不含其历史成本。失败/安全检查拒绝记录另见 result.json。','', '## 存在性分类','', '| 实体 | 分支 | 原因类别 | 状态 | 说明 |','|---|---|---|---|---|']
 for r in p['groups']:lines.append('| '+' | '.join(str(x).replace('|','/').replace('\n',' ') for x in [label(r['group_id']),r['partition'],r['cause'],r['status'],'；'.join(r['reason'])])+' |')
 lines+=['','## 空间关系','',f"合理共同出现实体 {n} 个；全部无序实体对 {len(s['relations'])} 对；负 cosine {s['negative_proposals']} 对；通过共同支撑筛查并跨 shot 复核 {s['support_pass']} 对。",'非负值不额外复核；参考端点/支撑不足保持未知。完整数值见 all_pairs.csv；确认冲突按实体对只扣一次。','']
 for r in spatial_conflicts:lines.extend([f"- {' ↔ '.join(r['entities'])}：cosine={r['cosine']:.6f}。{r['reason']}",f"  Prompt 因果复核：{r['prompt_motion_review']['causal_explanation_of_observed_relation_change']}"])
 lines+=['','## 实际执行流程','','1. 复用冻结 WeDetect 候选、独立单 shot 聚类、原图重力估计；核对 SHA-256。','2. 每个 shot 的六帧分别做 Pi3X 相机姿态/深度重建，在固定 Z-up 场景系中逐帧用深度约束 Boxer 预测全部框。','3. 新的独立 Codex 单 shot 动静判断；静止实体融合固定框，其他实体保留代表框及逐帧轨迹。','4. 新跨 shot 静态身份对应，并在看 cosine 之前冻结结构配准参照与局部支撑参照。','5. 两个独立存在性判断读取两 shot 原图、动静清单及正常剧情 Prompt；同意且证据门通过才计分。','6. RoMaV2 对全部 6×6 原帧配对；置信度/双向循环/同一结构区域过滤，按各帧深度和相机姿态提升到场景系。','7. 仅用训练关键点求带重力约束的正尺度、偏航角和平移，按对称重投影误差稳健拟合；空间留出点只诊断。','8. 对合理共同出现的全部无序实体对，在 Shot1 场景系中算相对中心向量 cosine；负值进入筛查。','9. 两次独立单 shot 局部支撑和顺序取证；通过支撑筛查后跨 shot 原帧复核，并强制检查 Prompt 运动是否解释变化。','10. 分别汇总两个分数、覆盖率、未知/豁免和扣分台账；审计所有调用的实际 token。']
 (o/'REPORT.md').write_text('\n'.join(lines)+'\n')
save(H/'summary.json',allresults)
print(json.dumps([{k:r[k] for k in ['case','presence','spatial','presence_conflicts','spatial_conflicts','tokens']} for r in allresults],ensure_ascii=False,indent=2))
