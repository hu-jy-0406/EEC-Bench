"""Report actual new work, validate preserved baseline, and compare completed runs only here."""
import csv,json,hashlib,itertools
from pathlib import Path
import numpy as np
H=Path(__file__).resolve().parent;O=H/'study2';B=H.parents[1]
def read(p):return json.loads(Path(p).read_text())
def save(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
runtime=read(O/'pipeline_runtime.json');assert runtime['status']=='success';detection=read(O/'entities/run.json');assert detection['status']=='success' and detection['detector_mode']=='fresh'
for p,h in read(H/'baseline_preservation.json').items():assert sha(p)==h,'Original pipeline/result changed: '+p
sources=read(O/'joint_sources.json')
for p,h in sources.items():assert sha(p)==h,'Final joint frozen source changed: '+p
assert read(H/'contract_validation.json')['passed']
inputs=[read(O/'inputs'/f'{s}.json') for s in ['shot1','shot3']];graphs=[read(O/'selected'/f'{s}_scene.json') for s in ['shot1','shot3']];names={e['entity_id']:e['name'] for g in graphs for e in g['entities']};matching=read(O/'matching.json');groups={g['group_id']:g for g in matching['groups']};presence=read(O/'presence.json');spatial=read(O/'spatial.json');joint=read(O/'joint_identity_presence.json')
assert presence['aggregation_version']=='joint_single_presence_witness_v1'
assert not any((O/'calls'/s).exists() for s in ['matching','identity_review','presence_1','presence_2']), 'Legacy full judgment called'
for src in inputs:
 assert len(src['frames'])==6
 for f in src['frames']:assert sha(f['path'])==f['sha256']
for side,g in zip(['a','b'],graphs):
 actual=[eid for x in groups.values() for eid in x[side+'_ids']];expected={e['entity_id'] for e in g['entities'] if e['motion_status']=='static'};assert len(actual)==len(set(actual)) and set(actual)==expected
expected=[r['group_id'] for r in presence['groups'] if r['joint_presence_reasonable']];assert spatial['population_group_ids']==expected;n=len(expected);assert len(spatial['relations'])==n*(n-1)//2;assert len({tuple(sorted(r['endpoint_groups'])) for r in spatial['relations']})==len(spatial['relations'])
aligned=read(O/'aligned_entities.json');coords={e['entity_id']:np.array(e['geometry']['center_world']) for s in aligned['shots'] for e in s['entities'] if e['geometry']};fit=spatial['registration'];R=np.array(fit['rotation']);assert np.allclose(R.T@R,np.eye(3),atol=1e-8) and np.isclose(np.linalg.det(R),1) and np.allclose(R@[0,0,1],[0,0,1],atol=1e-8) and fit['scale']>0
for r in spatial['relations']:
 a,b=[groups[k] for k in r['endpoint_groups']];va=coords[b['a_ids'][0]]-coords[a['a_ids'][0]];vb=coords[b['b_ids'][0]]-coords[a['b_ids'][0]];den=np.linalg.norm(va)*np.linalg.norm(vb)
 if r['cosine'] is not None:assert den>1e-10 and abs(float(va@vb/den)-r['cosine'])<1e-9
 if r['status']=='conflict':assert r['cosine']<0 and r['visual_gate_pass'] and r['prompt_gate_pass'] and r['verification']['prompt_motion_review']['verdict']=='does_not_explain_change'
def label(gid):return ' / '.join(dict.fromkeys(names[e] for e in groups[gid]['a_ids']+groups[gid]['b_ids']))
pconf=[dict(group_id=r['group_id'],entity=label(r['group_id']),kind=r['conflict_kind'],reason=r['reason']) for r in presence['groups'] if r['status']=='conflict'];sconf=[dict(relation_id=r['relation_id'],entities=[label(k) for k in r['endpoint_groups']],cosine=r['cosine'],reason=r['verification']['reason'],prompt_motion_review=r['verification']['prompt_motion_review']) for r in spatial['relations'] if r['status']=='conflict']
calls=[]
for p in list((O/'entities/shots').glob('*/status.json'))+list((O/'calls').glob('*/status.json')):
 d=read(p);req=read(p.parent/'request.json');cluster='entities/shots' in str(p);cmd=req['command'];assert '--ephemeral' in cmd and '--ignore-user-config' in cmd and cmd[cmd.index('--model')+1]=='gpt-6-astra' and 'model_reasoning_effort="medium"' in cmd
 assert d['started']>=runtime['started'] and not d.get('reused_from');assert d['status']=='success', 'A failed actual call needs separate reporting'
 us=d.get('usage',[]);tot={k:sum(u.get(k,0) for u in us) for k in ['input_tokens','output_tokens','cached_input_tokens']};tot['total_tokens']=tot['input_tokens']+tot['output_tokens'];end=d.get('ended',d.get('finished'))
 calls.append(dict(stage=('clustering_' if cluster else '')+p.parent.name,started=d['started'],ended=end,seconds=end-d['started'],model='gpt-6-astra',reasoning='medium',**tot,evidence=str(p)))
 if not cluster and p.parent.name.startswith(('motion_','observe_')):
  sid=p.parent.name.split('_',1)[1];assert len(req['images'])==6 and all(f['shot_id']==sid for f in req['images'])
calls.sort(key=lambda c:c['started']);totals={k:sum(c[k] for c in calls) for k in ['input_tokens','output_tokens','cached_input_tokens','total_tokens']};totals['calls']=len(calls)
stages=[]
def row(name,seconds,callnames):
 cs=[c for c in calls if c['stage'] in callnames];stages.append(dict(stage=name,seconds=seconds,calls=len(cs),**{k:sum(c[k] for c in cs) for k in ['input_tokens','output_tokens','cached_input_tokens','total_tokens']}))
row('WeDetect-Anything',detection['review_started']-detection['started'],[]);row('独立单shot聚类',detection['review_finished']-detection['review_started'],['clustering_shot1','clustering_shot3'])
labels={'geocalib':'GeoCalib重力估计','pi3x_shot1':'Pi3X Shot1','pi3x_shot3':'Pi3X Shot3','boxer_shot1':'Boxer Shot1','boxer_shot3':'Boxer Shot3','motion_and_fusion':'独立动静判断＋静态图融合','anchors_only':'仅配准参照实体对应','roma_matches':'RoMaV2 36帧对匹配','lift_correspondences':'筛点与坐标提升','registration':'重力约束Sim3配准','joint_identity_presence':'一次完整身份＋存在性联合判断','spatial':'cosine＋局部取证＋最终Prompt复核'}
for r in runtime['stages']:
 if r['stage']=='detection_and_clustering':continue
 cs=['motion_shot1','motion_shot3'] if r['stage']=='motion_and_fusion' else ['observe_shot1','observe_shot3','verify_relations'] if r['stage']=='spatial' else [r['stage']]
 row(labels.get(r['stage'],r['stage']),r['seconds'],cs)
assert sum(s['total_tokens'] for s in stages)==totals['total_tokens']
counts={g['shot_id']:dict(entities=len(g['entities']),**{s:sum(e['motion_status']==s for e in g['entities']) for s in ['static','moving','unknown']}) for g in graphs}
audit=dict(passed=True,original_pipeline_and_results_unchanged=True,all_inference_outputs_fresh=True,original_images_unchanged=True,all_calls_gpt6_astra_medium=True,legacy_full_matching_and_dual_presence_not_called=True,static_inventory_conserved=True,single_presence_evidence_gates_retained=True,all_unordered_pairs_once=True,cosines_recomputed_from_aligned_centers=True,frozen_final_registration_hash_verified=True,token_sum_reconciled=True,contract_tests=read(H/'contract_validation.json'))
# Baseline results are introduced ONLY for this completed-run comparison, never in model payloads.
baseline=read(Path(read(H/'run_spec.json')['baseline'])/'study2/result.json');old=baseline['tokens'];changed_stage_names={'anchors_only','joint_identity_presence'};new_changed=[c for c in calls if c['stage']=='anchors_only' or c['stage'].startswith('joint_identity_presence')]
old_changed=[s for s in baseline['stages'] if s['stage'] in ['Initial cross-shot identity matching','Post-alignment identity review','Presence consistency (two independent reviews)']]
comparison=dict(old_presence=baseline['presence'],new_presence=presence['summary'],old_spatial=baseline['spatial'],new_spatial=spatial['summary'],old_calls=old['calls'],new_calls=totals['calls'],old_total_tokens=old['total_tokens'],new_total_tokens=totals['total_tokens'],token_reduction_fraction=1-totals['total_tokens']/old['total_tokens'],old_wall_seconds=baseline['wall_seconds'],new_wall_seconds=runtime['seconds'],old_negative_pairs=baseline['negative_proposals'],new_negative_pairs=spatial['negative_proposals'],old_changed_stages_tokens=sum(s['total_tokens'] for s in old_changed),new_changed_stages_tokens=sum(c['total_tokens'] for c in new_changed),caveat='One full fresh run per variant; includes frontend inference variability and model/system latency, not a frozen-frontend or repeated-trial ablation.')
summary=dict(case='study2',shots=['shot1','shot3'],pipeline_revision='anchor_then_joint_presence_v1',full_fresh_run=True,presence=presence['summary'],spatial=spatial['summary'],counts=counts,common_static=n,all_pairs=spatial['all_pairs'],negative_proposals=spatial['negative_proposals'],support_pass=spatial['support_pass'],presence_conflicts=pconf,spatial_conflicts=sconf,anchors=read(O/'anchors_initial.json'),final_anchor_audits=joint['anchor_audits'],joint_audit=read(O/'joint_audit.json'),transform={k:fit[k] for k in ['scale','yaw_deg','translation','train','spatial_holdout']},tokens=totals,wall_seconds=runtime['seconds'],stages=stages,comparison=comparison,audit=audit)
save(O/'result.json',summary);save(O/'usage.json',dict(totals=totals,calls=calls));save(O/'audit.json',audit);save(O/'comparison.json',comparison)
for name,rows in [('stages.csv',stages),('calls.csv',calls)]:
 with (O/name).open('w') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
with (O/'all_pairs.csv').open('w') as f:
 w=csv.writer(f);w.writerow(['relation_id','entity_a','entity_b','cosine','angle_deg','status','reason'])
 for r in spatial['relations']:w.writerow([r['relation_id'],*[label(k) for k in r['endpoint_groups']],r['cosine'],r['angle_deg'],r['status'],r['reason']])
lines=['# Study2 新流程独立测试：参照先行、身份与存在性一次联合判断','','版本：`anchor_then_joint_presence_v1`；全部 Codex 调用 `gpt-6-astra / medium`。旧流程 `post_alignment_identity_review_v1` 原样保留，哈希审计通过。','','## 新旧结果','','| 指标 | 原流程完整重跑 | 新流程完整重跑 |','|---|---:|---:|']
for title,a,b in [('实体一致性分',baseline['presence']['score'],presence['summary']['score']),('空间关系一致性分',baseline['spatial']['score'],spatial['summary']['score']),('共同静态实体数',baseline['common_static'],n),('无序实体对',baseline['all_pairs'],spatial['all_pairs']),('负cosine',baseline['negative_proposals'],spatial['negative_proposals']),('Codex调用',old['calls'],totals['calls']),('输入tokens',old['input_tokens'],totals['input_tokens']),('输出tokens',old['output_tokens'],totals['output_tokens']),('总tokens',old['total_tokens'],totals['total_tokens']),('流水线墙钟秒',baseline['wall_seconds'],runtime['seconds'])]:lines.append(f'| {title} | {a} | {b} |')
lines+=['',f"总tokens变化：减少 {100*comparison['token_reduction_fraction']:.2f}%；原来的初始完整对应＋对齐后身份复核＋两次存在性判断共 {comparison['old_changed_stages_tokens']:,} tokens，新参照选择＋联合判断共 {comparison['new_changed_stages_tokens']:,} tokens。",'两组都从相同原始JPEG重新推理，无历史推理输出复用；只沿用代码/环境/预训练权重/原始Prompt输入。此次不是固定前端的严格消融，也不是多轮稳定性评估；时间差包含加载缓存、服务速度和系统波动，不能解释成固定加速比。','','## 实际阶段消耗','','| 环节 | 墙钟秒 | Codex次数 | Input tokens | Output tokens | Total tokens |','|---|---:|---:|---:|---:|---:|']
for s in stages:lines.append(f"| {s['stage']} | {s['seconds']:.2f} | {s['calls']} | {s['input_tokens']:,} | {s['output_tokens']:,} | {s['total_tokens']:,} |")
lines+=['',f"总墙钟 {runtime['seconds']:.3f}s；阶段切换间隔 {runtime.get('frontend_backend_handoff_seconds',0):.3f}s 已含在总墙钟内。并行调用按阶段墙钟计一次；GPU阶段含加载/安全检查。cached input={totals['cached_input_tokens']}，其已包含在input中，reasoning子项不重复相加。逐调用时间与usage见calls.csv和usage.json。实验准备/测试/报告整理未单列为模型推理耗时。",'','## 实际流程','','1. 两shot各6张原始JPEG→全新WeDetect→两次隔离聚类→全新GeoCalib/Pi3X/Boxer→两次隔离动静判断及静态融合。','2. 一次Codex只选择配准参照及局部支撑参照对；未选实体尚未对应，没有“默认单侧”标签。','3. 全新RoMa 36组帧对→结构筛点/深度提升→重力约束Sim3。','4. 一次Codex读取原帧、自己的/对齐后框、对側投影、融合误差、动静清单和正常剧情，输出全部实体身份分组及存在性原因；程序执行原证据和Prompt门。','5. 合理共同静态集合的全部无序对算cosine；负值经独立单shot局部取证及最终跨shot原帧/Prompt复核。','6. 保持两个分数公式和未知/豁免口径，审计实体守恒、原帧哈希、冻结变换、cosine和usage。','','## 参照及配准','']
for a in summary['anchors']['anchors']:lines.append(f"- {a['anchor_id']}: {names[a['a_id']]} ↔ {names[a['b_id']]}；{a['reason']}")
lines += ['',f"最终yaw={fit['yaw_deg']:.6f}°，scale={fit['scale']:.9f}，translation={fit['translation']}；留出点中位重投影误差{fit['spatial_holdout']['median_pixels']:.3f}px。",f"最终参照核验：{json.dumps(joint['anchor_audits'],ensure_ascii=False)}",f"参照回退记录：{json.dumps(summary['joint_audit'],ensure_ascii=False)}。",'','## 全部身份及存在性判定','','| 组 | Shot1实体 | Shot3实体 | 身份 | 存在状态 | 原因类别 |','|---|---|---|---|---|---|']
for r in presence['groups']:
 g=groups[r['group_id']];cells=[r['group_id'],' / '.join(names[e] for e in g['a_ids']),' / '.join(names[e] for e in g['b_ids']),g['identity'],r['status'],r['cause']];lines.append('| '+' | '.join(str(v).replace('|','/').replace('\n',' ') for v in cells)+' |')
lines+=['','## 未确认项与效果边界','','本次存在性分数升高不表示检出更好；需同时对照确认冲突数量和unknown。下面保留模型实际未确认的项目及理由。']
for g in groups.values():
 if g['identity'] in ['ambiguous','scope_mismatch']:
  lines.append(f"- 身份未定：{g['group_id']} {label(g['group_id'])}。{g['identity_evidence']}")
for r in presence['groups']:
 if r['status']=='unknown' and r['cause']=='inconsistency':lines.append(f"- 有不一致嫌疑但未确认：{r['group_id']} {label(r['group_id'])}。{'；'.join(r['reason'])}")
lines+=['', '参照集合、全新前端输出、配准结果和判定上下文均可能影响上述变化；一次端到端运行不能把原因唯一归结为少了一次复核。旧版结果与默认配置保留，新版仍是实验分支。']
lines+=['','## 确认冲突','']
for c in pconf:lines.append(f"- 存在性：{c['entity']}，{c['kind']}。{'；'.join(c['reason'])}")
for c in sconf:lines.append(f"- 空间：{' ↔ '.join(c['entities'])}，cosine={c['cosine']:.9f}。{c['reason']}")
if not pconf:lines.append('- 无确认存在性冲突。')
if not sconf:lines.append('- 无确认空间冲突，按规则得100分；不代表所有关系被证实一致。')
lines += ['',f"存在性 C/K/U/E={presence['summary']['C']}/{presence['summary']['K']}/{presence['summary']['U']}/{presence['summary']['E']}；空间 C/K/U/E={spatial['summary']['C']}/{spatial['summary']['K']}/{spatial['summary']['U']}/{spatial['summary']['E']}。score=100×(1−K/(C+K+U))，空间K=0时100。",'','## 验证与证据','','12项契约测试通过：参照阶段不强制完整匹配、参照重复/掩码ID冲突、单判断保留有效惩罚、大位移不自动拆身份、实体增删/重复拒绝、Prompt/多帧/漏检门不足降未知、应离开却仍出现仅影响存在性、未确认共同存在不进入空间比较、失效参照按实际点数触发重配准、无效参照不能进入局部坐标、像素范围校验、零空间冲突100。实际运行另通过原流程哈希、全新调用、模型medium、实体守恒、全部无序对、独立重算cosine、冻结输入和token对账审计。','','- study2/result.json / comparison.json：结果与比较','- study2/stages.csv / calls.csv / usage.json：完整消耗','- study2/anchors_initial.json：参照选择，未包含完整实体对应','- study2/joint_identity_presence.json：单次联合输出','- study2/matching.json / presence.json / spatial.json / all_pairs.csv：最终计分依据','- study2/calls/：原始请求/响应/实际usage','- baseline_preservation.json / code_snapshot/ / contract_validation.json：保留旧版与新实现证据']
(H/'REPORT.md').write_text('\n'.join(lines)+'\n');print(json.dumps({k:summary[k] for k in ['presence','spatial','counts','all_pairs','negative_proposals','support_pass','tokens','wall_seconds','comparison']},ensure_ascii=False,indent=2))
