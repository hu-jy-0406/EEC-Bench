"""Write the Chinese execution report from real, audited v1.3 outputs."""
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
RUN=BASE/'run01'
read=lambda p:json.loads(p.read_text())
s=read(RUN/'score.json');audit=read(RUN/'replay_audit.json');run=read(RUN/'run.json')
assert audit['status']=='pass' and run['status']=='success'
old=read(BASE.parent/'study_inconsistent_3/gs_relations_20260914/run01/score.json')
names={'g03':'黑色台灯','g05':'书柜小相框','g08':'书柜','g14':'书柜浅色器皿','g18':'走廊大画框','g19':'窗旁植物画','g20':'走廊窄画框','g21':'走廊矮柜','g22':'纸巾包','g23':'小桌书堆','g24':'走廊地毯','g25':'小桌花盆'}
labels={'unexplained_single_sided_static_presence':'确认异常单侧存在；扣分','viewpoint':'视角/遮挡解释；免罚','detection_gap':'前端记录缺口；未知不罚','unknown':'证据不足；未知不罚'}
rows=['| 组 | 实体 | 两轮审核及最终结果 |','|---|---|---|']
for r in s['presence_results']:rows.append(f"| {r['group_id']} | {names[r['group_id']]} | {labels.get(r['reason'],r['reason'])} |")
calls=['| 阶段 | 新上下文数 | 附图 | 实际输出 |','|---|---:|---:|---|',
    '| 静态实体对应 | 1 | 12 张原 JPEG | 11 对 matched、12 个 unmatched、1 组 ambiguous、1 组 scope_mismatch |',
    '| 剧情延续推断 | 1 | 0 | 覆盖全部 25 个静态实体组；此次全部 presence=persist、layout=stable |',
    '| 单侧原因审核 | 2 | 每次 12 张 | 两次各覆盖 12 项，分类一致 |',
    '| 共同静态关系审核 | 2 | 每次 12 张 | 两次各覆盖 55 对；54 unknown、1 局部包含关系 compatible |']
