# 多镜头生成模型选型（2026-09-21）

此次核查论文主实验、官方代码/权重/API及本地历史记录；未下载或运行新模型。难度判断不是AMD吞吐实测。

## 推荐组合

正式优先：Wan2.2-T2V-A14B（逐shot独立）、StoryMem（历史记忆）、HoloCine-14B-full（联合多shot；先过长输入/完整时长/ROCm检查）。第四个选Wan2.1-T2V-1.3B作为低成本控制，或CineTrans-DiT作为另一联合方法。先用已在本地运行过的Wan2.1-1.3B核查接口；不要预承诺尚未跑通的14B模型能够直接覆盖全300条。

## 已核实的相近benchmark

| 工作 | 相关评测对象 |
|---|---|
| [EntityBench](https://arxiv.org/html/2605.15199v1#S5.SS1) | HoloCine、CineTrans、StoryMem、EntityMem |
| [ST-Bench](https://arxiv.org/html/2512.19539v1#S4) | Wan2.2-T2V-A14B、StoryDiffusion+Wan2.2-I2V、IC-LoRA+Wan2.2-I2V、HoloCine、StoryMem |
| [MuSS](https://arxiv.org/html/2604.23789v1#S5) | StoryDiffusion+I2V、EchoShot、CineTrans、HoloCine；S2V另有Phantom、VACE1.3B/14B |
| [MSVBench](https://arxiv.org/html/2602.23969v1#S4) | Wan2.2系列、CogVideoX1.5-5B-I2V、HunyuanVideo-I2V、LTXV-13B-0.9.8、storyboard/agent方法、LongLive；表中商业模型Sora2、Veo3.1 |

不同benchmark成绩不能直接排序，I2V/S2V的视觉输入须注明。

## 可运行性与适配风险

- [Wan2.2](https://github.com/Wan-Video/Wan2.2)：代码和权重公开。A14B可作无跨shot记忆基础对照。官方720p单GPU例至少80GB，支持offload/T5 CPU/多GPU；这不是480p或本AMD平台显存保证。TI2V-5B另有24GB offload文本模式，可作轻量备选，不能冒充A14B。
- [StoryMem](https://github.com/Kevin-thu/StoryMem)：官方Wan2.2 T2V/I2V+M2V LoRA，提供逐shot pipeline、T2V首镜头和记忆推理，适合4/6/8shot。flash_attn与ROCm兼容性需验证。保留历史记忆，正确区分hard cut和延续；不要对每次换场景盲目清空记忆。
- [HoloCine](https://github.com/yihao-meng/HoloCine)：global_caption/shot_captions/shot_cut_frames接口匹配。官方README提示512token截断、默认241frames/15秒，本数据dense输入和20/30/40秒需专项检查。FA3/Hopper及CUDA wheel安装不能直接照搬AMD。若保不住全部prompt要求，不应静默压缩后按原要求评分；full/sparse明确版本。
- [CineTrans-DiT](https://github.com/Vchitect/CineTrans)：官方Wan2.1-1.3B+LoRA，模型较小，适合轻量联合试跑。官方A100约5分钟/示例不是本AMD20–40秒运行报价；短多shot演示不证明本数据全时长可用。另有Unet，必须区分版本。
- [Wan2.1](https://github.com/Wan-Video/Wan2.1)：本地已有10shot生成记录，832×480/81frames/16fps/20steps；[报告](../experiments/entitybench-wan21-complete-20260825/results.md)。这是非标准低步数smoke；正式质量基线须另定采样设置。
- [StoryDiffusion+Wan2.2-I2V](https://github.com/HVision-NKU/StoryDiffusion)：多篇benchmark采用，可作分镜图路线备选。要实现文本→一致分镜图→视频整套系统，额外规划/图像生成成本需算入。不能拿源视频真实帧作为纯文本实验隐藏条件。
- EntityMem：当前[官方仓库](https://github.com/Catherine-R-He/EntityBench)主要发布data/eval/examples，未核实完整生成系统入口，不当作立即可跑。

## 商业模型

[Veo3.1/Fast官方API](https://ai.google.dev/gemini-api/docs/veo?hl=en)避免本地GPU部署，但配额/网络/计费尚未在本任务验证。时长4/6/8秒，参考图模式8秒，与本数据5秒不直接相同；应明确单独兼容时长协议，不随意裁掉动作终态。Fast不能标成论文同版本Veo3.1。

不建议此时新建Sora2全量依赖：[官方公告](https://developers.openai.com/api/reference/typescript/resources/videos/methods/create)写明Sora API于2026-09-24永久关闭。历史benchmark采用不等于当前可持续复现。

## 建议执行顺序

每模型先6条（4/6/8shot各2），检查输入token/实际时长和shot数/显存/ROCm/切点/失败；再固定30条开发集（18/9/3）测真实时间与费用。开发和最终300按源作品隔离，固定共同测试ID，不能按生成结果挑样本。

最终300条每模型1500shots、125分钟目标成片；3模型4500shots、375分钟成片，不是运行墙钟估计。若先用完整400则每模型2000shots、166分40秒。冻结模型commit、采样精度/步数/seed/FPS/尺寸、实际输入文本及hash、格式适配与失败策略。只做协议所需转换；任何摘要须核验保留评分要求，不把丢失文本算成模型不遵循。

纯文本、文本自产参考图、外部参考图分清输入条件。源视频不用作纯文本生成输入。额外/缺失shot及生成失败保留记录，不静默丢弃。最终耗时和预算以新小样本实测为准，不能套用旧3shot流水线数字。
