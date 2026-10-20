# Appearance v1：Codex 与 DINO 分别报告

2026-09-20 用户选择：暂不融合，直接在 Study2/Study3 测试。本文取代 `entity-appearance-single-call-fusion-v1.md` 中未采用的融合建议。当前是独立下游 runner，不改变 temporal_v2 的 presence/spatial/registration。

入口：`scripts/gs_entity_appearance.py`，依次执行 prepare、codex、dino、summarize。输入为已完成 case 的 `global_entities/global_entities.json`、原始关键帧、shot inventory/candidates 和正常剧情。Study2/3 本次冻结来源为 `experiments/within_negative_review_20260920/full/`，仅 appearance 新计算。未重新做检测、聚类、身份或几何推理。

## 出现表与图像

每个 global entity 的每个正检测关键帧生成一个 appearance，包含原图路径/hash、shot/frame/time、local entity ID、原始 canonical bbox、选中候选 ID、全部归属候选及原始框。无保留检测的帧记录 unknown，不补框、不推断缺失。

每帧全部已归属候选框的 enclosing rectangle，加每侧 10% padding 并截到图像边界，生成派生 crop；这是 appearance 图像预处理，不写回原始 bbox，也不新增检测。此规则同样处理单框、重复检测、人体部件和集合成员；没有用最高置信的一支笔代表整组笔。覆盖所有观测候选仍不保证完整物体/集合可见，Codex 必须记录 scope/visibility 限制。

Codex 每个 appearance 收到两张图：原生分辨率无标记 crop + 原始完整关键帧。图像映射、boxes 与全部观察由 input.json 保存。DINO 只使用同一 crop；没有单独选图或按 Codex 分数筛图。n<2 的实体两项都 null；有多帧的单 shot 实体可评 shot 内稳定性，但无跨 shot 证据。

## 一实体一次 Codex 调用

固定 gpt-6-astra / medium；所有该实体 appearances 和正常剧情进入一次独立上下文，三路有界并发。不见 DINO 分数、不接收历史判分，不改写身份。prompt：`prompts/appearance/entity_v1.txt`。

泛化多视角规则：比对可对应的实际可见部位/表面，区分视角、遮挡、光照、合理形变与真实外观漂移；不把正反面天然不同判错，也不能用“换了视角”无证据豁免。集合比较实际可见范围，未知不能自动计一致。所有帧都进入判断，不能以多数近重复帧淹没少量异常帧。剧情只解释具体属性、具体时段允许的变化，不作为 prompt-fidelity 评分。

四项内部维度：structure_shape、color_texture_material、proportions、distinctive_details，各 0/25/50/75/100 或 null；总分为非 null 维度的算术平均，四项都 null 则总分 null。每个有分维度须引用至少两项 usable/partial appearance。保存逐 appearance 可用性、维度分、证据和解释。程序验证 schema、全部 appearance 顺序覆盖、合法证据 ID、可用 witness 数和分数均值；这不等于证明模型推理正确，需要人工校准。失败保留为失败、不填 0、不静默重试。

## DINO 独立分

参考 EntityBench 的 normalized CLS → normalized centroid → mean cosine，使用本地固定 `facebook/dinov2-base` 权重与 AutoImageProcessor。原模型 processor 会 shortest-edge resize256 + center-crop224；这会裁掉非方形目标的一部分，是当前分数的限制，不能说全部原始像素都进入 embedding。保存 processor 完整配置和模型 hash。

本项目一个 entity-shot 有多个关键帧，故每个 shot 总权重相同：

- n_s 为 shot s 有效 appearance 数，K 为该实体有效 shot 数；每帧 w_i=1/(K*n_s)。
- z_i 为单位长度 CLS；c=normalize(sum_i w_i z_i)。
- D_e=sum_i w_i dot(z_i,c)。不把自相似度作为成对分数加入。

保存每帧 centroid cosine、权重、完整 pairwise cosine 诊断矩阵与 embedding。中心退化/不足两帧时 null。DINO 是原始特征紧致程度，不是正确率，也没有被 VLM 纠正或融合。中心分可能很高，即使不同视角的两两相似度较低；不要把高分解释为每个细节都相同。

EntityBench 原文/实现：https://arxiv.org/html/2605.15199v1 和 https://github.com/Catherine-R-He/EntityBench/blob/main/eval/evaluate_benchmark.py 。关键帧 shot 平衡、下述实体等权以及本项目 Codex rubric 是本项目扩展，不宣称完全复现 EntityBench。

## Study 汇总

两个指标分别对非 null 实体等权均值，保留可评分/总实体数量；不把 null 填 0 或 100。并列报告全部实体、跨 shot 实体（>=2 确定出现 shot）、单 shot 实体三个子集。跨 shot 子集分数仍是那些实体全部 appearance 的整体分，不是额外独立跨 shot pair-only 评分。没有融合分，没有 presence/spatial 总分。

未确定匹配的记录仍分别评分，不能把其单 shot 高分解释为完成跨 shot 验证；不同 scene 不跨场景追踪同一人。本次复用的历史 Shot2 画框集合等保留历史聚类粒度，没有套用最新细化集合 prompt 重新聚类。

## 可复现性与执行

prepare 拒绝覆盖目录、校验冻结源/hash并保留全部证据；推理前与汇总时再次校验源。GPU 必须在已有 Slurm allocation 中经过 idle/VRAM/KFD guard，并以 UUID 绑定。CPU/API runner 使用配置好的 base Python；DINO 使用 vace Python。保留调用 prompt/schema/原始 response/events、usage、模型配置、时间，以及独立源文件快照。费用按实际 usage 和已核验标准 API 价估算，不冒充账单。