stage_times=sum(c['seconds'] for c in run['calls'])
report=f'''# Study2：按静态集合范围修正后的实际评测

## 结论

已新增 **Gs static-set consistency v1.3** 实现并在 Study2 Shot1/Shot3 完成六次真实 Codex 调用。Study2 指当前导出命名中的 study2，对应工作区旧目录 study_inconsistent_3。

扣分入口已按用户要求限定为：

1. 静态集合不相交部分中，由不一致造成的异常单侧存在。
2. 静态集合相交部分中，已确认的空间关系不一致。

静止/运动切换、视角互补、剧情许可均设置明确免罚分支；辅助运动实体不进入评分对象。身份、粒度、前端或几何证据不足保留未知。取消独立的形状/外观罚分。

**实际只确认了台灯缺失、纸巾出现两项存在性冲突；空间分数不可判定。** 这说明评分范围已经按要求修改，但本例的空间关系判断可靠性仍未解决。不能宣称已实现稳定的跨场景一致性测量。

## 分数

| 输出 | 分数 | 覆盖率 | C / K / U / 免罚 | 计分单位 |
|---|---:|---:|---|---|
| 总分 | 88.89（上界） | 11.11% | 0 / 2 / 16 / 7 | 静态实体组 |
| 存在性 | 88.89（上界） | 72.22% | 11 / 2 / 5 / 7 | 静态实体组 |
| 空间关系 | 不可判定（null） | 0% | 0 / 0 / 55 / 0 | 共同静态实体对 |

共同身份的存在性已有两侧观测，所以在存在性分项中计 C=11；其空间关系未通过完整门控，所以不能在总表中计作整体相容。两个分项使用不同单位，不能相加。

总分分母为 25 个实体组 − 7 个已证明视角互补组 = 18。两项确认冲突共扣 `100×2/18=11.11` 分，得到 88.89。总分逻辑区间为 [0,88.89]；存在性区间为 [61.11,88.89]。未知不扣分，区间不是统计置信区间。空间零项通过判定，因此返回 null，不返回虚假满分。

## 实际输入

- 静态 Gs：沿用旧 Gs 评测的 GeoCalib+Boxer 冻结几何，Shot1 **17 个**、Shot3 **21 个**。
- 辅助完整记录：Shot1 **19 个实体，其中 2 个 moving**；Shot3 **22 个，其中 1 个 moving**。这些记录只用于解释静态集合差异。
- 图像：各 shot 原始 6 张 JPEG，共 **12 张，852×480**；frame_id 均为 0/24/48/72/96/120。字节哈希不变，未重新提帧、缩放或编码。
- 动静标签：复用之前两个隔离上下文的结果，没有重新分类。
- 剧情：从有来源记录的全局 Prompt 逐字提取 11 条正常剧情事实，包括拿红书离开、走廊放书、空手返回、无人进入或重新布置书房。中间 Shot2 只提供剧情，不参与本次评分。
- 测试原始 Prompt 同时含“故意制造哪些错误”的答案说明；这些制作/答案指令没有传给评分模型。提取过程与字符跨度保存在 inputs/narrative_provenance.json。这是有记录的人工输入整理，不是一个自动剧情解析阶段；后续的逐实体延续判断由 Codex 完成。
- 没有把用户预期结果、历史分数、旧审核判断、上一轮长边优化结果传给模型。

## 详细实际执行 Pipeline

### 1. 校验输入与静态评分范围

代码验证冻结静态 Gs 节点与既有动静标签中的 static 集合完全一致，核验图像和输入文件哈希。评分对象始终是这 17+21 个静态节点；完整实体记录中的 moving 节点不能进入结果分母或空间端点。

### 2. 重新做静态实体对应

一次全新 Codex 上下文读取两个静态 Gs、2D 框和 12 张原图，划分为 **11 对共同静态实体、12 个单侧静态实体、1 组身份歧义、1 组粒度差异**，覆盖全部节点且不重复。

身份歧义为书柜植物与另一侧裁切植物；粒度差异为一根笔与一组书写工具。两组不强行归为交集或异常差集，最终保留未知。

模型提出 3 个候选稳定参照：墙上风景画 g01、主桌 g04、暖气片 g12。没有用另一侧的 moving 实体扩充交集。

### 3. 先推断剧情延续要求

另一个全新 Codex 上下文只读取全部实体组名称/对应和 11 条剧情事实，不看跨 shot 图像或几何差异。此次全部 25 组都推断为存在应延续、布局应保持；没有得到剧情许可例外。

这不是用户逐实体预先约定，Prompt 未提及的自生成实体也由模型根据同场景连续剧情和物理持续性推断。被观察到的消失或位移不被用来为自身编造剧情解释。

### 4. 固定比较机会并计算局部几何

12 个 unmatched 进入单侧原因分支；11 个 matched 产生 `11×10/2=55` 个无序实体对，全部进入关系分支。

采用原有两参照加重力的局部方向压力测试：3 个候选参照产生 **324 条方向比较、48 条数值反转候选**。同一实体对的多个轴/参照候选仍只计一对，不能把 48 当成已确认冲突或分母。

沿用中心扰动比例 0.25、方向容差 ±15°、归一化区间间距 0.005；没有针对本次结果调阈值。这些是未标定的启发式压力范围。

没有重新做全房间对齐，也没有使用上一轮 −26.47° 长边旋转。原 Gs 和匹配一经固定，后续审核不改几何以提高分数。

### 5. 两个独立上下文判定单侧原因

每次读取同样的静态 Gs、全部辅助实体及冻结动静标签、剧情政策和原帧。两个调用互不读取对方结论。逐项检查 moving 对应、视角/遮挡、剧情许可、前端遗漏及异常缺失/新增。

{chr(10).join(rows)}

两轮分类一致，全部 12 项通过格式/证据引用检查。台灯、纸巾还通过可观察性、独立参照、对侧至少两帧、遮挡/漏检/运动/剧情/其他映射排除等代码门控。结论限定为可比较区域中的占位不延续。

这组真实数据中 **motion_transition=0、story=0**，不能以此例宣称这两个分支已在真实视频中验证。它们由专门的合成控制测试覆盖。书堆没有被强行对应到单本运动红书，因此保留未知。

### 6. 两个独立上下文检查全部 55 对共同静态关系

两轮原始输出均为 **54 对 unknown、1 对 compatible**，没有给出 conflict。那一对 compatible 是窗台植物 g07 与其花盆 g13：原帧支持局部容纳关系保持。

杯子 g02—笔筒 g06 的 desk/radiator 局部轴仍有数值反转，但两轮均指出隐藏中心、深度及轴映射的不确定性，无法排除几何误差解释，因此没有通过冲突判定。

**模型结果与最终门控结果需要区分：**当前代码对完整关系判定统一要求两个独立参照；植物—花盆仅有直接容纳证据、未给独立参照，故该相容候选也降为 unknown。最终为 **55 对 unknown**。这暴露了本轮关系定义和参照门控较保守的覆盖限制，不能说所有 unknown 都由原图完全不可见造成，也不能声称直接包含关系本身需要全场景配准。

### 7. 确定性汇总与回放

代码检查分区覆盖、证据帧/框、动静范围、剧情资格、参照独立性和两轮判断一致性。最终罚分集合只有 g03、g22；共同静态关系没有形成罚分集合。每实体最多计一次，两个入口不会重叠。

{chr(10).join(calls)}

模型为配置的 gpt-6-astra，reasoning=medium。共 **6 个独立上下文**，输入 **{audit['total_input_tokens']:,} tokens**，输出 **{audit['total_output_tokens']:,} tokens**；调用耗时合计约 **{stage_times/60:.2f} 分钟**，不含代码准备。没有失败或重复的模型推断调用。

## 与旧 v1.2 的区别

旧 v1.2 总分 {old['score']:.2f}，曾确认杯子—笔筒反转并把两个端点加入扣分；本次 v1.3 总分 88.89，因为新的两轮审核没有确认该空间冲突。

**分数升高不代表视频变得更一致。** 评测流程和可判定覆盖改变了；本次整体覆盖只有 11.11%。此外，本轮整体相容要求相关预枚举关系都被解决，较旧单实体局部相容口径严格，不能直接把两个覆盖率当作同一准确率指标比较。

## 验证与局限

- 14 项针对性测试通过：静止到运动免罚、运动身份需证据、剧情/视角例外、漏检未知、两分支互斥、形状越界拒绝、循环参照、无效数值支持、重复帧、分母完整性等。
- 全部 6 次真实响应覆盖与帧/像素框校验通过。
- 原始输入/JPEG/代码快照哈希、6 个不同上下文、同分支两个输入完全相同、政策先于判断且不含图像、静态范围及罚分入口审计通过。
- 精确 JSON 回放与独立算术复算通过。最初审计把 Python tuple 与保存后的 JSON array 直接比较而报错，修正为 JSON 表示域比较后通过；没有改推断输出或分数。
- 仅复用已有 Slurm job185272 / auh7-1b-gpu-241 的单 CPU，无 GPU 或新分配。
- 尚无独立人工标注集校准；同模型两次同意不是统计置信度。实际空间判定覆盖仍不足，尤其是局部关系与统一参照门控的适配需要继续研究。

## 文件

- `run01/score.json`：完整结果、两轮原始判断、门控原因、分数和覆盖率。
- `run01/RESULT.md`：全部 12 个单侧项及 55 对关系的双审核明细。
- `run01/replay_audit.json`：真实回放、上下文、来源和 token 审计。
- `inputs/narrative_provenance.json`：剧情来源、排除测试答案的处理记录。
- `tests.json`：测试结果与代码哈希。
- 通用说明：`EECBench/docs/gs-static-set-v1.3.md`。
'''
(BASE/'RESULT.zh.md').write_text(report)
(BASE/'comparison.json').write_text(json.dumps(dict(previous_version='gs-consistency-v1.2',previous_score=old['score'],previous_coverage=old['coverage'],new_version=s['version'],new_overall=s['overall'],new_existence=s['existence'],new_spatial=s['spatial_relations'],comparison_not_same_protocol_accuracy=True),ensure_ascii=False,indent=2)+'\n')
(BASE/'post_run_changes.json').write_text(json.dumps(dict(inference_or_score_changed=False,changes=[dict(file='audit_static_set_consistency.py',reason='compare tuples after canonical JSON serialization; first audit failed representation comparison, subsequent exact replay passed',new_model_calls=0)]),ensure_ascii=False,indent=2)+'\n')
extra=[ROOT/'EECBench/scripts/audit_static_set_consistency.py',ROOT/'EECBench/tests/test_static_set_consistency.py',ROOT/'EECBench/docs/gs-static-set-v1.3.md',Path(__file__)]
(BASE/'report_and_audit_hashes.json').write_text(json.dumps({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in extra},indent=2)+'\n')

