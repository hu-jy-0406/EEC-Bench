> 2026-09-21: temporal_v2 now defaults to bounded `--schedule-profile parallel_v1`; `legacy` restores previous scheduling. Model/scoring protocol is unchanged. See [concurrency specification](gs-parallel-scheduling-v1.md).

# 完整 pipeline 的 appearance 接入

2026-09-20 用户确认将选定的 appearance v6 整合到完整 pipeline。

`scripts/run_gs_integrated.py` 默认 `temporal_v2` + `--stop-after full`。
原检测、shot 内聚类、几何、期望运动、全实体身份对应、时序存在性和空间评分保留，
全局实体表完成后自动运行 appearance。配准仍默认 `roma_fps32`；明确指定
`--alignment-method codex_direct` 时使用直接配准，两者均支持 appearance。

## 阶段与范围

1. `global_entity_table`：冻结最终复核后的身份表；只合并确定匹配，保留所有 shot 的实体。
2. `appearance_prepare`：从每个实体全部确定出现的关键帧生成 crop，保存原图、原框和候选归属。
3. `appearance_dino`：原 `gs_entity_appearance.py dino`，固定本地 DINOv2-base 和原公式。
4. `appearance_compact`：原 compact-v3 原生像素拼图和精简输入。
5. `appearance_codex`：每个可评实体一次 Astra/medium 调用，三路有界并发。
6. `appearance_report`：v6 本地严重属性封顶和 episode RMS 汇总。

没有增加核实机制、模型调用或模型输出字段。Codex 与 DINO 独立报告，
不与存在性、空间评分融合。仅在单个 shot 出现的实体也参与该实体已有多帧的稳定性评价；
不足两个 appearance 返回 null。身份歧义不强行合并。

依赖全局身份表的 appearance 可与剩余 CPU/API 时序评价交叠；调度器始终只执行一个 GPU 阶段。
DINO 使用原几何环境，启动前复用原 `guard_gpu.py` 检查利用率、显存、驻留进程和 UUID，
不新增 GPU allocation。

## 入口与提前停止

原来的完整运行命令无需增加参数。`--plan-only` 展示包含 appearance 的执行图。

| 参数 | 结果范围 |
|---|---|
| 默认 / `--stop-after full` | 完整 temporal_v2 + appearance |
| `--stop-after spatial` | 时序存在性、空间评分、全局实体表；不运行 appearance |
| `--stop-after presence` | 只到时序存在性与全局实体表 |
| `--stop-after identity` | 只到身份与全局实体表 |

历史 `--consistency-protocol flow1_fused_v1` 默认仍停在 spatial，不接 appearance；
显式请求该历史协议加 `full` 会报错，避免静默漏跑。
输出必须为新目录，沿用原完整 runner 的“不隐式恢复、不覆盖历史结果”规则。
appearance 任一阶段失败会阻止其后继阶段，整个完整运行不会被标记成功。

## 输出与统计

- `summary.json` 的 `appearance`：独立 Codex/DINO 主分、Codex 普通均分、可评/未知数量，
  全实体/多 shot/单 shot 三组，以及详细文件路径。
- `appearance/canonical/entities/<id>/input.json`：关键帧—原 bbox—crop 对应关系。
- `appearance/canonical/entities/<id>/dino.json`：特征中心相似度及两两诊断。
- `appearance/compact/calls/<id>/`：原 Codex prompt、响应、schema 和 usage。
- `appearance/report/results.json`、`entities.csv`：最终汇总及逐实体原均分/严重封顶/新分数。
- `calls.csv`、`stages.csv`、`summary.json`：包含 appearance 的实际调用 token、阶段时间和标准 API 等价费用。

用量只从调用 `status.json` 计一次；本地 report 的 `reused_*` 字段表示它读取前一模型阶段的结果，
不是再发生一笔费用。总览明确区分模型调用费用与零调用的本地汇总。
缓存 token 属于输入，不重复加总。并行阶段耗时之和不是整体墙钟。
费用使用 2026-09-20 已核实的 Astra 单价，属于标准 API 等价估算，不是账单保证；
失败调用若未提供 usage，统计只包含已知记录。

## 验证范围

见 `experiments/appearance_integration_20260920/REPORT.md`。验证包括原有模块回归、
默认执行图与提前停止、两种配准、费用去重、失败传播，以及 Study2/3 冻结数据的衔接回放。
回放重新生成 crop 与 compact 输入，逐项核对后复用历史 DINO/Codex 结果；禁止新模型调用。
这不是新一轮前端/GPU/付费模型端到端运行。
