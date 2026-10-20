> 2026-09-21: temporal_v2 now defaults to bounded `--schedule-profile parallel_v1`; `legacy` restores previous scheduling. Model/scoring protocol is unchanged. See [concurrency specification](gs-parallel-scheduling-v1.md).

> 2026-09-20 current default: temporal_v2 `--stop-after full` includes the selected appearance v6 after the global entity table, reporting Codex and DINO separately. Explicit `--stop-after spatial` omits appearance; historical flow1_fused_v1 retains its spatial default. See [current integration](gs-integrated-appearance-v6.md). The Flow1 tables below describe the historical protocol.

> 2026-09-20: current temporal_v2 also exports an episode global entity table after final identity review. Only confirmed matches merge; new shot clustering groups nearby same-kind objects (e.g. pens/oranges). See [episode-entity-registry-v1.md](episode-entity-registry-v1.md). Historical outputs and flow1_fused_v1 remain historical.

> 2026-09-20: integrated scoring now defaults to temporal_v2 (within-shot expected-motion checks + exact tail/head boundary checks). The two registration methods and numerical objective below are unchanged. Historical fused-static scoring is available with `--consistency-protocol flow1_fused_v1`. See [the accepted v2 protocol](temporal-consistency-v2-design.md).

# 简化流程1：从原始帧到跨 shot 分类

统一入口：`EECBench/scripts/run_gs_integrated.py`。输入两个同场景 shot 的原始 JPEG 清单和正常剧情事实，默认运行至两个最终分数；B 后接原空间关系 cosine、独立局部取证与最终 Prompt 复核。`--stop-after presence` 可只运行前两段至 B 分类。

## 执行顺序

| 阶段 | 当前规则 | Codex 调用 |
|---|---|---:|
| WeDetect-Anything | 检测全部原始关键帧，不重编码输入 | 0 |
| 单 shot 聚类 | 每个 shot 独立；紧凑候选输入，只输出命名候选簇及拒绝项；框由程序复制检测器原框，无补框/修框 | 每 shot 1 次 |
| 逐帧几何 | GeoCalib、Pi3X、深度条件 Boxer；每帧独立相机位姿，统一到各自 shot 的固定场景系 | 0 |
| 动静划分与融合 | 每个 shot 独立上下文，静止实体融合框，运动实体代表框及逐帧轨迹；无检测框时存在性未知 | 每 shot 1 次 |
| 初始 A＋A′ | 完整静态实体身份对应，选择高置信度结构参照；使用紧凑输入 | 1 次 |
| 场景配准 | 原 RoMa 多帧匹配、结构筛选、深度提升、重力约束尺度/旋转/平移拟合 | 0 |
| 对齐后身份复核 | 原帧＋对齐框＋投影与误差，复核全部身份组及参照 | 1 次 |
| B 分类 | 共现：判断是否应离场却仍出现；非共现：视角／运动／不一致。一次判断，保留原帧证据和 Prompt 门槛 | 1 次 |

两 shot 到 B 共 **7 次 Codex 调用**；空间阶段在有负候选且参照有效时增加两次独立取证，有通过支撑筛选的候选时再增加一次最终复核，完整运行最多 **10 次 Codex 调用**，均为 `gpt-6-astra / medium`。这是调用结构，非新实验的实测耗时/token。B 判断不能改写身份组，失败证据或待定身份记未知。身份与存在性分组结果直接供原空间关系阶段使用。

## 输入与运行

Manifest 沿用 WeDetect skill 的 `shots[].frames[]` 格式，路径相对 manifest；包含所有原始关键帧，不抽样。当前几何接口接受 `shot1`、`shot3` 两个 ID，每个 shot 内尺寸固定，两个 shot 之间可不同。正常剧情 JSON 使用已有 `facts` 格式，每条有唯一 `fact_id`，含相关中间镜头动作；不加入预期冲突或期望分数。

在已分配的自有计算节点，检查 GPU 使用率、显存及 KFD 驻留进程后运行：

```bash
python EECBench/scripts/run_gs_integrated.py \
  --manifest /absolute/raw_manifest.json \
  --narrative /absolute/narrative.json \
  --output /absolute/new_case \
  --gpu PHYSICAL_INDEX --gpu-uuid GPU-VERIFIED_UUID
```

`--plan-only` 只输出执行命令，不创建运行目录、不调用模型。输出目录必须不存在；不隐式恢复失败任务或复用历史推理。每个 GPU 阶段启动前重新检查并绑定 UUID。沿用已安装几何环境、模型权重和原几何/配准代码；模型元数据来源可用 `--model-manifest` 指定，GeoCalib 权重用 `--geocalib-weights` 指定。历史实验目录中的几何脚本是代码依赖，不读取其历史实体、框、配准或分类结果；数据由本次 `CASE_ROOT` 提供。

