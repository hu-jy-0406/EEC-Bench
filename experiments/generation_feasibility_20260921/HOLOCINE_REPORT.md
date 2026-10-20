# HoloCine 14B full：AMD/ROCm 实际推理验证

结论：在现有 Slurm 分配的单张 AMD MI210 64 GiB 上，官方 HoloCine 双 14B full-attention 专家可以运行。832×480 的 20/30/40 秒完整帧长均完成两步资源测试并输出可完整解码视频；另有 4-shot、81 帧、50 步的标准采样短视频完成并经目视检查。长视频 50 步时间是工程外推，不是实测完成时间。

## 实测

| 测试 | 帧数/步数 | 加载秒 | 生成秒 | 编码秒 | 峰值 allocated/reserved GiB | 解码 |
|---|---:|---:|---:|---:|---:|---|
| 4 shot / 20 s | 321/2 | 46.19 | 913.32 | 16.82 | 42.49/48.46 | 321 帧，通过 |
| 6 shot / 30 s | 481/2 | 81.51 | 1719.14 | 15.55 | 46.90/57.87 | 481 帧，通过 |
| 8 shot / 40 s | 641/2 | 61.92 | 2843.08 | 13.13 | 45.69/57.72 | 641 帧，通过 |
| 4 shot / 约 5 s 标准采样 | 81/50 | 82.95 | 1799.32 | 13.11 | 30.80/34.29 | 81 帧，通过 |

16 fps 是 benchmark 适配，官方示例保存为 15 fps。321/481/641 帧包含首帧，容器报告时长约 20.06/30.06/40.06 秒。所有输出均完成整段 ffmpeg 解码和精确帧数检查，RGB 有限、非恒定。两步长片仍明显未充分去噪，不能作为视觉质量通过证据。

50 步短样本的联系图可辨别：灰衣白帽女性 → 雪地庭院两人远景 → 女性近景 → 戴帽男性，符合四段实体出场次序的直观呈现。它将原 20 秒叙事压到约 5 秒，不验证原时长下的质量、身份一致性或评分。

## 400 条时间外推

主口径为生成加编码，不含模型加载、下载、排队、导入和验证。每长度只测试一个 prompt。公式：`实测两步 generation + 实测 encoding + 48 × 两步同步 denoise 时间均值`。CFG 正负两次 forward 已含在实测步时中，不再乘二。

| 长度 | 实测两步秒 | 外推50步/条小时 | 数量 | 外推GPU小时 |
|---|---|---:|---:|---:|
| 4 shot / 20 s | 323.26, 326.15 | 4.5878 | 240 | 1101.08 |
| 6 shot / 30 s | 691.91, 729.80 | 9.9599 | 120 | 1195.19 |
| 8 shot / 40 s | 1221.29, 1273.50 | 17.4253 | 40 | 697.01 |

合计 **2993.28 GPU 小时**，约 **124.72 单卡天**。理想持续使用 4/8 张同等 GPU 分别约 **31.18/15.59 天**；这不是已测多卡吞吐，也不表示当前可用专属卡数。

这不是精确上/下界：两步测试分别使用高/低噪声专家各一次，而 50 步日程为 21/29 次；第二步含专家切换，平均后重复外推会放大一次性开销。长序列原生卸载行为、缓存、其他输入和持续负载还会改变时间。显存峰值也只证明已测设置，不保证所有 50 步长视频上界。

## 兼容与资源记录

- PyTorch 2.7.1+ROCm 6.3，FlashAttention 2.7.4；实际 FlashAttention-2 可用。保留 full attention、双专家、官方 BF16/CFG5/sigma-shift5，未改 sparse、未量化、未用近似缓存。
- tokenizer 实查 4/6/8-shot 正向 prompt 为 281/397/429 tokens，全部低于 512，无截断；原始与适配 prompt、实体出场表见 `prompts/test_cases.json`。negative prompt 使用 runner 中固定简短中文列表，非官方示例整段。
- 修复官方 StepVideo 旁路导入：`PretrainedConfig` 从公开 `transformers` 导入。ModelManager 在 safetensors 逐张量读取时直接转选定 BF16，降低 FP32→BF16 CPU 峰值，最终推理 dtype 不变。差异见 `holocine_compat.patch`。
- 使用官方原生 CPU offload，retention 参数52 GiB；省去会重新把所有模型搬上 GPU 的示例 `pipe.to(cuda)`。实际专家分阶段驻留；长序列减少 retained weights，因此峰值 allocated 不必随长度单调增加。
- 初次 job196092 的 host RAM cgroup 实为64 GiB，加载中 SIGKILL；保留日志，并迁到已有 job206117/node306 的2 TiB额度。没有申请新资源。最终 GPU3/GPU5 均通过每次 fresh UUID/VRAM/util/KFD guard，仅用检查为空闲的卡。
- 旧 coordinator 对 GPU3 的冗余40秒启动因已占7.75GB VRAM被 guard 拒绝；真实40秒执行在 GPU5 的独立日志中，不曾重复生成。
- 40秒后处理曾出现日志空窗，最终原进程正常完成，无重跑、无 SDMA 修改、无已确认后处理故障。非阻塞 py-spy 检查被系统权限拒绝，未提权。可选 `holocine_latent_checkpoint.py` 仅为未来诊断准备，从未在这些推理中启用。

## 文件

- `run_holocine.py`：可复现独立 runner；`holocine_coordinator.py`：长度探针协调；`summarize_holocine.py` 与 `holocine_summary.json`：聚合与公式。
- `outputs/holocine/{4shot_20s_2step,6shot_30s_2step,8shot_40s_2step,4shot_5s_50step}/`：各自 `video.mp4`、`contactsheet.jpg`、`metrics.json`、`step_times.jsonl`。
- 40秒真实日志为 `logs/holocine_8shot_40s_2step_gpu5.log`；不带 `_gpu5` 的同名日志仅是旧协调器的 guard 拒绝。

所有这些生成均为本地模型推理：**0 次模型 API 调用，USD 0 API 成本**。未执行400条正式生成；集群资源成本未计价。
