"""Audit and summarize only this full fresh run; no historical results as inputs."""
import csv,hashlib,json,math
from pathlib import Path
H=Path(__file__).resolve().parent;O=H/'study2';B=H.parents[1]
def read(p):return json.loads(p.read_text())
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
runtime=read(O/'pipeline_runtime.json');assert runtime['status']=='success'
detection=read(O/'entities/run.json');assert detection['status']=='success' and detection['detector_mode']=='fresh'
presence=read(O/'presence.json');spatial=read(O/'spatial.json');matching=read(O/'matching.json');initial=read(O/'matching_initial.json');review=read(O/'identity_review.json')
inputs=[read(O/'inputs'/f'{s}.json') for s in ['shot1','shot3']];graphs=[read(O/'selected'/f'{s}_scene.json') for s in ['shot1','shot3']]
names={e['entity_id']:e['name'] for g in graphs for e in g['entities']};groups={g['group_id']:g for g in matching['groups']};oldgroups={g['group_id']:g for g in initial['groups']}
def label(gid):return ' / '.join(dict.fromkeys(names[e] for e in groups[gid]['a_ids']+groups[gid]['b_ids']))
counts={g['shot_id']:dict(entities=len(g['entities']),static=sum(e['motion_status']=='static' for e in g['entities']),moving=sum(e['motion_status']=='moving' for e in g['entities']),unknown=sum(e['motion_status']=='unknown' for e in g['entities'])) for g in graphs}
calls=[]
for path in list((O/'entities/shots').glob('*/status.json'))+list((O/'calls').glob('*/status.json')):
 d=read(path);request=read(path.parent/'request.json');iscluster='entities/shots' in str(path);assert d['status']=='success'
 assert not d.get('reused_from');assert d['started']>=runtime['started']
 if iscluster:
  assert request['model']=='gpt-6-astra' and request['reasoning']=='medium'
 else:assert d['model']=='gpt-6-astra' and d['reasoning']=='medium'
 command=request['command'];assert '--ignore-user-config' in command and '--ephemeral' in command
 assert command[command.index('--model')+1]=='gpt-6-astra' and 'model_reasoning_effort="medium"' in command
 usage=d.get('usage',[]);tot={key:sum(u.get(key,0) for u in usage) for key in ['input_tokens','output_tokens','cached_input_tokens']};tot['total_tokens']=tot['input_tokens']+tot['output_tokens']
 end=d.get('ended',d.get('finished'));calls.append(dict(stage=('clustering_' if iscluster else '')+path.parent.name,started=d['started'],ended=end,seconds=end-d['started'],model='gpt-6-astra',reasoning='medium',**tot,evidence=str(path)))
 if iscluster:
  payload=read(path.parent/'input.json');assert payload['shot_id']==path.parent.name
 elif path.parent.name.startswith(('motion_','observe_')):
  sid=path.parent.name.split('_',1)[1];assert len(request['images'])==6 and all(f['shot_id']==sid for f in request['images'])
calls.sort(key=lambda x:x['started']);totals={k:sum(c[k] for c in calls) for k in ['input_tokens','output_tokens','cached_input_tokens','total_tokens']};totals['calls']=len(calls)
stages=[]
def append_stage(name,seconds,selected,detail):
 cs=[c for c in calls if c['stage'] in selected];stages.append(dict(stage=name,seconds=seconds,calls=len(cs),**{k:sum(c[k] for c in cs) for k in ['input_tokens','output_tokens','cached_input_tokens','total_tokens']},detail=detail))