## 输出与衔接

- `entities/`：本次检测、紧凑聚类请求/响应、原框及候选来源。
- `inputs/`、`pi3x/`：本次几何输入和逐帧几何。
- `selected/`：每 shot 完整实体图和静态图，保留运动实体逐帧证据。
- `matching_initial.json`、`matching.json`、`identity_review*.json`：初始身份和复核后的身份。
- `registration/`：本次多帧匹配及统一场景变换。
- `presence.json`：单次 B 分类、证据门槛结果和存在性分数，版本 `single_presence_witness_v1`。
- `all_pair_cosines.json`、`negative_proposals.json`、`spatial.json`：全部实体对、负候选及原流程复核后的空间关系分数。
- `pipeline_runtime.json`、`stages.csv`：阶段时间、状态及 token；失败后停止下游。
- `calls.csv`、`summary.json`：逐调用时间与输入/输出/缓存 token；缓存属于输入，不重复累加。检测准备与并行聚类时间另行记录，阶段并行调用不能按耗时之和当作墙钟时间。
- `provenance.json`、`config_snapshot.json`：原帧哈希（manifest）、代码哈希、权重元数据来源及本次配置。

使用 `--stop-after presence` 完成分类的 case，可单独执行 `run_gs_flow1_stage.py CASE spatial`。默认完整运行会直接执行这一阶段。

## 验证状态

7项整合测试、8项单次B测试和离线接口审计通过。Study2 Shot1/Shot3 已完成一次全新完整模型运行：12张原始JPEG，全部重新检测/聚类/几何/动静/身份/配准/分类/空间复核，10次gpt-6-astra/medium调用。静止实体分86.666667、空间关系分96.428571；确认台灯缺失、纸巾新增、杯子与笔筒的空间冲突。总墙钟1429.936秒，656,483 tokens。

[完整实测报告](../experiments/study2_integrated_full_fresh_20260919/REPORT.md)记录每阶段及逐调用时间/token、全部cosine与审计。仅为单个case的一次完整验证，不代表多case准确率或稳定速度。

## Runtime profiles and auxiliary Shot2 (2026-09-19)

Default: `temporal_binary_v1`, selected in `configs/gs-runtime-profiles.v1.json`. Expected motion now uses one whole-shot binary decision with compact input and GPT-6 Astra/medium. Initial identity, aligned review and presence retain their existing medium settings; the three boundary spatial calls retain efficient transport and low reasoning. `temporal_cost_v1` restores interval motion, while `safe_spatial_medium` restores the earlier temporal runtime settings. Runtime rollback retains the shared sign-serialization bug fix. RoMa image matching may overlap CPU/API work, with one GPU workload at a time; point filtering/registration waits for selected anchors. See the current binary-motion contract below.

Use `--runtime-profile baseline` to reproduce the original sequential transport. `efficient_astra_low` and `efficient_astra_medium` are experimental, explicitly selectable profiles; neither is the default because fixed-input tests changed per-entity viewpoint/unknown classifications.

In legacy `flow1_fused_v1`, optional Shot2 stops after detection and clustering and its calls count under `auxiliary_clustering_counts`. Current `temporal_v2` processes every supplied shot through geometry, isolated motion classification and within-shot review; only same-scene boundaries receive cross-shot comparison.

Current measured comparisons, per-call tokens, quality differences, and clearly labeled full-runtime estimates: [optimization report](../experiments/gs_latency_cost_20260919/REPORT.md). The 10–15 minute and $1 targets have not both been demonstrated with unchanged per-entity judgments.


## 全实体身份对应（2026-09-19）

初始匹配与配准后身份复核覆盖冻结清单中的所有实体：静止、运动、运动状态未知。保留原始检测框、运动标签及逐帧几何；缺少 3D 框时仍利用原图和 2D 观测参与对应。运动状态不同不阻止同一身份匹配；有其他身份证据时，外观漂移本身不能成为拆分身份的唯一理由。

`matching.json` / `identity_review.json` 保存完整身份对应，供后续 appearance 评测使用；`matching_static.json` 为已有存在性/空间评分的静止子集。包含非静止成员的整组不进入静止评分，并在 `presence.json.excluded_nonstatic_identity_group_ids` 记录；不将运动对应物删除后误报为静止对象缺失。配准锚点必须在两侧均静止且有几何。

