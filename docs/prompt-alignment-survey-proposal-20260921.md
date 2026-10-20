# 实体级 Prompt Alignment：调研与设计建议

2026-09-21。**提案，未实现，未改变生产评分。** 核对论文方法、官方项目与仓库；未复现文献评测器。推荐B作为新独立分支，A作baseline，C作长期扩展。

## 文献依据

Prompt alignment与跨帧/跨镜头一致性不是同一目标。一直蓝色的杯子可高度一致，但不符合红杯要求；要求变色时，如实变化反而对齐。VBench和EvalCrafter覆盖多种质量/条件符合维度，EntityBench明确分开prompt-following与跨镜头一致性。

| 工作 | 已核对的方法 | 对本项目的借鉴与限制 |
|---|---|---|
| [VBench](https://openaccess.thecvf.com/content/CVPR2024/papers/Huang_VBench_Comprehensive_Benchmark_Suite_for_Video_Generative_Models_CVPR_2024_paper.pdf)、[EvalCrafter](https://openaccess.thecvf.com/content/CVPR2024/papers/Liu_EvalCrafter_Benchmarking_and_Evaluating_Large_Video_Generation_Models_CVPR_2024_paper.pdf) | 视频质量、条件符合与时间维度分开 | 对齐分不等于整体质量/一致性 |
| [EntityBench，2026](https://arxiv.org/html/2605.15199v1) | scheduled shot-entity的存在/描述符合度；标框多帧的动作主体、动词和交互 | 与registry/schedule最贴近；不直接移植检测为空即absent、单canonical crop或fidelity gate |
| [T2V-CompBench，CVPR2025](https://arxiv.org/abs/2407.14505) / [代码](https://github.com/KaiyueSun98/T2V-CompBench) | 属性/动态属性/空间/运动/动作/交互/数量；MLLM、检测深度和跟踪分工；运动扣除背景 | 按问题路由证据；平均背景补偿不等于任意相机运动下的世界轨迹 |
| [TC-Bench](https://arxiv.org/html/2406.08656v1) | 带帧索引断言，检验转变完成和过程一致性 | 拿起/放下须查初态、过程、末态；严格全断言完成率作为诊断 |
| [ETVA，ICCV2025](https://arxiv.org/html/2503.16867v1) / [代码](https://github.com/guankaisi/ETVA) | 实体/属性/关系生成原子问题，分阶段视频观察及知识辅助，按问答聚合 | 借鉴覆盖去重与逐项核验；无需复制全部多agent/多轮；常识不新增文本要求 |
| [DSG，ICLR2024](https://proceedings.iclr.cc/paper_files/paper/2024/hash/446905abfec9db8856f7f7465bbd5552-Abstract-Conference.html) | 图像原子问题的依赖图，减少重复遗漏和矛盾 | 迁移存在→属性、两实体→关系；本身不处理视频时间 |
| [VBench-2.0](https://arxiv.org/html/2503.21755v1) | 动态空间/属性、动作顺序等VQA或描述对齐 | 动态空间协议明确仅查初末关系，不验证是否同一实体真的移动；不足以作为完整运动评分 |
| [NeuS-V，CVPR2025](https://openaccess.thecvf.com/content/CVPR2025/papers/Sharan_Neuro-Symbolic_Evaluation_of_Text-to-Video_Models_using_Formal_Verification_CVPR_2025_paper.pdf) | Prompt时间逻辑、视频概率自动机、模型检查/校准 | 严格always/eventually/before/until；逻辑严格不能修复视觉命题错误，实现较重 |
| [SG-PVR，2026预印本](https://arxiv.org/html/2606.11838v1) | 时空图、原子计划、视频证据逐项核验；训练型reward model | 适合复用已有图+原像素；仅提示词模仿不等于复现训练效果；建议本项目代码聚合 |
| [VGIF-Score，2026预印本](https://arxiv.org/html/2607.13527v1) / [实现](https://github.com/PRIS-CV/VGIF-SCORE) | ST-DAG实体/属性/位置/动作/状态/依赖，诊断blocked；另有主观质量分支 | 直接相关工作，不能声称原子约束依赖图首创；不采用主客观混合总分 |
| [OSCBench，ACL2026](https://aclanthology.org/2026.acl-long.1425/) | 动作诱发物体状态改变，人类/MLLM评估 | 手动不等于动作完成；借鉴手持→桌面支撑→手空；烹饪结果不证明任意场景泛化 |

补充：[FETV](https://arxiv.org/abs/2311.01813)用于分层校准设计，[VideoScore2](https://arxiv.org/abs/2509.22799)作为训练型整体评测对照。未比较跨论文榜单数字，未验证其公开效果。T2V-CompBench早期/后续规模不同；实施复现需锁版本。

## 三种方案

**A：每镜头结构化rubric。** 原始帧+registry/schedule+绑定，单次返回每实体外观、位置、动作及证据。工程少、调用少；长Prompt易漏项、整体评分较主观。适合作baseline。

**B：冻结原子要求+证据核验+代码汇总（推荐）。** 视频评分前仅从registry/schedule/shot prompt生成要求清单，同任务所有生成模型共用。每条含原文依据、prompt实体ID、镜头/事件范围、谓词、期望值、坐标系、时间量词及依赖。绑定后按镜头一次批量核验，明确跨镜头要求再做相关镜头的事件判断；不是每问题一次API。模型判事实，代码校验和聚合；不默认增加第二审核或ensemble。可解释且复用现有证据，但需验证编译、几何语义与动作采样。

**C：轨迹+时间逻辑。** 在B上增加密集轨迹、接触/支撑状态和事件时间，使用状态机/时间逻辑检查持续、先后、到达、释放、次数。适合复杂时序专项，感知误差传播与成本最高，不建议第一版重建全部3D流程。

这是相对工程判断，非实测API/时间报价；不能用当前binding费用外推。

## 新评分内容

- 存在/数量：预置实体是否出现、数量、明确禁止项。未检测到不等于不存在。
- 外观：只评明确颜色/形状/材质/衣着等，原crop+全图；DINO相似度不是文本符合度。
- 空间：位置/前后/支撑/接触/距离，区分画面、相机、实体朝向和场景坐标；bbox中心高低不能证明on或inside。
- 运动/动作：谁对谁做什么，方向、指定静止状态；扣除摄像机影响，中心位移不等于走路，伸手不等于拿起。
- 时序/完成：初态、过程、末态，顺序、持续、次数；正确端点不证明正确过程。

所有明确Prompt要求都检查，不能只查已有负余弦候选；一直放错的一侧也应判对齐错误。动作人口由文本要求决定，不由观察moving决定；已有binary motion是合理运动预期，不能当实际动作完成证据。未绑定/缺几何/检测人口未覆盖的预置实体保留账本，不能自动跳过或转unbound。

required意为镜头内应出现，不代表每帧可见；要求发生过、始终、先后、直到不可混用。跨硬切不臆测过程。稀疏关键帧可能漏掉短暂手物接触：先原帧评估、不足unknown；可靠动作验证需显式固定更密集采样/原视频证据扩展。新帧不得无声修改冻结实体/候选/原boxes/注册目标。

unbound通常没有单独属性要求，但“仅拿本、其他物体不动”等显式全称/否定约束可以涉及它们；输出清单不穷尽时不能证明全部满足。

## 评分建议

satisfied/violated/unknown，加blocked_by根因；未指定属性not_applicable，不自动满分。复合要求可分诊断子条件，但父要求和其所有子条件不重复计权。

各维报告满足T、明确违反F、未知U；已判定符合率100*T/(T+F)，无已判定则null。不能只用条件分排名，可并列固定要求人口识别区间[100*T/N,100*(T+U)/N]，N=T+F+U。这是未知取值边界，不是统计置信区间；正式单分政策应校准再冻结。仅新alignment使用，不改旧spatial分数/coverage政策。

有充分证据的必需实体缺失是presence违反，检测失败/遮挡是unknown。依赖属性不可凭空满足；逻辑派生失败注明derived而非独立视觉见证。同义要求去重，避免单缺失按十个同义属性重复惩罚。

实体维度按要求→实体×镜头→prompt实体→episode分层汇总，关系按唯一关系要求，时间按事件链；防止描述长/视觉碎片多的对象权重过高。新分支以prompt ID索引证据但不新增跨场景视觉身份边；旧一致性保留global ID及原数学。暂不融合新总分或回灌旧评分gate。

## 接入与Study3

Prompt+registry+schedule → 编译冻结要求；当前WeDetect/几何/身份 → global_entities → prompt_binding → 新prompt_alignment。可与原appearance/within/boundary并行；复用原始证据而非已有分数，保持FPS32/原空间和presence提示词/whole-shot motion不变。

Study3适合测试女子发型衣着、红本颜色/硬封、Shot1拿起离开、Shot2携带→放在指定console→释放后空手、Shot3回到原椅旁站立。木种/微小衣色可能unknown；画面没本不能证明它物理上仍在走廊。

**评分Prompt必须明确。** 原生成指令含故意异常，当前正常评测情节排除了注入说明。对真实生成指令评分时，制造指定变化可以alignment正确而consistency低；对正常情节评分是另一目标。建议分别保存generation_prompt/evaluation_contract/test_intervention并引用原文，不能混用或声称现有5实体清单覆盖完整生成指令。本次不改registry/历史分类。

## 校准计划建议

建议从50–100段/镜头片段及数百要求开始，非已执行工作：固定视频只改颜色/左右/主体/动作/先后；静态化/倒序/删关键过程；纳入相机运动、正确端点错误过程、错误对象动作、伸手未拿、瞬移、遮挡、小对象和重复实例。人类分别标要求编译、绑定、逐项结果与证据；按episode/source分开发与保留集。固定judge比较A/B、全图/crop+全图、稀疏/密集、是否几何；报告错误precision/recall、人机一致率/κ、排序相关、unknown和实际费用/延迟。

研究定位应在多镜头实体绑定、预置schedule、原始几何与不确定性处理的组合及验证；原子问答、时空图和时间逻辑均有直接先例。
