import json,time,hashlib,shutil
from pathlib import Path
R=Path(__file__).resolve().parent;rd=lambda p:json.loads(p.read_text());comparison=rd(R/'comparison.json');usage=rd(R/'usage.json');rows=comparison['studies']
def n(x):return '—' if x is None else f'{x:.2f}'
lines=['# 最简身份输入：Study2/3/4 完整下游验证','',
'结论：三组冻结上游上的最简身份输入均保留确认身份、锚点、存在性/空间关系逐实体判定及原始位移比例。Study2/3直接完成；Study4原始prompt绑定连续两次格式校验失败，在实验输出schema中明确既有约束后完成。不能称为原生产流程三组一次全部无问题。','',
'本次只更改身份复核请求的输入范围。生产默认未切换。检测、原始图像、三维重建、whole-shot motion、配准和片内复核均复用冻结基线；跨镜头复核、外观Codex、prompt绑定与alignment新调用；全部位移重新汇总并保存原始r_e。DINO使用同一权重/处理器在已分配节点CPU重新计算，未占用GPU。','',
'## 结果','', '| Study | 身份分组 | 存在性 旧→新 | 空间关系 旧→新 | 位移 片内/跨shot/全部 | 外观Codex |', '|---|---|---|---|---|---|']
for x,a in zip(rows,comparison['audits']):
 lines.append(f"| {x['study']} | {'一致' if a['identity']['population']['equal'] else '变化见明细'} | {n(x['presence_before']['score'])} → {n(x['presence_after']['score'])} | {n(x['spatial_before']['score'])} → {n(x['spatial_after']['score'])} | {' / '.join(n(x['displacement'][k]['score']) for k in ['within','cross','all'])} | {n(x['appearance']['codex_score'])} |")
lines += ['', '三组空间冲突数分别为1/36、1/45、0/3。Study4沿用原冻结集合粒度，只有3个空间实体对；不能据此宣称所有茶杯交换都得到评估。片内空间结果复用，均100，不是此次重新模型验证。存在性未知记录继续保留，不能将100解释为全部证据充分。', '',
'## 细项差异与归因','',
'- 三组确认身份、anchor资格/选择/参考均保持；实体对应的存在性与空间最终状态保持。Study3一个不确定组的标识符变化，不改变成员和unknown状态。所有有效跨shot原始r_e、距离和实体位移分数保持。',
'- Study3外观总分85.7756006保持，未知属性数量26→25；原始crop像素和所属实体/帧逐项核验。DINO CPU/GPU有浮点级差异，未声称逐位相同。',
'- Study3 prompt空间分78.5714286→80.9523810，唯一原子状态变化为shot1_lamp_on_desk：unknown→satisfied。该Shot1模型输入与旧版逐值完全相同，属于观察到的重复调用波动。',
'- Study3绑定中书堆ge0035从unbound→unknown(candidate notebook)。绑定模型输入与旧版完全相同；未改变冻结视觉身份，相关未知信息传入后续prompt判断。其余三个prompt维度分数保持。',
'- Study2/4原冻结基线没有这套完整prompt参照，因此本次由各自保存的情节文本编译54/161条要求，作为首次测试，不能报告与历史完整prompt分数等价，也不宜按不同要求集合直接比较Study间分数。Study4保留原文明确授权的杯子换位/内容变化。', '',
'## Prompt分项','', '| Study | Presence | Appearance | Spatial | Motion | 要求数 |', '|---|---:|---:|---:|---:|---:|']
for x,a in zip(rows,comparison['audits']):
 lines.append('| '+x['study']+' | '+' | '.join(n(x['alignment'][k]['score']) for k in ['presence','appearance','spatial','motion'])+f" | {a['alignment_claims']} |")