heading='## 2026-09-16 — Static-set-only penalty scope correction and Study2 v1.3 actual run'
note='''
User corrected scope explicitly: score ONLY the two frozen STATIC sets. One-sided static entities may be moving in the other shot, view/occlusion-only, story-permitted, or truly inconsistent. Penalize only unexplained inconsistent one-sided static presence and confirmed spatial relations among COMMON STATIC identities. Full moving inventories are auxiliary evidence only, never score units. Motion-transition exemptions apply in this static metric regardless of judging the motion itself. Prompt-driven persistence must be inferred for all static entities including unmentioned generated entities, not a user-provided whitelist.

Implemented new run_static_set_consistency.py/static_set_contract.py/score_static_set_consistency.py/audit_static_set_consistency.py and four existing/new prompt roles; documented EECBench/docs/gs-static-set-v1.3.md. Frozen old releases/geometry/motion labels/scores preserved. Reused Study2=oldStudy3 study_inconsistent_3, original12JPEGs852x480,17/21static from19/22full entities. Narrative source includes defect-injection answers: prepared11verbatim normal-story facts with sourcehash/charspans, excluded expected-error instructions; extraction is explicit evaluator preparation, NOT an automatic parsing model. Optional source-policy question had no reply; proceeded with stated narrative-only assumption. Model policy then covers all25groups before visual judgments, without images/geometry/prior results. All25 persist/stable this case.

Actual6fresh configured gpt-6-astra/medium calls: matching1, policy1, one-sided2independent, common-spatial2independent. Matching11common/12singletons/1ambiguous/1scope_mismatch;3anchor candidates painting/desk/radiator. All55common-static unordered pairs enumerated before looking at scores;324reference-axis diagnostics/48numeric candidates (v1.2 fixed stress settings .25/15deg/.005), no whole-scene fitting/previousyaw use. Presence reviews both: lamp g03 and tissue g22 inconsistent;7viewpoint exemptions;bookcase g08 and pot g25 detection_gap;book stack g23 unknown. Motion/story exemptions0in this realcase, validated synthetically only.

Spatial reviews BOTH54unknown/1compatible; cup-holder g02/g06 numeric reversal remains unknown due hidden centers/depth/reference ambiguity. The compatible windowplant/pot g07/g13 is directcontainment only and fails current uniformtwo-independent-anchor gate, so final55unknown. This conservative gate is an explicit coverage limitation, not proof directcontainment intrinsically needs full registration. No confirmed spatial penalties. Do not silently restore oldv1.2 cup-holder conflict or call zero detected conflicts100% spatial consistency.

Overallentity score88.888889UPPERBOUND, C0/K2/U16/E7,N18,coverage11.1111%,logicalinterval[0,88.8889]. Existenceentity score88.888889,C11/K2/U5/E7,coverage72.2222%,interval[61.1111,88.8889]. Spatialpair scoreNULL,C0/K0/U55,coverage0%,interval[0,100]. Components use differentunits, notadded. Mainentitycoverage is stricter than oldperentitylocalcompatibility; oldv1.2score77.7778/coverage33.3333 not directly comparable asaccuracy. Improvedscore is lower detectioncoverage, not improvedvideo.

14focusedtestsPASS(.609s),all6actualresponses/witnesscoverage,exactJSONreplay,independentscorearithmetic,input/image/snapshothashes,sixuniquefreshcontexts,equalindependentreviewinputs,policy-before-verdicts,static-onlydisjointpenaltyscopePASS. Audit firstfailed Python tuple vsJSONarray representation, corrected serializationcomparison only; no model/score changes or inferenceretries.442148input+30878output=473026tokens. Existing185272/node241singleCPU only,noGPU/newalloc. No heldout humanaccuracyvalidation.

Report:EECBench/experiments/study2_static_set_consistency_20260916/RESULT.zh.md;run01/RESULT.md has all12+55double-review rows;score.json,replay_audit.json,queries,numeric_relations,auxiliaryinventories,policy,narrative,rawstagecalls preserveactual execution. inputs/narrative_provenance.json,tests.json,comparison.json,post_run_changes.json andreport/audit hashes at experimentroot. Task scope changes andactualrun complete; reliable Study2 spatial scoring remains unresolved.
'''
for name in ['research-log.md','findings.md','docs/continuity.md']:
    p=ROOT/name;oldtext=p.read_text()
    if heading not in oldtext:p.write_text(oldtext+'\n\n'+heading+'\n'+note)
