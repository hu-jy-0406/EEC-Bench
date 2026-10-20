# 配准后身份复核新旧流程切换

用户已确认保留两版、默认新版。当前 `scoring_efficiency_v1` 的 `identity_review_input` 为 `minimal`；正式完整入口/单阶段入口均支持 `--identity-review-input full` 回退，或 `minimal` 显式选择新版。历史 runtime/no-GeoCalib 默认不变。

## 实现与边界

- 新版调用现有 `aligned_centers_sizes_v1` 输入生成器及已验证 minimal prompt；旧版恢复完整 payload、全部原始帧、辅助对齐图、focused old prompt。原 prompt 文件、输出 schema 和 `validate` 函数均未改动。
- 两版均保存完整 canonical 三维数据，沿用原校验。只改模型请求输入；注册、评分公式、身份人口和其他阶段均未修改。
- 完整入口把实际选择写入 runtime/执行计划，阶段状态/request manifest/audit 记录实际版本和哈希。单阶段优先使用保存的 runtime，可显式覆盖。
- 拒绝已有调用目录，在 prepare 之前失败，避免跨版本缓存复用/覆盖。新调用必须使用新输出；下游身份表和评分要基于该次复核重新生成。
- 模型响应语义校验失败会标记失败并保留原始输出/usage，不发布有效匹配。
- 原源码/配置/prompt 保存在 `before/`，变更见 `implementation.patch`，新源码哈希见最终 `audit.json`。

## 自动化及冻结数据验证

52 项回归测试通过（`tests.log`），覆盖配置默认/覆盖、两个编排器、历史兼容性、保存 runtime、正确输入与 prompt 路由、完整 canonical 校验、失败保护和原身份/时序流程。

Study2/3/4 × minimal/full 共六组冻结数据检查通过（`frozen_routing_audit.json`）：通过正式 `run_case`，重建的 canonical 与历史逐值相等；原图逐字节校验，完整/精简输入与对应生成器结果相等；使用此前保存的有效响应通过真实语义校验。此部分不调用模型，不代表六次新模型结果。

正式入口的两次 Study3 新调用结果见下节；仅重跑身份复核，未重跑 WeDetect、GeoCalib、Pi3X、配准或下游评分。旧的 Study2/3/4 完整下游验证另见 `../identity_minimal_full_validation_20260922/REPORT.md`。

## 运行环境

复用已有 allocation 206117 / node306，检查占用后使用 CPU16–17/nice10；GPU 隐藏，BLAS/OMP 单线程；没有新资源申请。`resource_check.json` 保存检查。两个独立正式阶段进程并发调用配置的 Astra/medium。

## 正式入口实测结果

两次调用均成功，使用相同冻结 Study3 上游；本次没有重跑其他评分。

| 流程 | 原帧/辅助图 | 总耗时（秒） | 输入 tokens（含缓存） | 缓存子集 | 输出 tokens | 总 tokens | 估算 API 等价 USD |
|---|---:|---:|---:|---:|---:|---:|---:|
| minimal | 12 | 172.577 | 29267 | 7680 | 5334 | 34601 | 0.490250 |
| full | 13 | 167.139 | 128654 | 0 | 5152 | 133806 | 1.544140 |

并发墙钟 172.880 秒，总计 168,407 tokens / USD 2.034390。费用是按项目2026-09-20已核实的 Astra 标准价格（每百万非缓存输入$10、缓存输入$1、输出$50）计算的 API 等价估算，不是账单；缓存输入属于输入子集，未重复计费。本次两版时延接近，新版未显示更快，不作稳定加速承诺。

全部确认身份链接、锚点 g05/g14、origin/reference 一致。完整分组不完全相同：Shot1 e20 `Plant on side table` / Shot3 e11 `Trailing plant on console table` 在新版为两个 unmatched 单侧组，旧版为一个 ambiguous 组。保留原判断，没有事后统一。此前消融中也有不确定植物分组波动。该差异可能改变下游事件人口，不能据本次仅身份阶段验证宣称下游分数相同。

`live_validation.json` 与 `live/study3_*/` 保存全部新调用、原始结果和费用。`audit.json` 保存最终源码哈希、精确分组差异和通过情况；所有本任务进程已结束。