lines += ['', '各维度T/F/U、分层汇总和全部见证见comparison.json与各alignment/results.json；unknown不是已证实一致。Study2/4自动文本编译通过结构、引句和范围检查，但不是独立人工标注的完备性证明。', '',
'## Study4恢复记录','',
'1. 初始文本schedule遗漏Shot2开头可见的花园门；在不使用视频判定的情况下，按原文另存修正版，增加4条相关要求，原编译输入/输出保留。',
'2. 初版和修正版的两次普通绑定调用均给unknown记录填写fact_ids，违反现有materialize要求。均真实失败，原响应/日志/费用保留；没有清空字段后伪装原模型通过。',
'3. strict_binding.py仅在实验调用的JSON schema中编码原有bound/unbound/unknown字段约束。原prompt和materialize不变，新调用通过原校验，再完整运行修正版alignment。不是额外身份复核或评分门槛调整；生产schema未修改。',
'4. Study4成功的边界复核、DINO和appearance调用不重复。补做因调度中止而未执行的本地位移/外观报告。初始pipeline_runtime仍保留failed，最终完成状态是有记录的checkpoint恢复。', '',
'## 时间和API用量','', '| Study | 首轮下游执行秒（不含编译） | 从并行启动至最终完成秒 | 本次全部tokens | 标准API等价USD |', '|---|---:|---:|---:|---:|']
for x in rows:
 calls=[c for c in usage['calls'] if c['study']==x['study']]
 lines.append(f"| {x['study']} | {x['seconds']:.2f} | {x['including_reference_seconds']:.2f} | {sum(c['total_tokens'] for c in calls):,} | {sum(c['standard_api_equivalent_usd'] for c in calls):.6f} |")
elapsed=max(x['including_reference_seconds'] for x in rows)
lines += ['',f"三组实际并行从启动至最后成功输出：{elapsed:.2f}秒（{elapsed/60:.2f}分钟），含首次参照编译与Study4修正/失败恢复；不含前置代码准备、资源检查和最终报告审计。所有{usage['model_calls']}次API请求共{usage['tokens']:,}tokens，USD{usage['standard_api_equivalent_usd']:.6f}标准API等价估算。",'',
'费用按记录的Astra标准价：每百万未缓存输入USD10、缓存输入USD1、输出USD50，缓存为输入子集；长上下文按既有计价函数。不是实际账单，不含父对话/历史实验，集群费用未知。usage.json保留每次用量、缓存、编译和失败恢复费用。上述验证总额不是采用最简输入后每集正常运行的成本。','',
'## 产物与边界','',
'- runs/study{2,3,4}/comparison.json：全部细项差异；displacement/results.json与entities.csv保存未取整原始r_e。',
'- Study2/3完整结果：runs/study*/summary.json、appearance/report/results.json、prompt_alignment/results.json。',
'- Study4采用的prompt结果：study4_prompt_recovery_v2/{binding,alignment}/results.json；外观与空间仍位于runs/study4。',
'- frozen_upstream.json、source_snapshot、原始请求/响应、各调用status、参考编译和schema审计完整保留。',
'- 这是三例冻结前端的下游验证，没有重新运行检测/几何，没有独立人工正确性或新episode泛化验证。没有据分数择优挑选模型判定。']
(R/'REPORT.md').write_text('\n'.join(lines)+'\n')
# Final application source immutability, while report/audit helpers evolved locally.
hashes=rd(R/'source_hashes.json');checks={p:hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items() if '/EECBench/scripts/' in p or '/EECBench/prompts/' in p or '/EECBench/configs/' in p};assert all(checks.values())
for a in comparison['audits']:
 assert all(a['identity'][k]['equal'] for k in ['confirmed','eligible','anchors','references'])
 assert not a['presence_changes'] and not a['spatial_changes']
final=dict(status='complete_with_documented_study4_recovery',studies=3,all_confirmed_identity_and_anchor_results_preserved=True,all_entity_presence_and_spatial_statuses_preserved=True,application_source_hashes_unchanged=checks,production_default_changed=False,parallel_seconds=elapsed,model_calls=usage['model_calls'],total_tokens=usage['tokens'],standard_api_equivalent_usd=usage['standard_api_equivalent_usd'],raw_re_preserved=True,first_pass_all_three_success=False,initial_rejected_binding_calls=2)
(R/'selected_validation_summary.json').write_text(json.dumps(dict(status='complete_with_documented_recovery',studies=rows,selected_study4_prompt_root=str(R/'study4_prompt_recovery_v2'),initial_study4_pipeline_succeeded=False),ensure_ascii=False,indent=2)+'\n')
(R/'completion_audit.json').write_text(json.dumps(final,indent=2)+'\n')
print(json.dumps({k:v for k,v in final.items() if k!='application_source_hashes_unchanged'},indent=2))
