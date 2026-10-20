# Study2 / Study3 appearance：独立 Codex 与 DINO 实测

复用 `within_negative_review_20260920/full` 的冻结全局身份表，appearance 全部新算。未重新检测、聚类、注册或计算原有 presence/spatial；没有融合分。每个可评实体一次 Astra/medium 调用，传入全部出现的 crop 与原图。DINOv2-base 独立推理。

| 范围 | Study | Codex可评 / DINO可评 / 总实体 | Codex /100 | DINO centroid cosine |
|---|---|---:|---:|---:|
| 全部实体 | study2 | 34 / 34 / 36 | 98.3456 | 0.910026 |
| 全部实体 | study3 | 33 / 33 / 35 | 96.6540 | 0.911623 |
| 跨 shot 实体子集 | study2 | 9 / 9 / 9 | 94.4444 | 0.865530 |
| 跨 shot 实体子集 | study3 | 10 / 10 / 10 | 89.5833 | 0.858438 |
| 单 shot 实体子集 | study2 | 25 / 25 / 27 | 99.7500 | 0.926045 |
| 单 shot 实体子集 | study3 | 23 / 23 / 25 | 99.7283 | 0.934747 |

两项均采用有效实体等权均值；DINO 每实体内部各 shot 总权重相等。跨 shot 子集仍包含这些实体的全部关键帧，不是单独的跨 shot pair-only 指标。每个 study 两个实体只有一帧，均 null。未知身份不合并，场景间不建立身份链，因此 Shot2 的人物/书等仍独立记录。

## 主要非满分 Codex 结果

| Study | Entity | Name | Codex | DINO | 解释 |
|---|---|---|---:|---:|---|
| study2 | ge0004 | Woman wearing a gray sweater | 75.00 | 0.7399 | 跨镜头的头脸、发型、毛衣及身体比例基本一致；主要不一致集中在裤装腰髋部的剪裁、表面质感和缝褶细节。站起及手臂动作可以解释衣物褶皱变化，但不足以解释整套裤装构造差异。 |
| study2 | ge0016 | Plant pot by window | 83.33 | 0.8637 | 全部帧中盆体在各自镜头内稳定，跨镜头保留锥形陶盆构造和土褐色外观，但盆身由细长变得较宽矮，存在明显比例漂移。 |
| study2 | ge0009 | Trailing plant by window | 91.67 | 0.9350 | 所有帧中植物在各自镜头内稳定；跨镜头保留褐色圆盆、绿色小叶和长垂藤组合，主要可见差异是盆体略变宽矮。叙事未授权植物外观变化。 |
| study2 | ge0023 | Wooden console table | 93.75 | 0.9202 | 六次出现的可见构造和比例一致，主要偏差是末帧木纹变淡、表面趋于平滑。放书及手部遮挡不构成桌体自身变化。 |
| study3 | ge0003 | desk lamp | 62.50 | 0.8380 | 各镜头内部外观稳定，但跨镜头可对应的灯罩、顶颈和底座出现显著黑白变色，并伴随底座形态及细节的小幅变化。叙事没有授权这些外观改变。 |
| study3 | ge0004 | woman | 75.00 | 0.7109 | 人物面部、发型、毛衣和身体比例总体连贯，主要不一致集中在跨镜头裤装的构造、面料观感及前片细节。叙事未授权换装。 |
| study3 | ge0016 | plant pot by window | 75.00 | 0.8497 | 各镜头内部花盆外观稳定；跨镜头保留收底陶盆构造，但盆身高宽比例出现明显变化，并有轻度色调差异。叙事未授权花盆外观改变。 |
| study3 | ge0013 | wooden chair | 83.33 | 0.8520 | 各镜头内部可见部分稳定，跨镜头保留棕色木材和椅背主要轮廓，但内竖条数量及开口布局出现明显变化。叙事未授权椅子结构改变。 |
| study3 | ge0023 | Wooden console table | 93.75 | 0.9202 | 六次出现中的桌体构造和比例稳定，主要差异是末帧木纹变得较平滑。放置书本仅造成局部遮挡，并未授权桌体外观改变。 |

## 使用量与耗时

| Study | 调用 | Input | Cached subset | Output | Token总量 | API等价USD | 调用墙钟分钟 |
|---|---:|---:|---:|---:|---:|---:|---:|
| study2 | 34 | 565,866 | 69,120 | 28,274 | 594,140 | $6.450280 | 5.93 |
| study3 | 33 | 549,351 | 184,320 | 28,660 | 578,011 | $5.267630 | 6.04 |

合计 67 次调用，1,172,151 tokens，标准 API 等价估算 $11.717910；三路有界并发墙钟 11.76 分钟。无自动重试。两 study 调用范围可能交叠，时间不能相加。DINO 474 个 appearance 已完成，时间/config 见各 study 的 dino_runtime.json。
价格核验：2026-09-20 [OpenAI GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra)，普通输入$10/M、缓存输入$1/M、缓存写入$12.5/M、输出$50/M；逐调用适用长上下文规则。缓存输入为输入子集，没有重复计算；reasoning token 是 output 子集，不再另加。标准 API 等价费用，不是账单，不包含本对话和 GPU。

## 验证与限制

5项 CPU 测试通过；audit.json 校验全部冻结实体/appearance 的保全、原图/原框/hash不变、附件映射、Codex证据ID/维度均值和独立重算DINO/汇总分。GPU使用现有job196093/node197，启动前guard核验idle/VRAM/KFD并绑定GPU UUID；DINO完成后退出，无新allocation。
模型结果是首轮诊断，没有人工真值标定；本次样例不能证明适用于所有物体/视角。DINO默认processor的center crop可能截去细长实体边部；小物体、遮挡和背景进入crop也会影响分数。Codex只对可比较属性评分，未显示表面不代表验证一致。
历史Shot2画框集合保留旧粒度；当前更严格“独立物体分开、真实集合合并”规则未对这些冻结来源重新执行。该限制不隐藏，也不在appearance阶段改身份。
逐实体：study2/REPORT.md、study3/REPORT.md 与 entities.csv；统一appearance表：appearance_table.json、appearances.csv；全部appearance原框/crop映射：entities/ge*/input.json；原始模型证据：calls/ge*/；特征和诊断：dino_embeddings.npz、entities/ge*/dino.json。协议见 EECBench/docs/entity-appearance-separate-v1.md。

人工抽查待复核项：Study2/ge0009植物的扣分理由主要涉及盆体，但花盆另有ge0016实体，存在同一花盆变化重复归因的风险。尚无精确实体范围标注，故标为potential_scope_leakage，而非已确认误报。本轮保留全部原始分数，没有见到结果后改prompt/重跑。详见manual_review_flags.json及visual_spot_checks.md。
