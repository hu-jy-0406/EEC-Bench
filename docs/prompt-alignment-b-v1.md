# Prompt alignment B v1

## 当前四维版本（2026-09-21 用户修订）

当前只评估 presence、appearance、spatial、motion 四维。独立 temporal（时序/持续性）维度已删除；新编译不生成动作排序、时长或画外持续性要求，也不将它们改名塞入其他维度。四维中的原有静止、空间、可见外观与动作完成要求及其证据门槛保留。

`gs_prompt_alignment.py` 的 schema、编译 prompt、评测 prompt 和聚合器已更新。旧五维合同不能直接用于新评分；显式迁移后冻结为新文件，保留历史：

```bash
python EECBench/scripts/gs_prompt_alignment.py four-dimensions --draft OLD_CONTRACT.json --out NEW_FROZEN_DIRECTORY
```

若保留要求依赖已删除 temporal 要求，迁移明确报错，不能静默移除前置门槛。新 freeze/results 标记 `dimension_profile=four_dimensions_v1`。总体 Pipeline 仍使用 `--prompt-alignment-contract`，现在指向四维合同。

当前 Study3 参照：`EECBench/experiments/prompt_alignment_four_dimensions_20260921/frozen/contract.json`，79 条要求（18/28/17/16），9 个 prompt 实体。对应 `alignment/results.json` 和 `alignment/report.md` 是原始完整判定的离线筛选重汇总，四维分数逐字段不变：100/92.857143/95.238095/100。删除4条 temporal 要求，不再输出 temporal=null。没有新增模型调用，0 tokens/USD0 API；原模型用量单独保存在 reused_historical_usage，不伪装新计费。

19 项 alignment +11 项 binding 测试通过；旧合同/结果保留。以下涉及83条/五维的实验说明是历史，不是当前启用配置。


2026-09-21，用户明确选择方案 B。新的独立评分分支，不改变 temporal_v2、原空间/存在评分、appearance v6、注册方法或旧结果。不实现提案 A/C；不增加二审或模型集成。

## 评测参照先于视频评分

原生成提示词、用于人为制造错误的指令、正常情节评测参照是不同对象。评分只使用正常参照。Study3 正常参照在 `experiments/prompt_alignment_study3_20260921/reference/story_prompt_zh.md`，保留拿走红本→走廊放下→空手返回的情节，并规定黑色台灯、水杯、笔筒的正常外观与位置；没有故意换物、移物或制造不一致的要求。未指定背景物体不自动被禁止。

`prompt_alignment_b_v1` contract 内含完整参照文本、逐字来源 facts、预置 registry/schedule、原子 claims、排除范围。每条 claim 包含维度、prompt entity IDs、镜头范围、谓词/期望值、坐标系、时间量词、同范围前置依赖和原文引句。`freeze` 在观看/评分生成视频前保存 contract/narrative/registry/hash。Study3 是人工按文本编译的 83 条要求、9 个 prompt 实体，脚本不读取视频或已有判定。覆盖材料/颜色、支撑/遮挡、拿起/放下/释放、指定静止、动作顺序等。

可使用文本编译命令，输入仅含 `reference_text, shot_ids, narrative, registry` 四项，独立 Astra/medium 调用，无图像。自动编译仍需检查语义覆盖，结构校验不能保证自然语言的无遗漏或同义去重；当前 Study3 使用已检查的人工清单，不声称自动编译质量已经实测。

```bash
python EECBench/scripts/gs_prompt_alignment.py compile --reference normal_reference.json --out new_text_compile
python EECBench/scripts/gs_prompt_alignment.py freeze --draft authored_contract.json --out frozen_reference
```

## 接入

```text
正常参照 + 预置 registry/schedule → 冻结原子要求
原检测/几何/最终身份 → global_entities → 按该参照绑定 → prompt_alignment
                                              └ 原 appearance 等保持独立
```

新完整集成运行传 `run_gs_integrated.py --prompt-alignment-contract frozen_reference/contract.json`，其余原必需参数照常。合同在前端执行前复制冻结。该参数自动启用绑定；正常参照仅供新分支使用，不替换原 `--narrative` 或既有判断提示词。若同时提供 `--prompt-registry`，必须与合同完全相同。只有 `--stop-after full` 执行 alignment；较早停止保留所请求阶段语义。无此参数的执行计划保持原样；默认注册仍是 FPS32。

已有冻结前端可单独运行：

```bash
python EECBench/scripts/gs_prompt_binding.py run --case CASE --registry frozen_reference/prompt_registry.json --narrative frozen_reference/narrative.json --out NEW_BINDING
python EECBench/scripts/gs_prompt_alignment.py run --case CASE --contract frozen_reference/contract.json --binding NEW_BINDING/results.json --out NEW_ALIGNMENT
```