state=ROOT/'research-state.yaml'
entry='''

gs_static_set_consistency_20260916:
  status: implemented_and_study2_actual_run_completed_spatial_coverage_failure
  version: gs-static-set-v1.3
  report: EECBench/experiments/study2_static_set_consistency_20260916/RESULT.zh.md
  design: EECBench/docs/gs-static-set-v1.3.md
  score_scope: frozen_static_entity_sets_only
  auxiliary_motion_entities_scored: false
  allowed_penalty_branches: [unexplained_one_sided_static_presence, common_static_spatial_relation]
  explicit_exemptions: [motion_transition, viewpoint, story]
  narrative_policy: model_inference_all_static_entities_before_verdicts
  story_input: provenance_traced_normal_narrative_without_defect_injection_answers
  static_counts: [17, 21]
  matched_pairs: 11
  one_sided_entities: 12
  spatial_pair_opportunities: 55
  model_calls: 6
  input_tokens: 442148
  output_tokens: 30878
  confirmed_presence_groups: [g03, g22]
  confirmed_spatial_pairs: []
  overall_score_upper_bound: 88.88888888888889
  overall_coverage: 0.1111111111111111
  overall_weights: {compatible: 0, conflict: 2, unknown: 16, exempt: 7}
  existence_score_upper_bound: 88.88888888888889
  existence_coverage: 0.7222222222222222
  spatial_score: null
  spatial_coverage: 0.0
  spatial_weights: {compatible: 0, conflict: 0, unknown: 55, exempt: 0}
  tests_passed: 14
  exact_replay_and_provenance_audit: pass
  real_case_motion_and_story_exemptions: 0
  source_graphs_frames_and_motion_unchanged: true
  old_scores_changed: false
  gpu_calls: 0
  human_accuracy_validated: false
  limitation: uniform_reference_gate_and_uncertain_geometry_limit_spatial_coverage
'''
if 'gs_static_set_consistency_20260916:' not in state.read_text():state.write_text(state.read_text()+entry)
print(BASE/'RESULT.zh.md')
