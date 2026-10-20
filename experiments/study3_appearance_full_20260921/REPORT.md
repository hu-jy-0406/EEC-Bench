# Study3 台灯变色：从 WeDetect 开始的完整新运行（2026-09-21）

本轮新做全部18张原始关键帧的检测、三次独立shot聚类、GeoCalib/Pi3X/Boxer、动静判断、跨shot身份、RoMa/FPS32配准、身份复核、时序评分、DINO和Codex appearance。没有复用历史推理。使用 temporal_v2 / temporal_spatial_v1 / roma_fps32 / full，未修改模型prompt、评分门槛或配准目标。

## 结果

| 指标 | 分数 | 说明 |
|---|---:|---|
| Codex appearance v6 | 85.002383 | 36实体，34可评，2个单appearance实体不评分 |
| DINO | 0.913816651 | 与Codex分别报告 |
| Codex普通实体均分（辅助） | 95.343137 | 主分采用RMS缺陷汇总 |
| 跨shot存在性 | 91.666667 | C=9、K=1、U=2、E=18 |
| 跨shot空间 | 97.777778 | 45对中1对确认冲突 |
| Shot1/Shot2/Shot3内部空间 | 100 / 100 / 100 | 各190/15/190对，无确认冲突；内部存在性按当前协议不评 |

台灯在初始匹配与最终复核中均保持同一实体 ge0003，覆盖Shot1/Shot3。Codex明确指出灯罩和底座黑→乳白，不能由反向视角或光照解释。属性为100/25/75/100，原均分75，v6严重属性封顶后的实体分25。
跨shot存在性确认新增纸巾包；空间确认深绿杯与笔筒的相对关系冲突。未知诊断仍保留，不解释为空间覆盖失败。

相对上一轮冻结v3重算的Study3（Codex85.403145，DINO0.911623149），本轮为85.002383/0.913816651。实体表由35变36、appearances由234变240，可评由33变34：这是从前端开始的新运行，不能把变化全部归因于评分随机性或声称固定输入完全复现。台灯的最终25分保持。

## 实测耗时与费用

完整runner墙钟 **1674.647秒 = 27.91分钟**（约27分55秒）。不含启动前资源/输入检查、受沙箱拦截的Slurm启动等待和结束后的本地审计。
本轮 **48次新模型调用，1,049,420 tokens，US$12.114328标准API等价估算**。不代表实际CLI账单，不含本对话及集群费用。
输入1,004,424，其中缓存读取19,968、缓存写入0；输出44,996。缓存属于输入，reasoning属于输出，均不重复累加。
Appearance五阶段合计440.051秒，34次调用，217,540tokens / US$2.377648，已包含在整轮总账。与跨shot边界评分并行，阶段耗时相加不等于总墙钟。

按[2026-09-21核实的官方标准价格](https://developers.openai.com/api/docs/pricing)：每百万输入/缓存读取/缓存写入/输出分别US$10/$1/$12.5/$50，逐调用考虑长上下文价格；见pricing.json。

| 阶段 | 秒 | tokens | API等价USD |
|---|---:|---:|---:|
| detection_and_clustering | 110.41 | 46,398 | 0.514260 |
| geocalib | 88.94 | 0 | 0.000000 |
| prepare_shot_inputs | 0.95 | 0 | 0.000000 |
| pi3x_shot1 | 91.15 | 0 | 0.000000 |
| boxer_shot1 | 35.05 | 0 | 0.000000 |
| pi3x_shot2 | 50.53 | 0 | 0.000000 |
| boxer_shot2 | 36.45 | 0 | 0.000000 |
| pi3x_shot3 | 66.17 | 0 | 0.000000 |
| boxer_shot3 | 32.98 | 0 | 0.000000 |
| expected_motion_shot1 | 56.37 | 29,974 | 0.343660 |
| expected_motion_shot2 | 30.45 | 19,638 | 0.210020 |
| within_shot2 | 0.88 | 0 | 0.000000 |
| expected_motion_shot3 | 55.20 | 32,050 | 0.362860 |
| within_shot1 | 42.65 | 36,930 | 0.399220 |
| within_shot3 | 49.49 | 39,589 | 0.435410 |
| pair_000_prepare | 0.55 | 0 | 0.000000 |
| pair_000_initial_identity | 138.17 | 80,733 | 0.965850 |
| pair_000_roma_matches | 175.06 | 0 | 0.000000 |
| pair_000_lift | 3.66 | 0 | 0.000000 |
| pair_000_registration | 0.95 | 0 | 0.000000 |
| pair_000_identity_review | 405.90 | 140,950 | 1.918420 |
| pair_000_boundary | 437.04 | 405,618 | 4.586980 |
| global_entity_table | 0.29 | 0 | 0.000000 |
| appearance_prepare | 11.74 | 0 | 0.000000 |
| appearance_dino | 89.29 | 0 | 0.000000 |
| appearance_compact | 7.71 | 0 | 0.000000 |
| appearance_codex | 325.35 | 217,540 | 2.377648 |
| appearance_report | 5.96 | 0 | 0.000000 |

身份复核405.90秒、跨shot边界437.04秒、appearance Codex325.35秒是主要API耗时。DINO阶段89.29秒含启动/空闲GPU检查/模型加载等，其中脚本报告的共享起点计算时间28.84秒，不应将两者混为一个计时口径。

## 完整性与运行记录

审计通过：18张原图hash不变、59份固定代码/config/prompt哈希不变，240个appearance像素、原prompt/schema/响应一致性通过；逐调用token/费用与各阶段和总表相符，无失败模型调用或推理重跑。GPU阶段均经原guard检查，使用已有196093 allocation、auh7-1b-gpu-197物理GPU6（UUID GPU-9bd66cc06860c5b4），无新allocation或GPU重叠。
首次主运行启动器和首次CPU审计启动器分别因沙箱Slurm socket权限阻塞，均先停止后获准重启；这些失败没有启动推理。保留pipeline.log/audit.log与实际成功的*-permitted.log。
执行技能：[gs-consistency-flow1](../../skills/gs-consistency-flow1/SKILL.md)、[wedetect-shot-entities](../../skills/wedetect-shot-entities/SKILL.md)；范围按用户完整运行请求及当前temporal/appearance修订。

输出：run/summary.json、run/stages.csv、run/calls.csv、run/global_entities/、run/appearance/report/results.json、run/appearance/report/entities.csv、audit.json、source_snapshot/。所有本任务进程已结束，旧运行不变。
