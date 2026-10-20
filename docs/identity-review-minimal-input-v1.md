# 配准后身份复核：最简实测输入 v1

配置名：`aligned_centers_sizes_v1`。输入导出器：`scripts/gs_identity_review_minimal_input.py`。模型仍是 GPT-6 Astra / medium，完整逐组身份复核、focused 输出、原帧见证与身份/锚点校验不变。实验在 `experiments/identity_input_ablation_20260922/`。

这是本次完成跨 Study2/3/4、每组三次重复验证的候选中输入最小的一档。质量承诺限于已验证结论：全部确认身份、锚点、参考实体、实体清单及冻结端点数值保持；完整身份分组存在原完整输入也出现过的植物 ambiguous/unmatched 波动。不能宣称每个未知项完全相同、身份100%正确或统计非劣。消融实验完成时未切换默认；2026-09-22 经完整下游验证和用户确认后，当前生产默认已切为此档，旧版可显式切回（见下节）。

## 正式入口与旧版切换（2026-09-22）

当前 `scoring_efficiency_v1` 默认使用 `minimal`（输入版本 `aligned_centers_sizes_v1`）。在原有完整运行命令中选择：

```bash
# 新版：可省略此参数，当前生产配置默认即为新版
--identity-review-input minimal

# 旧版：恢复完整输入及旧提示词，其他阶段设置不变
--identity-review-input full
```

两者均由 `scripts/run_gs_integrated.py` 正式支持，覆盖 temporal_v2 和历史 Flow1 编排。完整旧版输入使用 `gs_aligned_identity_scoring_v1.txt`、全部原帧及辅助对齐图；新版使用已验证的 `gs_aligned_identity_minimal_v1.txt`。两者沿用相同 focused 输出 schema、Astra/medium 和完整 canonical 身份/锚点/见证校验。旧的 legacy 输出协议及 `gs_aligned_identity_review_v1.txt` 也继续保留。

仅重跑准备好的配准后复核，可用下列正式阶段入口（应在已分配计算节点运行）：

```bash
python EECBench/scripts/run_gs_flow1_stage.py /absolute/path/to/fresh/pair_case \
  review_identity --runtime-profile scoring_efficiency_v1 \
  --identity-review-input full
```

切回新版时将 `full` 改成 `minimal`。不要更改已完成实验：完整 runner 拒绝已有输出目录，阶段入口及底层复核拒绝已有 `calls/identity_review`，必须使用新的 case/output。复核结果变化后，下游身份表和评分也必须重新生成，不能混用另一版本的旧评分。

参数优先于所选 runtime 的默认值。单独阶段未指定 `--runtime-profile` 时优先读取该 case 保存的 `runtime_profile.json`；显式指定 runtime 则采用该配置，再应用输入参数。完整编排将最终选择写入执行命令及 runtime 快照，因此后续默认变化不会改变已有计划的输入版本。其他历史 runtime 和实验性 `gravity_free_v1` 保留 `full` 默认；不支持 focused 输出的历史 runtime 会明确拒绝 `minimal`，不自动更换协议。

每次保存 `identity_review_request.json`（输入版本、提示词/输入/schema 哈希、模型设置及图片哈希），并在 `identity_review_audit.json`、阶段状态中记录选择。完整 `identity_review_payload.json` 和全部三维数据仍保留，本次模型输入单独保存在 `calls/identity_review/input.json`。模型返回不通过语义校验时保留原始输出及 token 记录，将状态记为失败，不发布有效匹配。

接入验证记录：`experiments/identity_review_switch_20260922/REPORT.md`。此前完整下游验证见 `experiments/identity_minimal_full_validation_20260922/REPORT.md`；后者复用了上游，不是新一轮完整 GPU 运行。

## 模型收到什么

