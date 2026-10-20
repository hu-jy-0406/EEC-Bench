> 后续设计：用户已接受DINO算法说明，并指定VLM使用Codex。针对正面/背面等差异的新建议见 [entity-appearance-view-aware-proposal.md](entity-appearance-view-aware-proposal.md)；该多视角方案尚未实施或被选定。

# 实体全部关键帧出现案例的 appearance 评价方案（待用户选定）

日期：2026-09-20。状态：设计建议；未实施外观评分、未修改现有评分 prompt/门槛、未运行新模型。上一轮 episode global registry 已实现，包含逐帧 observations 与原 bbox，但还没有物化 appearance crop/index。

## 查阅依据

- EntityBench 论文 Appendix B.3/B.4/B.5：https://arxiv.org/html/2605.15199v1#A2.SS4
- 官方 evaluator：https://github.com/Catherine-R-He/EntityBench/blob/main/eval/evaluate_benchmark.py
- 本地旧 evaluator：`EntityBench/eval/evaluate_benchmark.py`；可能含本地修改，实际方法以论文和当前官方调用路径为准。

论文按实体-shot 选一个 canonical crop，DINOv2 对全部 canonical embeddings 的归一化中心计算相似度，再选最接近中心的真实 crop 作为 VLM anchor，与其余 crop 逐对比较。人物维度是 face/hair/clothing/build，物体是 shape/color_texture/proportions/details。当前官方主调用路径是 pairwise；不能根据遗留 set-judge 函数或过时注释推断实际路径。它还使用 prompt fidelity gate；此 gate 不宜直接迁移到我们的输出实体自一致性评价，否则可能筛掉应评的外观变化。

## 推荐 v1

保留 frozen global identity；建立逐关键帧 appearance 索引；全量计算 DINOv2 相似度与诊断；用固定的代表 crop 对全部其他案例做结构化 VLM 外观评价。DINO 与 VLM 分开报告，不随意相加。以下是 EEC 的扩展建议，不称为 EntityBench 原样复现。

### 1. Appearance index

每个正检测对应一行，主键 `(global_entity_id, shot_id, frame_id)`，包括：

- appearance_id、global_entity_id、shot_id、local_entity_id、scene_id；
- frame_id、timestamp_sec、原 image_path/image_sha256；
- 原 detector_bbox_xyxy、box_candidate_id、全部 candidate_ids 和各自原框；
- crop_path/crop_sha256、预处理配置、collection evidence 类型；
- 图像可判读性、不可判断原因以及后续的 per-criterion scores。

直接从现有 `global_entities.json.entities[].appearances[].observations` 展平；图像路径/时间从源 raw_manifest 的相同 shot/frame 联接。null bbox 不生成正出现案例，未知观测仍保留在 registry。不得补框、补存在性或用不确定身份加入行。每个实体的所有 supplied keyframes 正出现都进入索引；没有逐视频帧采样承诺。

### 2. Evidence

原始框不可改写。常规实体从原图原框取 crop；可固定加10%上下文边距，但仅写入独立 appearance 预处理字段，不覆盖 detector bbox/3D输入。DINO 使用固定 facebook/dinov2-base 及其固定预处理；VLM 看原分辨率 crop 与必要的原图上下文，避免224输入导致细节不可辨。

集合实体不能用最高分单个成员框充当整个集合。优先使用已有整组检测证据；只有成员框时，保留所有成员原框、成员crop和原帧标注形成集合证据。v1中不将范围不同的“单成员crop”和“整组crop”做直接DINO比较；该情况标记 scope_not_comparable，VLM仍可审查集合证据。集合评成员类型/外观组成、材质/颜色与可见整体形态；没有充分证据不要求精确计数或成员一对一。集合模型证据组织属于待选定方案，尚未修改当前输入语义。

筛选只处理无法可靠判读的证据（极小、严重模糊/遮挡、错误范围等），不因颜色/外形不像参考、DINO低分或不符“黑灯”等描述而筛除。按维度判可观察性：看不清脸不阻止评价清楚的衣服。失败/未知不自动计一致或不一致。