可在 manifest 每个 shot 上填写 `scene_id`，例如 Shot1/Shot3 为 `room`、Shot2 为 `corridor`。一旦填写，所有 shot 都须显式填写。`identity_scope.json` 保存场景、需比较的 shot 对及单 shot 跳过原因。只有单 shot 场景时，集成执行止于检测/聚类，不进行跨 shot 匹配或产生两个一致性分数。无 scene_id 的旧 manifest 仍按 Shot1/Shot3 同场景、Shot2 单独场景解释。

当前几何适配器仍限定 Shot1/Shot3 比较。其他多 shot 组合明确报错，需要独立 pair case；本次未实现任意多 shot 的全局身份合并。仅扩展身份阶段，appearance 分数和独立 prompt 一致性分数尚未实现。历史实验和全流程质量/耗时结论保留其原始静止实体范围；新范围需另做实际模型验证。


只检查跨 shot 身份对应时使用 `--stop-after identity`：保留全部检测/聚类、动静、配准和对齐后复核，止于 `identity_review.json` / `matching.json`，不调用 B 或空间评分。summary.json 明确标记 presence_evaluation_run=false。


## Registration objective (2026-09-19 user correction)

The default registration stage is `scripts/register_gs_3d.py`, backed by `gs_registration_3d.py`. It fits ALL selected 3D correspondence rows by minimizing `sum_i ||s Rz(theta) Q_i+t-P_i||_2`, with equal point weights, unsquared distances, no residual trimming/clipping, and no reprojection objective. Historical train/holdout labels are descriptive only because both subsets enter this fit. Existing positive scale [0.1,10], gravity-axis yaw and translation remain. The multi-start solver reports convergence without certifying a global optimum. Registration-only reruns use `--case CASE --method roma --output NEW/registration.json`; existing results cannot be overwritten. Fresh integrated runs write their new default registration in the usual case location. Historical `experiments/study2_full_fresh_20260918/register.py` retains the old objective for provenance and diagnostic projection functions.


## FPS32 default (2026-09-19, explicit user selection)

The default registration now selects up to32 pairs with the validated deterministic joint-endpoint6D FPS (confidence floor0.2 unchanged), from the full valid lifted anchor pool across both legacy partitions. If3–31eligible pairs are available, use all; fewer than3fails. Every selected pair contributes equally to the exact unsquared3D Euclidean-distance sum, with no residual-based deletion or reweighting. `register_gs_3d.py --sampling all` retains full-pool fitting for explicit comparisons. Save selected row indices, separate selection/optimization timings, selected fitting error and full-pool diagnostics. Legacy partitions are NOT independent holdouts. RoMA still uses36pairs for the current6×6inputs, precise setting and5000sampled matches perpair; reducing upstream RoMA work is not yet adopted.


## 两套 pipeline 固定（2026-09-19）

Study2/Study3 × FPS32/Codex 的四组全流程实验已完成并通过审计。用户要求将两套实现固定，以 `--alignment-method roma_fps32|codex_direct` 按指令选择。当前规范、公共步骤及基线快照见 [registration-options.md](registration-options.md)；未指定时沿用并说明 FPS32 默认，无自动切换。此前“待新模型验证”等叙述保留其历史范围，本次完成情况以四组[实验报告](../experiments/alignment_full_four_20260919/REPORT.md)为准。


## 2026-09-20 temporal cost profile

`temporal_cost_v1` keeps all GPT-6 Astra medium stages except the three boundary spatial calls, which use validated lossless/compact input-output transport and low reasoning. Two isolated local spatial calls run concurrently, then final verification runs. No frame/entity removal, geometry rounding, prompt-prefix changes or gate changes. Other temporal stages retain original transport after broader compression showed per-entity classification drift.

Study2/3/4 frozen-upstream component tests and composition audits preserve every final event status and score. Estimated combined production cost falls from $47.004546 / 3,883,009 tokens to $41.885576 / 3,397,860 tokens; these are standard API equivalents using recorded component usage, not a fresh end-to-end measurement or bill. See `experiments/temporal_cost_quality_20260920/REPORT.md` for separate validation cost and latency estimates. Roll back with `--runtime-profile safe_spatial_medium`.


Current whole-shot binary motion supersedes the earlier interval profile descriptions above. See [the binary motion contract](shot-motion-binary-v1.md) and [validation/cost report](../experiments/shot_binary_motion_20260920/REPORT.md). `temporal_cost_v1` explicitly restores interval inference; `safe_spatial_medium` restores the pre-optimization temporal runtime.
