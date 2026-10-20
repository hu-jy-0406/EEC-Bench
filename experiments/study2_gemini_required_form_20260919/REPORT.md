# Study2 Gemini 必填组 ID 表修复验证

状态：通过。Gemini 3.5 Flash / medium 一次真实复核输出 **29/29** 组，原身份、实体完整性、证据和锚点语义校验全部通过。

用户要求将逐组复核改为填空。Gemini 专用适配器动态生成全部初始组 ID 为必填键，禁止额外键；每个键通过单值 enum 固定关联到一个复核行。模型以正常 JSON 对象填写每行的全部决定与证据字段，共享字段 schema 只传一次。程序严格检查行数恰好等于组数、索引和所有原字段，再恢复原数组接口。不补决定、不填证据、不放松原校验。普通 Codex/Astra pipeline 未改。

## 真实验证

- 同一 Study2 的冻结输入、12 张原始 JPEG、诊断图、初始匹配和配准；输入与来源哈希均未变。
- 只新调用 aligned identity review；这是修复验证，非从头重跑完整 pipeline。
- 复核 29 组，动作计数 `{"keep": 29}`；最终 29 组。
- 最终单侧组检查 18/18；语义校验通过。
- 调用耗时 186.40 秒；输入 215942、输出含思考 46335、合计 262277 tokens；缓存输入 0 已包含在输入内。
- 8 项 CPU 回归测试通过。历史 4/29 和 20/29 回复转换为新表后均被 required-key 校验拒绝。
- CPU：现有 owned allocation 191764 / node306，单个检查为空闲的 core21，nice19，GPU 隐藏，无新资源申请。
- presence/spatial 未运行，没有新的最终评分。单次通过不证明跨样例或多次调用稳定性。

## 接口限制与完整记录

最初把完整嵌套字段在29个 ID 下分别展开，接口返回 HTTP400；共享 `$ref`、缩短字段名、共享 witness 表、无固定内部字段的对象，以及29行 minItems/maxItems 的探针也返回400。原数组 schema、单组对象及必填 ID 对应字符串的探针被接受。JSON 文本值的真实调用填齐29个 ID，但 g01 内部 JSON 转义错误，已判失败且未修补。最终采用必填 ID/固定索引 + 正常 JSON 行数组；接口约束全部 ID 和每行字段，程序约束恰好29行。此版本没有转义字符串。schema 被拒绝的现象与[官方文档的复杂度限制](https://ai.google.dev/gemini-api/docs/structured-output)一致，但服务未给出具体限制值。

首次拒绝保留在 `call/`、`result.json`、`replay.log`；微型探针独立保存，共 61 个已报告 tokens，HTTP400 未返回 usage。JSON 文本值失败保留在 `json_form/`，输入216147、输出含思考41061、合计257208 tokens。最终验证在 `indexed_form/`；原始 API 回复、实际 prompt/schema、表格式回复、解码后的 canonical 回复、usage、源码快照和来源哈希齐全。全部本次已报告用量为 519546 tokens。探针与失败请求没有混入原 CPU 实验账目。

审计：`audit.json`。历史失败实验保持原样。