### 3. DINOv2 diagnostics and representative selection

为所有范围可比、可判读的 crop 编码一次并缓存单位向量。计算全部向量余弦矩阵，不需要逐对GPU前向；保存逐案例相似度、低相似度案例以及 shot 内/跨 shot 子矩阵。

为了使多帧shot不淹没其他shot，建议对每个shot内的特征先求均值，再对各shot等权求均值并归一化，作为实体中心；这是相对 EntityBench 单crop/shot 的扩展。选质量合格且最接近中心的实际crop为代表；平分按manifest/frame顺序固定选择。保存中心、选择理由和所有候选质量信息。单个有效案例不能自比较成满分。DINO分是连续相似度，不是正确率，也不直接用未经校准的0.8等阈值定外观冲突。

建议保留首次可靠出现的相似度轨迹作为渐变漂移诊断，尤其当后期多数已变成另一种外观时；它不替换主代表，也不自动重设参考。强视角变化导致无法比较时可弃权；后续多视角参考库需另行验证，不自动选最相似参考来抬高分数。

### 4. VLM appearance judge

沿用当前已配置 Astra/medium 作为首版候选，实现时必须冻结新prompt和schema；这不是EntityBench的Gemini模型复现。每次输入一个固定参考案例和一个目标案例，附原始定位与必要上下文；不输入identity reviewer的判断理由、DINO分数或已知错误标签。身份固定，仅评外观，不能用is_same重新拆全局ID。

- 物体：形状结构、颜色/纹理/材质、相对比例、独特细节。
- 人物：面部形态、发型发色、服饰配件、体型比例；自然动作/表情不自动判外观冲突。
- 集合：适用的物体维度加可见成员组成证据；不得因成员遮挡改变就推断数量异常。

逐维度输出可观察性、1–10一致性分数或null、变化描述和原图证据。位置、镜头角度、透视大小不作为外观错误；光照变化与固有颜色变化分辨不清则该维度unknown。

原始外观变化与合理变化分开记录。正常剧情明确允许的换衣、倒入饮料等可将对应维度/时间区间标为expected_change，不能因此豁免同一实体其他外观变化。不把故事文字用于“必须像最初描述”的过滤。

N个可比较案例通常需要N-1个anchor-target判断，不是N(N-1)/2；每个案例都有记录。首版不以低DINO分触发唯一复核路径，因为高DINO分仍可能存在颜色等重要变化。批量传输多个独立pair可后续验证，但不声称等价或默认采用EntityBench已报告不可靠的整组一次性outlier计数。

### 5. Outputs and aggregation

每个实体保留逐appearance、逐维度分数，异常案例定位、原图bbox、unknown/expected-change记录，以及DINO诊断。参考自身不计满分样本。

主VLM连续分：仅对适用且可判断的非豁免维度求平均，先得到案例分，再在shot内平均，最后在实体涉及的shot间等权平均。明确这是“对固定代表的外观一致性”，不可将它冒称为独立shot内分数。可按维度另报均值及判读数量。若需要episode汇总，建议实体等权（人物/普通物体/集合分开），不是把所有关键帧直接混平均；v1不与存在性/空间分数混成总分。

另报最差可判断案例及其理由，避免只看均值。少于两个可比较案例时分数null。只出现一个shot但有多帧，可评价该shot内外观稳定性；没有跨shot结论。缺框由存在性模块处理；没有外观证据不自动算0或100。报告评测数、unknown数、失败数和预期变化数，防止少量易例高分被解释成全实体稳定；不改变现有空间无coverage规则。

### 6. Minimal validation before adopting

在已冻结全局身份上选Study3黑/白台灯、绿杯、人物，以及新规则未来产生的笔组为例；导出全部现有关键帧案例。先人工标30–50组比较，覆盖视角/光照变化、真实变色、遮挡与集合范围问题。确认固定代表、证据粒度和逐维度判断能区分这些情况，再固定模板扩大运行。新笔组必须来自按新prompt完成的聚类，历史scope_mismatch不得事后伪装修复。此步骤为建议，没有运行或费用承诺。
