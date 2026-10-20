# Study2：Gemini 3.5 Flash 完整 CPU pipeline 测试

**结论：API 可用，新分支已创建并实跑；本次在配准后身份复核被原协议校验截停，没有有效的最终存在性/空间分数。**

## 实际完成与失败

18 张原始 JPEG 从 WeDetect 重新运行：三镜头独立聚类、Shot1/Shot3 GeoCalib、Pi3X、Boxer、隔离动静判断、全实体初始身份匹配、全部36对RoMa匹配和数值配准均完成。Shot2只检测聚类。所有模型调用均为Gemini3.5Flash/medium，未执行Codex CLI。

|配准后身份复核|初始组复核覆盖|非共同组检查覆盖|原完整性校验|
|---|---:|---:|---|
|identity_review_attempt1|4/29|7/24|失败|
|identity_review|20/29|18/18|失败|

两次API响应均完成且JSON schema有效，40个实体均保留；缺失的是协议强制要求的逐组审查证据。第二次为完全相同请求的独立重试，完整请求哈希相同。没有补写遗漏项、修改框或放宽评分门槛。
身份决定也不稳定：第一次把挂画、小桌、桌上植物三组拆分，第二次全部保留匹配。这些均为未通过完整审查的原始响应，不能当作最终身份结论。

## 用量与耗时

共8次Gemini调用（包含失败复核及一次重试），输入668,924、输出含推理112,610，合计 **781,534 tokens**。缓存输入203,275已包含在输入中。
按[官方标准API价格](https://ai.google.dev/gemini-api/docs/pricing)估算 **$1.7425**，不是账户实际账单；不含独立连接探针、开发和审计。价格：未缓存输入$1.50/M、缓存输入$0.15/M、输出含推理$9/M。
本次运行实际墙钟 **2861.57秒（47.69分钟）**，包含CPU重调度、四worker内存保护停止、模型失败及人工处理/重试间隔，不能作为理想生产延迟。

开始四线程串行RoMa，保留本次已完成6对后尝试四个worker；合计RSS达到32.44GiB时触发24GiB保护并停止。随后两个worker各四线程完成剩余30对，峰值20.07GiB。全部使用已分配节点306的CPU；未申请或使用GPU。原36对、每对5000点、precise设置和逐对种子均保留；无历史推理复用。

## 与历史Astra结果的关系

本次聚类Shot1/2/3实体数20/7/20，Shot1/3静态数18/19。候选ID、框、类别、原图与历史Astra完全相同，置信度只有最大5.31e-6浮点差异。Gemini拒绝Shot1黑笔和Shot3两个花盆；Shot1仍把花盆单列，出现跨镜头粒度差异。详细候选集合比较见frontend_comparison.json。
历史Astra完整运行存在性86.6667、空间96.4286，确认台灯消失、纸巾新增和杯子—笔筒关系冲突；本次没有完成B和空间阶段，不能比较这些缺陷的召回率或最终分数。历史还使用GPU几何及旧静态身份总体，不能视为纯模型受控消融。

**目前不宜直接替换默认Astra判断器。** 后续可单独测试：将已有逐组完整性要求进一步编码为Gemini结构化输出约束；该适配尚未实施，也未据此重跑本次测试。原pipeline及默认配置保持不变。

## 产物与审计

入口：EECBench/scripts/run_gs_integrated_gemini.py；CPU入口：EECBench/scripts/run_gs_integrated_gemini_cpu.py；使用说明：EECBench/docs/gs-integrated-gemini.md。
12项适配器与原集成测试通过。停跑审计通过18原图、原候选框、36图像对、同次检查点、源码快照、单镜头图像隔离、全部Gemini请求、相同请求重试和完整token对账；原语义校验的两次失败已独立复现。
详见result.json、audit.json、run01/calls.csv、run01/stages.csv及calls/identity_review_attempt1、calls/identity_review原始响应。

|阶段|状态|秒|tokens|
|---|---|---:|---:|
|detection_and_clustering|success|114.66|65,391|
|geocalib|success|31.09|0|
|prepare_shot_inputs|success|2.08|0|
|pi3x_shot1|success|158.30|0|
|boxer_shot1|success|20.70|0|
|pi3x_shot3|success|153.94|0|
|boxer_shot3|success|22.89|0|
|motion_and_fusion|success|49.16|108,141|
|initial_identity|success|51.17|123,179|
|roma_matches|success|1937.91|0|
|lift_correspondences|success|2.06|0|
|registration|success|2.05|0|
|aligned_identity_review|failed|366.71|484,823|
