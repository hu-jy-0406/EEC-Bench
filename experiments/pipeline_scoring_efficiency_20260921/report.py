import csv,hashlib,json,shutil,time
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parents[1]
def read(p):return json.loads(p.read_text())
def save(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
replay=read(R/'replay_status.json');more=read(R/'additional_presence_validation.json');audit=read(R/'audit.json')
assert replay['status']=='success' and audit['status']=='pass' and all(v['status']=='success' for v in more.values())
base=read(B/'experiments/study3_final_integrated_20260921/run/summary.json');oldcalls=base['calls'];rows=[]
for component,prefix in [('identity','pairs/pair_000/calls/identity_review'),('presence','pairs/pair_000/calls/boundary_review_'),('alignment','prompt_alignment/calls/')]:
 old=[r for r in oldcalls if r['call'].startswith(prefix)];new=[r for r in replay['calls'] if r['component']==component]
 oldsec=next(s['seconds'] for s in base['stages'] if s['stage']=='prompt_alignment') if component=='alignment' else sum(c['seconds'] for c in old)
 newsec=replay['components']['alignment']['seconds'] if component=='alignment' else sum(c['seconds'] for c in new)
 tokens0=sum(r['total_tokens'] for r in old);tokens1=sum(r['tokens'] for r in new);usd0=sum(r['standard_api_equivalent_usd'] for r in old);usd1=sum(r['standard_api_equivalent_usd'] for r in new)
 nocache=sum((u['input_tokens']*10+u['output_tokens']*50)/1e6 for c in new for u in c['usage'])
 rows.append(dict(component=component,old_seconds=oldsec,new_seconds=newsec,time_reduction_percent=100*(1-newsec/oldsec),old_tokens=tokens0,new_tokens=tokens1,old_usd=usd0,new_usd=usd1,new_usd_if_no_cache=nocache))
t0=sum(r['old_tokens'] for r in rows);t1=sum(r['new_tokens'] for r in rows);c0=sum(r['old_usd'] for r in rows);c1=sum(r['new_usd'] for r in rows)
validation_tokens=t1+sum(r['total_tokens'] for r in more.values());validation_usd=c1+sum(r['standard_api_equivalent_usd'] for r in more.values())
result=dict(selected_runtime='scoring_efficiency_v1',selected_schedule='parallel_v2',fresh_gpu_run=False,components=rows,
 study3_changed_components=dict(old_tokens=t0,new_tokens=t1,token_reduction_percent=100*(1-t1/t0),old_usd=c0,new_usd=c1,new_usd_if_no_cache=sum(r['new_usd_if_no_cache'] for r in rows)),
 validation_expense=dict(model_calls=8,tokens=validation_tokens,standard_api_equivalent_usd=validation_usd),
 tests_passed=268,quality_scope='Study3 identity/presence/alignment and offline downstream composition; Study2/4 presence only. Documented uncertainty/population changes, not exact quality equivalence.',
 full_episode_wall_time_measured=False,full_episode_token_composition=dict(tokens=base['total_tokens']-t0+t1,standard_api_equivalent_usd=base['standard_api_equivalent_usd']-c0+c1,estimated=True,retains_original_failed_binding_attempt=True,does_not_rerun_changed_identity_downstream=True),
 pricing='Standard Astra equivalent, not billed: USD/M input10, cached-input1, cache-write12.5, output50; input>272000 uses input-side x2/output x1.5. Cached input is a subset. Current calls below long-context threshold.')
save(R/'comparison.json',result)
with (R/'component_comparison.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
lines=['# 评分流程优化：scoring_efficiency_v1','',
'已选为当前默认，调度默认 parallel_v2。旧配置 temporal_spatial_v1 / parallel_v1 保留。用户本轮明确授权删除不必要的模型任务、优化调用并发。详细流程见 ../../docs/pipeline-scoring-efficiency-v1.md。','',
'## 实现','',
'- 身份复核删除仅保存、未被下游使用的 noncommon_checks（单侧实体的视角/运动/缺失预判），交给独立存在性环节判断。合并重复的几何/视觉/同物移动解释为一个证据字段；仍要求完整初始分组审核、原图证据、拆分门槛和锚点校验。',
'- 身份输出使用已校验的 unchanged_group_ids 复制完整未变分组，保留所有逐组审核、修改分组与证据。',
'- 存在性去掉六个空间专属布尔字段及无关的空间/镜头内任务段落，保留五个有效存在性门槛、Prompt因果、端点证据、未知和具体理由。',
'- 存在性与 Prompt alignment 使用已有无损表格/引用编码。原始帧、实体、定义几何及 canonical input 均保留；六个 Study3 调用原始输入与图像哈希完全相同，编码往返通过。',
'- Prompt alignment 的独立scope批次两路并发，保证原输出顺序、scope内依赖及失败后等待已启动调用结束。整体最多8路API/1个GPU；启用alignment时appearance3路，使 boundary3+appearance3+alignment2同时容纳；没有alignment时appearance仍为5路。',
'- 其余注册目标、模型/推理档、空间门槛、外观和位移公式不变，原始r_e继续保存。局部空间placement参与共同支撑关系校验，因此保留。','',
'## Study3 固定输入模型复测','',
'重用上一轮固定检测/几何/初始身份等输入，重新调用改变的环节。以下每行内部可比较；不是GPU全流程重跑，不可把并发环节时长相加当整集wall。','',
'| 环节 | 旧→新耗时(s) | 旧→新tokens | 旧→新标准API等价USD |','|---|---:|---:|---:|']
for r in rows:lines.append(f'| {r["component"]} | {r["old_seconds"]:.2f} → {r["new_seconds"]:.2f} | {r["old_tokens"]:,} → {r["new_tokens"]:,} | {r["old_usd"]:.6f} → {r["new_usd"]:.6f} |')
lines += ['',f'这三个改动环节合计 {t0:,}→{t1:,} tokens，减少{100*(1-t1/t0):.2f}%；标准API等价 USD {c0:.6f}→{c1:.6f}。',
'新身份调用命中128,640缓存输入tokens，费用下降包含缓存收益，不能作为未来每次运行保证。把新调用缓存按未缓存费率计算，同一组三环节约USD '+f'{sum(r["new_usd_if_no_cache"] for r in rows):.6f}。缓存tokens是输入子集，不重复累加。',result['pricing'],'',
'## 判定与分母变化','',
'- Study3 Prompt alignment：79/79状态相同，四维T/F/U、得分和区间相同。',
'- Study3 存在性：固定旧身份图上的30/30事件状态相同，包含原有冲突。Study2另行复测29/29实际事件一致（另1个未解析身份单位仍unknown），原两个冲突保留。',
'- Study4：20个实际presence事件中3个状态变化：g03 exempt→compatible；g10/g14 exempt→unknown。原无冲突、复测仍无冲突；得分100不变，但N9→12、C2→3、U7→9、E13→10，coverage也变，不能声称全部细节一致。2个不确定身份原本无调用事件，保留原unknown单位。',
'- Study3 身份：全部10条已确认匹配、锚点、46个局部实体及36个全局实体的实际出现记录不变。植物 shot1/e20 与 shot3/e11 从两个unmatched改为一个ambiguous关联，未强制合并全局实体。身份总组数30→29；不确定关联0→1。',
'- 对这一新身份图做明确标注的离线下游组合：只复用事件输入完全相同的新presence判断及原局部空间判断；空间全部结果一致；48条有效位移记录及原始r_e完全一致，三个position分数不变。未计分位移记录28→27。',
'- 存在性公式原本将unknown纳入分母，两个旧exempt植物单位变为一个unknown单位，故组合presence N12→13、U2→3、E18→16，分数91.666667→92.307692；不是新增发现正确实体。保留原公式和差异，不按目标得分调参。',
'- 新身份图的appearance/binding/alignment没有重新调用；实际出现记录完全一致，不能把离线组合描述为完整新模型重跑。单次固定样例对照不构成人工质量校准或一般无损保证。','',
'## 验证与开销','',
'268项GS回归测试通过，包括省略字段前后门槛等价、身份/锚点/拆分证据、端点证据、并发限额、scope依赖、失败收尾、历史回退和新默认配置。tests_selected.log为晋升后的最终验证。',
f'本轮全部8次模型验证调用：{validation_tokens:,} tokens，标准API等价 USD {validation_usd:.6f}，并非账单。Study3三环节{t1:,}/USD{c1:.6f}；Study2/4补充验证{validation_tokens-t1:,}/USD{validation_usd-c1:.6f}。本地代码测试/组合审计0新模型调用。',
'沿用已有196093/node197的低负载CPU8–11，未运行GPU、未新申请资源。没有新全流程wall测量；comparison.json中的整集token/cost为替换三环节的组合估计，含原失败binding调用，不是实际新生产运行费用。开发和本对话开销不属于这8次评测调用。','',
'## 文件','',
'- comparison.json / component_comparison.csv：时间、tokens、含缓存及无缓存估算。',
'- replay_status.json / additional_presence_validation.json：新鲜模型调用、完整逐事件差异。',
'- audit.json / composition_case_v3：完整输入往返、原帧哈希、改变身份图后的下游组合审计。先前composition_case与_v2保留审计脚本开发的失败中间结果，不是生产结果。',
'- identity / presence / alignment / study2_presence / study4_presence：全部实际请求、canonical/wire输入、响应和usage。',
'- source_snapshot / promotion.json：晋升后的代码和配置快照。','']
(R/'REPORT.md').write_text('\n'.join(lines))
paths=[B/'scripts'/n for n in ('review_aligned_entity_identities.py','run_gs_flow1_stage.py','gs_efficient_transport.py','gs_temporal_contract.py','gs_temporal_review.py','run_gs_temporal_stage.py','gs_prompt_binding.py','gs_prompt_alignment.py','run_gs_temporal.py','run_gs_integrated.py','gs_flow1_compact_payload.py')]+[B/'prompts/gs_aligned_identity_scoring_v1.txt',B/'prompts/gs_flow1/boundary_presence_scoring_v1.txt',B/'configs/gs-runtime-profiles.v1.json']
snapshot={}
for p in paths:
 q=R/'source_snapshot'/p.relative_to(B);q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q);snapshot[str(p)]=dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),snapshot=str(q))
save(R/'promotion.json',dict(time=time.time(),selected_runtime='scoring_efficiency_v1',selected_schedule='parallel_v2',source_snapshot=snapshot,validation_expense=result['validation_expense']))
print(json.dumps(result,ensure_ascii=False,indent=2))
