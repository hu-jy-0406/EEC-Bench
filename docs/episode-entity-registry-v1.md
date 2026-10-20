# Episode 全局实体表与集合粒度 v1

2026-09-20 用户明确要求：整个 episode 维护一个实体表，只记录确定的 shot 内出现；确定跨 shot 匹配合并到同一行，身份歧义不补入不确定的 shot；集合粒度后续修订为：清晰独立物体分开，仅对一筐/堆橘子、笔筒里一束笔这类真正集合合并。

## 全局表

当前 `temporal_v2` 在所有 pair 的最终身份复核完成后运行 `gs_episode_entities.py`，输出：

- `global_entities/global_entities.json`：机器可读表、local→global 映射、原观测、确定/歧义关联和源文件哈希。
- `global_entities/global_entities.md`：按 manifest 与 shot 实体顺序排列的可读表。
- `summary.json.global_entity_table`：路径及记录数。导出阶段没有模型调用，计入运行时间，token 为零。

每行包含 `global_entity_id`、首次观察名称、`scene_id`、`observed_shot_ids` 和 `appearances`。每个 appearance 保存本地实体 ID、该 shot 名称、实际检测到的帧、原始逐帧观测，以及原实体文件和候选文件路径。名称可跨 shot 不同，不用名称相等推断身份。未记录的 shot/帧不是不存在判定。

只读取已通过审计的 `identity_review.json`，并核对其 matching 与最终 `matching.json` 相同；不读取初始匹配或静态筛选匹配代替最终全实体对应。先还原 pair-local aliases，再沿确定的一对一匹配建立连通分量。确定链可合并多次出现；不跨越歧义链，不允许同一全局行含同一 shot 的两个不同冻结实体。清单丢失、重复、缺少 pair 或错误 alias 均报错。

- `matched`：两侧记录合并，例如绿杯记录 Shot1、Shot3。
- `unmatched`：保留本地出现，例如黑台灯只记录 Shot1。异常消失与视角原因仍由原存在性阶段判断。
- `ambiguous`：不合并。Shot1 书柜植物的行不记录 Shot3；Shot3 已确定检测到的局部植物独立保留其本地记录，两行用 unresolved link 关联。这不宣称物理上一定有两盆植物。
- `scope_mismatch`：不能据此建立一对一身份。历史单笔/笔组暂时各保留本地记录；通过新聚类规则在新运行的前端统一粒度，不事后伪造历史结果。

全局表收录 episode 的所有 shot，包括独立场景的 Shot2。目前确定合并仍来自现有同 scene 的相邻 occurrence 匹配；不新增跨场景身份推理，也不推测隔着未匹配 shot 的重现。global_records 是记录数，不保证等于真实物理实体总数。appearance 分数尚未实现。

可独立导出历史 temporal_v2 case，输出到新的目录，不修改历史源：

```bash
python EECBench/scripts/gs_episode_entities.py \
  --case /absolute/existing_temporal_case \
  --output /absolute/new_registry_directory
```

历史 `flow1_fused_v1` runner 未接入此导出阶段；本次不改写历史协议。

## 同类集合聚类

当前 `skills/wedetect-shot-entities/review_prompt.txt` 用新规则替换原“单独成员优先、拒绝集合”规则：

- 默认保留清晰可区分的独立物体，包括靠近的两个杯子、几幅独立画框或几个独立靠垫。同类、相邻、接触、同一支撑面都不足以合并。
- 仅把多个物品构成的自然整体（如一筐/堆橘子、笔筒里一束笔）合并为集合；按组织形式和独立区分的意义判断，不设固定数量阈值。真正集合的成员框和整组框归同一节点。
- 一堆橘子、一组笔按整体命名，不能同时输出整体和成员节点。单支成员候选可支持集合，不要求额外的整组候选。
- 不把不同堆、空间分离或独立放置的实例合并；孤立单物仍是单物。容器与内容物分开，如笔筒与笔组。
- 仍按 shot 独立判断；不输入其他 shot 结果，不创造无候选实体，候选必须恰好归属一次。

本次不改变检测框选择：每帧仍取最高置信度原候选框，分数相同按候选 ID 排序。集合节点的选中框可能只覆盖一个成员，不能当作整组范围。全部成员候选及原框可由 canonical input 和 observations.candidate_ids 获取；appearance 的集合证据构建尚待设计。未改变空间 prompt、评分门槛、配准或历史检测结果。

## 验证范围

验证报告：`experiments/episode_entity_registry_20260920/REPORT.md`。使用历史 Study2 的冻结清单/最终身份导出，不重新聚类，不代表新 prompt 的模型行为已验证。


集合粒度后续修订验证：`experiments/collection_granularity_v2_20260920/REPORT.md`。新的独立聚类调用验证Study4两个shot的两杯保持单独节点、Study2笔束仍整体且笔筒独立；未重跑下游身份/得分，橘子例子未有实测样本。