append_stage('WeDetect-Anything',detection['review_started']-detection['started'],[], '12 original JPEGs; includes GPU checks, model loading, inference, validation and detection visualization')
append_stage('Codex independent shot clustering',detection['review_finished']-detection['review_started'],['clustering_shot1','clustering_shot3'],'Two fresh contexts in parallel; elapsed time, not sum of calls')
mapping={'geocalib':('GeoCalib',[]),'pi3x_shot1':('Pi3X Shot1',[]),'boxer_shot1':('Boxer Shot1',[]),'pi3x_shot3':('Pi3X Shot3',[]),'boxer_shot3':('Boxer Shot3',[]),'motion_and_fusion':('Independent motion + static graph fusion',['motion_shot1','motion_shot3']),'initial_identity':('Initial cross-shot identity matching',['matching']),'roma_matches':('RoMaV2 36 frame-pair matching',[]),'lift_correspondences':('Point filtering and lifting',[]),'registration':('Gravity-constrained Sim3 registration',[]),'aligned_identity_review':('Post-alignment identity review',['identity_review']),'presence':('Presence consistency (two independent reviews)',['presence_1','presence_2']),'spatial':('Cosines + local evidence + final Prompt review',['observe_shot1','observe_shot3','verify_relations'])}
# Resolve actual presence call names from the saved run rather than assuming numbering.
for rec in runtime['stages']:
 if rec['stage']=='detection_and_clustering':continue
 title,selected=mapping[rec['stage']]
 if rec['stage']=='presence':selected=[c['stage'] for c in calls if c['stage'].startswith('presence')]
 append_stage(title,rec['seconds'],selected,'Stage process wall time including fresh model loading/checks where applicable; concurrent Codex calls are not double-counted')
assert sum(s['total_tokens'] for s in stages)==totals['total_tokens'], 'Every actual Codex call must be assigned once'
for src in inputs:
 assert len(src['frames'])==6
 for f in src['frames']:assert sha(Path(f['path']))==f['sha256']
 for side,key in [('a','shot1'),('b','shot3')]:
  if src['shot_id']!=key:continue
  assigned=[e for g in groups.values() for e in g[side+'_ids']];expected=[e['entity_id'] for graph in graphs if graph['shot_id']==key for e in graph['entities'] if e['motion_status']=='static']
  assert len(assigned)==len(set(assigned)) and set(assigned)==set(expected)
expected=[r['group_id'] for r in presence['groups'] if r['joint_presence_reasonable']];assert spatial['population_group_ids']==expected
n=len(expected);assert spatial['all_pairs']==n*(n-1)//2;assert len({tuple(sorted(r['endpoint_groups'])) for r in spatial['relations']})==spatial['all_pairs']
import numpy as np
aligned=read(O/'aligned_entities.json');coords={e['entity_id']:np.array(e['geometry']['center_world']) for shot in aligned['shots'] for e in shot['entities'] if e['geometry'] is not None}
R=np.array(spatial['registration']['rotation']);assert np.allclose(R.T@R,np.eye(3),atol=1e-8) and np.isclose(np.linalg.det(R),1) and np.allclose(R@[0,0,1],[0,0,1],atol=1e-8) and spatial['registration']['scale']>0
for r in spatial['relations']:
 a,b=[groups[k] for k in r['endpoint_groups']];va=coords[b['a_ids'][0]]-coords[a['a_ids'][0]];vb=coords[b['b_ids'][0]]-coords[a['b_ids'][0]];den=np.linalg.norm(va)*np.linalg.norm(vb)
 if r['cosine'] is not None:assert den>1e-10 and abs(float(va@vb/den)-r['cosine'])<1e-9
 if r['status']=='conflict':assert r['cosine']<0 and r['visual_gate_pass'] and r['prompt_gate_pass'] and r['verification']['prompt_motion_review']['verdict']=='does_not_explain_change'
