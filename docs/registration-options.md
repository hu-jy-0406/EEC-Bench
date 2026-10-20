> 2026-09-20: integrated scoring now defaults to temporal_v2 (within-shot expected-motion checks + exact tail/head boundary checks). The two registration methods and numerical objective below are unchanged. Historical fused-static scoring is available with `--consistency-protocol flow1_fused_v1`. See [the accepted v2 protocol](temporal-consistency-v2-design.md).

# 固定的两套坐标配准 pipeline

2026-09-19，用户在 Study2、Study3 的四组全流程实验完成并检查实体对应后，明确要求固定这两套 pipeline。以后根据用户要求选择坐标配准方法；其他阶段沿用本次验证的实现。

统一入口：`EECBench/scripts/run_gs_integrated.py`。方法由 `--alignment-method` 指定，每次运行保存 `alignment_method.json`，并在 `summary.json` 中报告。

| 用户指定 | 参数 | 配准流程 |
|---|---|---|
| 优化方法 / FPS32 | `--alignment-method roma_fps32` | Codex 初始身份匹配及 anchor 选择；RoMA 匹配并提升为 anchor 上的有效 3D 点对；确定性联合端点 6D FPS 最多选 32 对；最小化全部选中点对的未平方三维欧氏距离总和 |
| Codex 方法 / 直接估计 | `--alignment-method codex_direct` | 正常 prompt、原始关键帧、各 shot 独立实体和几何输入 Codex，由其直接输出变换参数；配准调用不输入 anchors、跨 shot 匹配或历史变换，不运行 RoMA 或数值优化 |

用户明确指定的方法优先。未指定时沿用既定 FPS32 默认，并在运行说明中标明；不自动回退、混用、同时运行或按分数选择方法。只有用户要求比较时才运行两套。

两者都采用 Shot3 → Shot1 的正尺度（0.1–10）、重力轴 yaw 和三维平移模型。优化方案的目标固定为 `sum_i ||s Rz(theta) Q_i + t - P_i||_2`，各点等权、距离不平方、不按残差删除或降权。置信度下限 0.2；有效点对 3–31 时全部使用，少于 3 时失败。RoMA 保持 precise、当前 6×6 帧对、每对 5000 采样点。

公共流程固定为：所有输入关键帧 WeDetect → 各 shot 独立聚类 → 几何与独立动静判断 → 同场景全实体初始身份匹配 → 所选坐标配准 → 全实体对齐后身份复核 → 静止实体存在性与空间一致性评分。Codex 方法同样保留初始身份匹配调用；该公共调用产生的 anchors 不供直接配准使用。保持 `safe_spatial_medium`、现有模型/推理设置、原图原框、证据门槛和评分公式。单 shot 场景跳过跨 shot 对应；当前几何适配仍限 Shot1/Shot3，辅助 Shot2 仅检测聚类。

Appearance 和独立 prompt 一致性评分尚未实现，不属于本次固定范围。改变固定方案的算法、模型、采样或评分语义须由用户提出或确认；后续实验另存版本和结果。

## 固定基线与验证

四组实验全部完成且审计通过：`study2_fps32`、`study2_codex_direct`、`study3_fps32`、`study3_codex_direct`。参见[完整报告](../experiments/alignment_full_four_20260919/REPORT.md)及[实体对应](../experiments/alignment_full_four_20260919/IDENTITIES.md)。该实验目录保留 138 个源码文件的快照和 SHA256，以及逐运行配置、原始输入和模型输出；固定时已核对当前源码与全部快照一致。

这是已完成测例上的固定实现基线，不保证随机模型调用每次产生完全相同的输出。历史 TopK、高置信度 FPS、角点及混合优化保留为实验结果，不作为正式选项。本次固定不重跑推理，不修改历史结果。