1. **全部原始帧**：两侧每个原始关键帧，原始字节/分辨率不变；帧索引和图片尺寸保留。本次每组共12张。
2. **冻结实体与逐帧二维观测**：`entity_id/name/motion_status`，每帧 `frame_id/exist/visible/box_xyxy`。坐标不取整，不修框，不删实体/空观测；运动实体和没有3D的实体也保留。
3. **每实体一份已对齐的代表中心与尺寸**：`aligned_geometry.center_world` 和 `size_xyz`，没有几何则保留 null。中心已经处于共同 Shot1 坐标系；尺寸为物体自身三轴边长，未提供旋转时不能把它们当成世界轴包围范围。移动实体的代表框不是其他帧的位置承诺。
4. **完整初始身份假设与锚点/参考选择**：保留分组、初始理由和资格，供模型挑战。初始理由不是事实真值。
5. **正常情节 Prompt 事实**：保留相关中间镜头的因果信息，不传故意制造不一致的目标或预期评分。
6. **少量坐标/配准元信息**：统一坐标系说明、原数值配准质量摘要及其诊断限制、既有不确定性规则、原配准目标说明。历史 train/spatial_holdout 标签不是独立验证。

仍采用已有无损表格/引用传输，实体分组以 unchanged-group 引用及 revised-groups 返回，每组审核行保留。输出语言、推理档、证据门槛和调用数没有因这次输入简化改变。

## 从模型输入中删除什么

- 原坐标系的重复三维框和相机参数；已对齐坐标不要求模型再次计算变换。
- 逐帧完整3D框、三维轨迹、旋转矩阵、八角点。
- 聚合权重、选帧/拒绝帧、逐实体中心/尺寸MAD等融合元数据。
- 跨视角中心投影与图像内外布尔诊断。
- 可以从中心/尺寸计算的配对距离、位移向量与归一化距离摘要。
- 辅助对齐图。
- 检测候选ID、逐帧重复说明、上游运动分类的重复理由。

上述信息只从**此次模型请求**中移除。完整 canonical 文件、原始图片、检测候选归属、配准、原始逐帧评分几何全部留在本地，位移与 cosine 的数值计算继续使用完整原数据。

## 导出和复现

```bash
python EECBench/scripts/gs_identity_review_minimal_input.py \
  --case /absolute/path/to/run/pairs/pair_000 \
  --out /absolute/path/to/new/minimal_input \
  --profile aligned_centers_sizes_v1
```

输出 `input.json`、`images.json`、`manifest.json`。导出器逐字节验证原始图片，保留输入来源哈希，拒绝覆盖现有输出。该命令本身不调用模型。

实际验证的 prompt 保存在 `prompts/gs_aligned_identity_minimal_v1.txt`，与本实验 `prompt.txt` 相同。模型调用使用现有 `gs_efficient_transport.call('identity_review', ...)` 和 `FOCUSED_SCHEMA`；返回后始终用**完整 canonical payload**执行现有 `validate(..., FOCUSED_PROTOCOL)`，不要把删减后的模型输入当成评分几何或校验依据。

导出器另提供两个实验档：`aligned_center_trajectories_v1`、`aligned_center_trajectories_min_v1`，分别对应保留简短逐帧中心轨迹并保留/删除重复摘要；不是当前最简建议。任何新输入范围、其他模型/推理档或 no-GeoCalib 几何都不在本次验证承诺内。

## 质量与时间边界

- 每组3次最终候选，逐实体比较完整分组、确认链接、锚点资格/选择/参考，验证原始帧见证、完整实体范围、图像哈希和生成器与实际请求逐值相等。
- 冻结几何上的 cosine/中心距离及其比较人口经过本地重算。没有重跑下游存在性、空间复核、外观或 prompt alignment 的模型判定，不能把局部审计称作完整端到端等价。
- 不确定植物的 ambiguous/unmatched 表达会影响存在性事件人口；完整输入也有这一波动。原始结果和全部差异均保留，未事后统一标签。
- 输入/费用减少显著；模型仍需审查全部实体并输出见证，实际延迟改善有限且有波动。具体 tokens、缓存、API等价费用和时间见实验报告，不承诺未来固定费用或加速。