pconf=[dict(group_id=r['group_id'],entity=label(r['group_id']),kind=r['conflict_kind'],reason=r['reason']) for r in presence['groups'] if r['status']=='conflict']
sconf=[dict(relation_id=r['relation_id'],entities=[label(k) for k in r['endpoint_groups']],cosine=r['cosine'],reason=r['verification']['reason'],prompt_motion_review=r['verification']['prompt_motion_review']) for r in spatial['relations'] if r['status']=='conflict']
changes=[dict(initial_group_id=r['initial_group_id'],entities=[names[e] for e in oldgroups[r['initial_group_id']]['a_ids']+oldgroups[r['initial_group_id']]['b_ids']],action=r['action'],result_group_ids=r['result_group_ids'],review=r) for r in review['initial_group_reviews'] if r['action']!='keep']
fit=read(O/'registration/roma_geometry/registration.json')['fits']['all_structures']
for source,expected_sha in read(O/'identity_review_sources.json').items():assert sha(Path(source))==expected_sha, 'Frozen pre-review source changed'
removed_anchors=set(initial['structural_anchor_group_ids'])-set(matching['structural_anchor_group_ids']);point_schema=read(O/'registration/roma_geometry/schema.json');removed_anchor_points={g:int(point_schema['groups'].get(str(int(g[1:])),0)) for g in sorted(removed_anchors)}
audit=dict(passed=True,no_prior_inference_outputs_reused=True,raw_images_hashes_unchanged=True,all_calls_gpt6_astra_medium=True,all_calls_new_contexts=True,independent_within_shot_clustering_motion_and_local_observation=True,static_identity_inventory_conserved=True,all_unordered_pairs_once=True,confirmed_conflicts_have_visual_and_prompt_gates=True,stage_token_sum_equals_actual_call_sum=True)
summary=dict(case='study2',shots=['shot1','shot3'],pipeline_revision='post_alignment_identity_review_v1',full_fresh_run=True,presence=presence['summary'],spatial=spatial['summary'],counts=counts,common_static=n,all_pairs=spatial['all_pairs'],negative_proposals=spatial['negative_proposals'],support_pass=spatial['support_pass'],presence_conflicts=pconf,spatial_conflicts=sconf,identity_changes=changes,removed_anchor_point_counts=removed_anchor_points,transform={k:fit[k] for k in ['scale','yaw_deg','translation','train','spatial_holdout']},tokens=totals,wall_seconds=runtime['seconds'],stages=stages,audit=audit)
save(O/'result.json',summary);save(O/'usage.json',dict(totals=totals,calls=calls));save(O/'audit.json',audit)
for filename,rows in [('stages.csv',stages),('calls.csv',calls)]:
 with (O/filename).open('w') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
with (O/'all_pairs.csv').open('w') as f:
 w=csv.writer(f);w.writerow(['relation_id','entity_a','entity_b','cosine','angle_deg','status','reason'])
 for r in spatial['relations']:w.writerow([r['relation_id'],*[label(k) for k in r['endpoint_groups']],r['cosine'],r['angle_deg'],r['status'],r['reason']])
lines=['# Study2 全流程独立重跑（Shot1 / Shot3）','','模型：所有 Codex 调用均为 `gpt-6-astra / medium`。流程：`gs-consistency-two-scores-v1 / post_alignment_identity_review_v1`。','',f"实体一致性 **{presence['summary']['score']:.2f}**；空间关系一致性 **{spatial['summary']['score']:.2f}**。",f"总墙钟耗时 **{runtime['seconds']/60:.2f} 分钟**，实际 **{len(calls)} 次** Codex 调用，**{totals['total_tokens']:,} tokens**（input {totals['input_tokens']:,} + output {totals['output_tokens']:,}；cached input {totals['cached_input_tokens']:,} 已包含在 input 中）。",'','## 从头运行范围','','原始 JPEG 直接作为输入，不重新抽帧或重新编码。WeDetect 候选、Codex 聚类、GeoCalib 重力、Pi3X 相机姿态/深度、Boxer 框、动静标签、初始匹配、RoMa 点、变换、对齐后身份复核、存在性和关系复核全部重新计算。只复用实现代码、环境、预训练权重与原始输入。原剧情 Prompt 按既有评测口径取正常剧情条款，剔除制作测试视频时写入的预期错误/答案指令；详见 narrative_provenance.json。','','## 阶段消耗','','| 阶段 | 墙钟秒 | Codex 次数 | Input tokens | Output tokens | Total tokens |','|---|---:|---:|---:|---:|---:|']
for s in stages:lines.append(f"| {s['stage']} | {s['seconds']:.2f} | {s['calls']} | {s['input_tokens']:,} | {s['output_tokens']:,} | {s['total_tokens']:,} |")
lines+=['','并行调用按阶段墙钟计时，未把两个并行调用的时间相加当作总耗时。表内GPU阶段含安全检查和模型加载；纯逐帧推理时间另见原始日志。总墙钟还包含输入组装/阶段切换；调用自身时间见 calls.csv。Token 来自 CLI 实际 usage 事件，未另行累加其子项。','','## 检出与身份复核','','```json',json.dumps(counts,ensure_ascii=False,indent=2),'```']
presence_by_id={r['group_id']:r for r in presence['groups']}
for c in changes:
 outcomes='；'.join(gid+': '+presence_by_id[gid]['status']+'/'+presence_by_id[gid]['cause'] for gid in c['result_group_ids'])
 lines.append(f"- {c['initial_group_id']}（{' / '.join(c['entities'])}）：{c['action']} → {outcomes}。")
 lines.append('  原帧身份依据：'+c['review']['visual_identity_evidence'])
