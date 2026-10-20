# 400 条 prompt 的 schedule 就绪检查

检查时间：2026-09-21T19:09:14.858595+00:00。仅做结构审计，没有模型调用或生产修改。

| 项目 | 数量 |
|---|---:|
| Episode / global prompt | 400 / 400 |
| Shot / per-shot prompt | 2000 / 2000 |
| 源视频实体记录 | 1813 |
| 带 prompt_entity_ids 的 shot | 2000 |
| 包含正式 registry 的 episode | 0 |
| 源实体上的完整 schedule | 0 |
| 包含 claims 的 episode | 0 |
| ID/引用结构错误 | 0 |

全量原始 JSONL 未修改，SHA256：`e124ff566333309b1c1a667408b8aaabb506f4ae9f224253f9f2d6e200c08fb9`。原包 deliverables 未交付独立冻结 schedule/contract。

## 已有格式

采用 `EECBench/docs/prompt-binding-v1.md` 与 `EECBench/docs/prompt-alignment-b-v1.md` 当前顶层四维规则。
`prompt_registry_v1` 包含 ordered shot_ids 和 episode 级实体 ID。每个实体包含 name、description、逐字 prompt evidence，以及覆盖每个 shot 的 schedule（shot_id、expectation、reason）。expectation 为 required / not_required / forbidden / unknown。

required 是镜头内应出现，不要求每帧可见；not_required 不构成不存在/禁止；forbidden 必须来自明确约束；unknown 保留真实歧义。实体 ID 跨整个 episode 共用，场景上下文及衣物属性不自动独立成实体。

`prompt_alignment_b_v1` + `four_dimensions_v1` 另保存原子 claims，维度仅 presence / appearance / spatial / motion。Schedule 本身不能替代颜色、空间关系、动作要求。required/forbidden 行必须对应存在/缺失 claim；其余要求须逐字文本证据、实体及 shot scope、量词、坐标系、依赖。

## Study3 验证范围

参照有9实体、79claims（18 presence / 28 appearance / 17 spatial / 16 motion），由人工文本编译。`study3_final_integrated_20260921/REPORT.md` 记录一次新完整评测；此前离线四维迁移是独立历史结果。最新 comparison_witnesses 绑定扩展仅CPU测试，未进行新完整模型运行。

这证明已有格式可以接入评测；不证明400条自动编译或4/6/8镜头批处理已经通过语义审计。

## 补齐建议（未执行生产编译）

1. 以真正给生成模型的 global+per-shot prompt 冻结 reference_text / facts；源帧说明和 uncertainties 仅保留为来源记录，不自动成为评分要求。
2. 沿用 episode 内实体 ID，保存源 ID 映射；按文本检查实体/实体粒度和完整逐-shot schedule，禁止从源图未出现直接推导 forbidden。
3. 使用现有四维 claim 编译与校验规则；普通外观 when_visible、存在 exists，静止/动作按实际文本，不恢复独立 temporal 维度。
4. 先以4/6/8shot样例验证文本编译的语义覆盖，再处理全400条并导出冻结contract、registry、narrative、hash及可读schedule。
5. 各模型prompt适配必须保留同一冻结实体/要求；短文本删掉了评分要求时，不能仍按完整要求评测并声称公平。

无需据此改写已选定的评分公式或Judge提示词。当前缺口是数据侧输入编译及审计。

本次新增0次模型调用、0tokens、USD0 API费用。
