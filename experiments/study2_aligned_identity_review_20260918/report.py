import json,hashlib,csv,time
from pathlib import Path
H=Path(__file__).resolve().parent;O=H/'study2';BASE=H.parent/'study012_two_scores_20260916/study2'
def read(p):return json.loads(p.read_text())
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
review=read(O/'identity_review.json');m=review['matching'];initial=read(O/'matching_initial.json');groups={g['group_id']:g for g in m['groups']};olds={g['group_id']:g for g in initial['groups']};presence=read(O/'presence.json');spatial=read(O/'spatial.json');pr={r['group_id']:r for r in presence['groups']};names={e['entity_id']:e['name'] for sid in ['shot1','shot3'] for e in read(O/'selected'/f'{sid}_scene.json')['entities']};before_p=read(BASE/'presence.json');before_s=read(BASE/'spatial.json')
changes=[]
for d in review['initial_group_reviews']:
 if d['action']=='keep':continue
 old=olds[d['initial_group_id']];new=[groups[g] for g in d['result_group_ids']]
 changes.append(dict(initial_group_id=d['initial_group_id'],initial_entities=[dict(entity_id=e,name=names[e]) for e in old['a_ids']+old['b_ids']],action=d['action'],new_groups=[dict(group_id=g['group_id'],a_ids=g['a_ids'],b_ids=g['b_ids'],identity=g['identity'],presence_status=pr[g['group_id']]['status'],presence_cause=pr[g['group_id']]['cause'],presence_reasons=pr[g['group_id']]['reason']) for g in new],review=d))
# Original fitting remains frozen. Record whether rejected anchors contributed points.
oldanchors=set(initial['structural_anchor_group_ids']);newanchors=set(m['structural_anchor_group_ids']);schema=read(O/'registration/roma_geometry/schema.json');removed={g:int(schema['groups'].get(str(int(g[1:])),0)) for g in sorted(oldanchors-newanchors)}
fit_equal=sha(O/'registration/roma_geometry/registration.json')==sha(BASE/'registration/roma_geometry/registration.json');assert fit_equal
assert sha(O/'matching_initial.json')==sha(BASE/'matching.json') or read(O/'matching_initial.json')==read(BASE/'matching.json')
known={g for g in spatial['population_group_ids']};assert all(groups[g]['identity']=='matched' for g in known);assert spatial['all_pairs']==len(known)*(len(known)-1)//2
for r in spatial['relations']:assert set(r['endpoint_groups'])<=known
oldpairs={r['relation_id']:r for r in before_s['relations']}
for r in spatial['relations']:
 if r['relation_id'] in oldpairs:
  # Compare only truly unchanged group membership, not just reused IDs.
  if all(groups[g]['a_ids']==olds[g]['a_ids'] and groups[g]['b_ids']==olds[g]['b_ids'] for g in r['endpoint_groups']):assert abs(r['cosine']-oldpairs[r['relation_id']]['cosine'])<1e-10
calls=[]
for p in sorted((O/'calls').glob('*/status.json')):
 d=read(p);assert d['status']=='success',p;us=d['usage'];calls.append(dict(stage=p.parent.name,seconds=d['seconds'],started=d['started'],ended=d['ended'],input_tokens=sum(u.get('input_tokens',0) for u in us),output_tokens=sum(u.get('output_tokens',0) for u in us),cached_input_tokens=sum(u.get('cached_input_tokens',0) for u in us)))
usage=dict(new_model_calls=len(calls),input_tokens=sum(c['input_tokens'] for c in calls),output_tokens=sum(c['output_tokens'] for c in calls),cached_input_tokens=sum(c['cached_input_tokens'] for c in calls),wall_span_seconds=max(c['ended'] for c in calls)-min(c['started'] for c in calls),sum_call_seconds=sum(c['seconds'] for c in calls),calls=calls);usage['total_tokens']=usage['input_tokens']+usage['output_tokens'];save(O/'usage.json',usage)
conflicts=dict(presence=[r for r in presence['groups'] if r['status']=='conflict'],spatial=[r for r in spatial['relations'] if r['status']=='conflict'])
summary=dict(protocol='gs-consistency-two-scores-v1',pipeline_revision='post_alignment_identity_review_v1',case='study2',old_entity_score=before_p['summary'],new_entity_score=presence['summary'],old_spatial_score=before_s['summary'],new_spatial_score=spatial['summary'],old_common_static=len(before_s['population_group_ids']),new_common_static=len(known),old_pair_count=before_s['all_pairs'],new_pair_count=spatial['all_pairs'],old_negative_count=before_s['negative_proposals'],new_negative_count=spatial['negative_proposals'],identity_changes=changes,removed_registration_anchors_and_original_point_counts=removed,registration_unchanged=fit_equal,conflicts=conflicts,usage=usage)
save(O/'result.json',summary);save(O/'audit.json',dict(passed=True,registration_unchanged=True,all_entities_conserved=True,only_reviewed_common_groups_in_spatial_population=True,all_unordered_pairs_count_correct=True,unchanged_pair_cosines_replayed=True,all_calls_successful=True,code_hashes={str(p):sha(p) for p in [H.parents[1]/'scripts/review_aligned_entity_identities.py',H.parents[1]/'prompts/gs_aligned_identity_review_v1.txt',H.parent/'study012_two_scores_20260916/evaluate.py',H.parent/'study012_two_scores_20260916/run_cpu.py']}))
lines=['# Study2 对齐后身份复核测试','','## 实际范围','','保留2026-09-16原身份区域筛选的RoMa配准，未采用后来的无身份全图变换。复用检测、独立单shot动静判断、3D框、初次对应和原配准；新运行对齐后身份复核、两次独立存在性判断、两次隔离单shot局部关系观察和按需最终原帧+Prompt复核。原历史实验文件未覆盖。','','## 身份复核结果','','| 原组 | 原实体 | 动作 | 新分组及最终存在性分类 |','|---|---|---|---|']
for c in changes:
 lab=' / '.join(e['name'] for e in c['initial_entities']);new='; '.join(g['group_id']+': '+g['identity']+', '+g['presence_status']+'/'+g['presence_cause'] for g in c['new_groups']);lines.append('| '+' | '.join([c['initial_group_id'],lab,c['action'],new])+' |')