lines+=['', '## 全部存在性分类', '', '| 实体组 | 实体 | 分支 | 原因类别 | 最终状态 |', '|---|---|---|---|---|']
for r in presence['groups']:lines.append('| '+' | '.join(str(x).replace('|','/').replace('\n',' ') for x in [r['group_id'],label(r['group_id']),r['partition'],r['cause'],r['status']])+' |')
lines+=['', '## 配准质量', '', f"正尺度 {fit['scale']:.9f}；yaw {fit['yaw_deg']:.6f}°；平移 {fit['translation']}（模型场景单位）。留出点对称重投影中位误差 {fit['spatial_holdout']['median_pixels']:.3f} px，5px内点比例 {100*fit['spatial_holdout']['inlier_5px']:.2f}%。全局配准仍有明显误差，坐标差仅作复核证据；冲突判定还需原帧和局部参照支持。"]
lines+=['','## 确认扣分','','### 存在性','']
for c in pconf:lines.append(f"- {c['entity']}：{c['kind']}。{'；'.join(c['reason'])}")
if not pconf:lines.append('无确认冲突。')
lines+=['','### 空间关系','',f"合理共同静态实体 {n} 个；全部无序实体对 {spatial['all_pairs']}；负 cosine {spatial['negative_proposals']}；进入最终复核 {spatial['support_pass']}。"]
for c in sconf:lines.append(f"- {' ↔ '.join(c['entities'])}：cosine = {c['cosine']:.9f}。{c['reason']}")
if not sconf:lines.append('无确认冲突，按当前规则空间分为 100；这不表示所有关系均已被证实一致。')
lines+=['',f"存在性 C/K/U/E = {presence['summary']['C']}/{presence['summary']['K']}/{presence['summary']['U']}/{presence['summary']['E']}；空间 C/K/U/E = {spatial['summary']['C']}/{spatial['summary']['K']}/{spatial['summary']['U']}/{spatial['summary']['E']}。C=确认兼容，K=确认冲突，U=未知/未确认，E=豁免。",'分数沿用 100×(1−K/(C+K+U))；空间无确认冲突即100。全部关系数值和分类见 all_pairs.csv。','','## 实际执行 Pipeline','','1. 12张原始 JPEG → 新 WeDetect 推理；两个独立 Codex 上下文分别聚类，只保留检测候选支持的实体。','2. 新 GeoCalib 重力估计；每个shot独立 Pi3X 多帧相机/深度，构建固定 Z-up 场景系；逐帧深度约束 Boxer 预测3D框。','3. 两个独立 Codex 上下文判断各shot动静；静止框融合，其他实体保留代表框和逐帧轨迹。','4. Codex 初始跨shot身份对应，确定结构参照。','5. RoMaV2 全部36帧对匹配；结构区域、置信度、循环一致性和深度筛点；重力约束正尺度+yaw+平移稳健配准。','6. 冻结变换，Codex结合全部原帧、对齐框/中心差异、反投影和Prompt逐组复核身份；拆分/修正初始对应并守恒实体清单。','7. 两次独立存在性判断；区分视角、运动、不一致，检查共同实体是否应该离开却仍出现；证据与Prompt门通过才扣分。','8. 对合理共同静态集合的每个无序实体对计算共同坐标系相对向量cosine；仅负值进入筛查。','9. 每shot独立局部支撑/顺序取证；通过门的负值进入跨shot原帧及Prompt运动复核，确认冲突按实体对扣一次。','10. 汇总两分数及逐阶段真实运行时间、实际token，检查输入哈希和调用隔离。','','## 证据索引','','- study2/result.json、usage.json、stages.csv、calls.csv：结果和消耗','- study2/entities/：新检测、独立聚类及原始CLI记录','- study2/calibration_new/、pi3x/、selected/：新重力、逐帧几何、静态图','- study2/registration/：新关键点和变换','- study2/matching_initial.json、identity_review.json、matching.json：初始/复核对应','- study2/presence.json、spatial.json、all_pairs.csv：分类、得分、全部cosine','- study2/calls/：下游所有新CLI请求/响应/usage','- code_snapshot/、run_spec.json、raw_manifest.json：代码与运行规范']
(H/'REPORT.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({k:summary[k] for k in ['presence','spatial','counts','all_pairs','negative_proposals','tokens','wall_seconds']},ensure_ascii=False,indent=2))