API/测试在已检查低 CPU 负载的现有自有 Slurm 分配运行；不申请 GPU 或重算几何。新目录强制防止覆盖旧实验。绑定须对应相同 registry 和相同 visual registry hash。来源、要求、原始帧和代码执行前后验 hash；每次调用保留请求、JSON schema、原始响应、事件、usage、运行状态。失败仍记录已知用量和费用不可用项。

## 独立证据核验

同镜头范围的 claims 合并一次 Astra/medium 调用，按范围顺序执行，最多占 1 个 API slot。Study3 有三个单镜头范围和三个明确跨镜头范围。每次 fresh Codex 上下文，禁用工具/技能/项目文档；单镜头不接收其他镜头的实际图像、局部实体/几何或判定。跨镜头要求在单独调用中使用对应的原始镜头。

输入为所有相关原始关键帧、原 2D observations、逐帧 defining 3D/cameras，以及冻结实体对应。保留缺框；省略可精确重建的重复 3D corners 沿用既有 <=1e-9 校验。完整输入有来源记录。**当前使用原始全图和框/几何，不另增裁剪图或密集视频帧**；小物体和短动作可能 unknown。没有跨镜头数值注册转换输入，因此原始世界坐标不能跨镜头相减；跨镜头位置按原图的场景锚点和视角核验，不足则 unknown。已有运动类别/融合框/分数/异常 verdict 一律不输入。

核验不受已有负余弦、moving 类别、绑定是否成功或检测是否完整筛选。所有冻结要求留在账本。检测漏检不等于缺失；required 是该镜头应出现，不是每帧可见；未绑定对象仍检查上下文。绑定是角色对应，不新增跨场景视觉身份边。颜色不符合不使台灯自动变成 unbound。

模型输出 satisfied/violated/unknown、原帧证据、原因、blocked_by。结构校验拒绝遗漏、重复、外来证据和无见证的决定性结论。存在等前置要求未满足时，代码将依赖项保留 unknown，记录 raw_status/修正标记和根因，不重复伪造属性错误；该依赖处理是确定性汇总，不是二次模型审核。单个反例可否定持续要求；稀疏帧不足以证明释放/动作顺序/离画后的持续存在时未知。

## 五类分数

presence / appearance / spatial / motion / temporal 分开。每条已判定要求 T/F；U 是未知。

- 单元为 `prompt entity tuple × shot scope`，单元条件分 `100*T/(T+F)`；无 T/F 则 null。
- 同实体或同关系组内对镜头范围等权，再对实体/关系组等权，得到该维度 score；防止长描述或多视觉碎片主导。
- 并列原始 T/F/U、逐单元结果及 micro 条件分。unknown 单元/实体组显式计数。
- 对每单元保留固定人口区间 `[100*T/N, 100*(T+U)/N]`，按同样层级汇总。它是未知取值边界，不是统计置信区间；条件分不能脱离 U/区间排名。
- 无五维融合总分，不与原一致性或 DINO 融合。父复合要求与同义子要求需在编译时去重；结构校验只保证确切重复不计入，语义去重依赖编译审阅。

产物：`results.json`（全部原子证据及分层分数）、`report.md`、`contract.json`、`source_hashes.json`、`calls/*`、`status.json`。usage/cost 是现有 Astra 标准 API 等价估计，非实际账单。编译、绑定与评分分别计费，集成 summary 按实际调用目录计一次。

## 验证边界

Study3 是冻结前端上的新绑定和新评分组件测试，不是新完整 GPU 运行，不是独立人类标注校准。当前提示词冻结、依赖和评分逻辑已有单元/回归测试；实际语义准确性仍受关键帧密度、材质识别、场景注册信息和 judge 能力影响。实验详情见对应 REPORT.md。

## Study3 开发校正与选定合同

首轮 `frozen/` + `alignment/` 将普通外观属性也编为 `throughout`，在人物离画/遮挡后产生额外未知。这增加了原文本未要求的离画后验证义务。保留完整首轮及其开销，统一把全部 28 条普通外观要求改为 `when_visible`；其余 55 条要求、正常文本、9 实体 registry/schedule、原视频完全不变。差异详见实验 `reference_domain_correction.json`。这项修正定义评测观察范围，不是改判现有输出。

选定参照为 `experiments/prompt_alignment_study3_20260921/frozen_visible/contract.json`。`when_visible` 要求有充分清晰的可见外观证据并检查所有提供帧；可靠反例则 violated，没有可判断的可见证据则 unknown，遮挡或离画本身不使已支持的可见外观成为 unknown。它不声称离画期间的物理持续性，不替换显式 `throughout` 或跨镜头持存要求。修正后在 `alignment_visible/` 全部范围重新调用，没有挑选混合两轮 verdict。绑定因 registry/参照事实未变而复用；费用分别报告。