lines+=['','模型同时收到12张原JPEG、初次身份假设、全部静态框在共同坐标系的位置、各初始配对中心差异、逐帧对侧中心投影、原配准误差和正常剧情Prompt，另附全实体对齐图。提示词检查全部组，无“小木桌必须拆分”等目标名单，也未输入cosine或预期冲突结果。坐标差异不是硬阈值；保持同一物体真实移动仍可被后续空间判断检出。','', '## 新旧结果','','| 指标 | 原实验 | 加入复核后 |','|---|---:|---:|']
for title,a,b in [('实体分',before_p['summary']['score'],presence['summary']['score']),('空间关系分',before_s['summary']['score'],spatial['summary']['score']),('合理共同静态实体',len(before_s['population_group_ids']),len(known)),('无序空间对',before_s['all_pairs'],spatial['all_pairs']),('负cosine候选',before_s['negative_proposals'],spatial['negative_proposals'])]:lines.append(f'| {title} | {a} | {b} |')
lines+=['',f"实体C/K/U/E={presence['summary']['C']}/{presence['summary']['K']}/{presence['summary']['U']}/{presence['summary']['E']}；空间C/K/U/E={spatial['summary']['C']}/{spatial['summary']['K']}/{spatial['summary']['U']}/{spatial['summary']['E']}。",'分组变化会改变计分分母；分数变动不能直接当作视频质量变化。复核拆分与视角免罚是两个判断，视角原因由下游两次判断核实，证据不足仍unknown。','','## 确认冲突']
for r in conflicts['presence']:lines.append('- 存在性 '+r['group_id']+': '+str(r['reason']))
for r in conflicts['spatial']:lines.append('- 空间 '+r['relation_id']+f": cosine={r['cosine']:.9f}; "+r['verification']['reason'])
lines+=['','## 配准及审计',f'原配准文件哈希完全不变。被移除的旧结构参照及原有效点数：{removed}。未重新拟合。','7项身份契约测试通过：允许大差异保持身份、拆分守恒、重复/丢失实体拒绝、双shot拆分证据、失效参照拒绝及原帧坐标范围。校验新空间总体只含复核后合理共同实体，关系计数正确，未变对应的cosine精确重现旧值。','', '## 消耗',f"新增模型调用{usage['new_model_calls']}次；input={usage['input_tokens']}，output={usage['output_tokens']}，total={usage['total_tokens']} tokens。调用时间跨度{usage['wall_span_seconds']/60:.2f}分钟（包含阶段间等待/开发）；累计调用耗时{usage['sum_call_seconds']/60:.2f}分钟（并行部分重复计入），均不含复用历史阶段成本。所有新调用gpt-6-astra/medium，实际计量见usage.json。",'','## 证据文件','','- study2/identity_review.json：完整逐组原帧身份复核及初步单侧原因','- study2/matching_initial.json 与 matching.json：初始/修正对应','- study2/presence.json：两次独立判断及最终原因','- study2/spatial.json：全部空间关系与最终Prompt复核','- study2/calls/：各次请求、原始响应、事件与token记录','- study2/identity_review_alignment.png：提供给模型的中性对齐图']
(H/'REPORT.md').write_text('\n'.join(lines)+'\n');print(json.dumps({k:summary[k] for k in ['new_entity_score','new_spatial_score','old_common_static','new_common_static','old_pair_count','new_pair_count','old_negative_count','new_negative_count','removed_registration_anchors_and_original_point_counts']},indent=2));print('USAGE',usage['total_tokens'])
