# Shot 内仅复核负 cosine

用户于2026-09-20要求：忽略 shot 内缺框，只让 agent 逐个复核负 cosine 实体对，判断真实不一致或数值误差；接入完整流程并验证质量、时间、token/API开销。

## 运行路径

`run_gs_integrated.py --runtime-profile temporal_spatial_v1` → `run_gs_temporal_stage.py within` → `gs_temporal_within_spatial.review`。模型保持 GPT-6 Astra/medium。默认是否选用以 `configs/gs-runtime-profiles.v1.json` 的 selected 为准；temporal_binary_v1保留通用复核回退（同样暂停缺框复核）。

1. 程序保留原始逐帧缺失值，按既有运动二分类与所有关键帧两两组合计算 cosine，不补框或插值。
2. 只向 agent 提交符合原有资格条件的负 cosine 事件。多个时间组合属于同一实体对时，全部事件仍逐项保留。无候选时不调用模型。
3. 同一 shot 每批最多32事件，独立上下文；全部原始关键帧均提供。没有存在性复核、运动重分类或身份重匹配任务。
4. 模型输出逐事件判断和简短依据；共享原图 witness 数组，事件用索引引用。证据不足保留unknown，不强行当成正常或异常。
5. 程序展开为原始事件契约，并执行既有目标帧、正常Prompt、视觉证据门槛；同一实体对最多扣一次分，分母仍为全部枚举实体对。

## 输入精简

本地 `within/SHOT/canonical_review_input.json` 保留完整原始图和运动分类。实际输入保留所有实体、所有原始2D框、每帧3D中心/尺寸/朝向、相机参数、normal-story事实，以及可用于解释几何误差的置信度/截断/离群诊断。角点仅在1e-9重建检查通过时省略，否则原值保留。不舍弃原图、不裁剪降质、不取整、不改变数值候选。

去除仅供身份/配准使用的融合框、重复运动分类描述，以及融合选择权重/eligible/selected和重复source_group；这些字段不决定逐帧 cosine。保留的reason等融合诊断只能解释估计误差，不能充当真实物体运动的视觉证据。

紧凑表格/引用由已有compact transport处理，完整实际输入和wire输入均存档。

## 输出精简

每事件仅输出event_id、status、cause、prompt_verdict、fact引用、witness引用、unverified检查名列表、一个同时涵盖视觉与因果的reason和一个剩余解释。由程序推导空间conflict_kind，并把共享reason映射到原始reason/prompt_explanation。原始11项证据检查使用“未验证字段名列表”编码；遗漏表示模型明确确认，不能为了简短默认通过。解码后仍逐项执行旧门槛，缺目标帧或任一冲突门槛未满足时不能确认冲突。

shot 内presence=null，presence_evaluation_run=false，presence_status=not_evaluated_user_disabled。跨shot存在性、所有跨shot原版prompt、配准和空间分公式不变。没有新总分或外观分。

## 验证与边界

实验目录 `experiments/within_negative_review_20260920`：冻结上游对照和全新完整运行分开记账。固定输入16事件中14详细状态一致，Study2两项unknown→occlusion-exempt；确认异常集合和分数不变。原9个shot内调用661847tokens/$8.12231/累计1432.865秒，新4个调用145923tokens/$1.61567/累计143.922秒。标准API等价费用，非实际账单；不是完整流程墙钟耗时。此对照中的shot内候选没有已确认正例，不能据此宣称真实异常召回率经过全面验证。

完整运行结果与更多质量差异以实验REPORT.md为准；本次还需区分已有集合聚类规则造成的上游实体变化。
