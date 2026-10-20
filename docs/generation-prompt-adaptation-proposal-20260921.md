# 三模型正式生成的 Prompt 适配方案（待用户选定）

日期：2026-09-21。本文是调研后的建议，不是已经实施的 prompt 修改。Core100 ⊂ Priority200 ⊂ Full400 的 ID 划分、原始文本和生成队列保持冻结，用户已明确认可该划分。没有启动新一轮模型推理或 schedule 编译。

建议主实验采用：**同一份共同精简语义版本，按模型原生接口确定性封装；所有模型共用同一个评测语义合同。** 在用户提出的两种选择中，更接近“统一满足要求”，但无需把完全相同的字符串送入本来就不同的接口。

## 已核实的本地文本限制

| 模型／当前运行方式 | 512 token 的作用范围 | 适配方式建议 |
|---|---|---|
| HoloCine 14B full attention | 整个 episode 的 global caption + 全部 per-shot captions + 格式标记 + tokenizer special tokens | 共同内容按其原生格式拼接，一次编码 |
| Wan2.2-T2V-A14B，独立逐 shot | 每次调用 text encoder 的完整 shot 输入；若补充 global context，也占该次预算 | 共同场景／当前实体定义 + 当前 shot 描述，逐 shot 调用 |
| StoryMem Wan2.2-MI2V-A14B | 每次 shot 生成的完整文本输入；episode 总长度不共用一个512预算 | 与 Wan 使用相同逐 shot 语义展开，装入其 script，保留原生视觉记忆机制 |

以上是当前配置下生成主文本编码器的限制，不是声称所有可能的模型配置／辅助文本处理都只有同一限制。负向文本单独编码，也要独立检查。512 指模型 tokenizer 的 token，不是英文单词、字符或 assistant tokenizer 的数量。

本地证据（workspace-relative）：

- `EECBench/experiments/generation_feasibility_20260921/repos/Wan2.2/wan/configs/shared_config.py:11`：`text_len = 512`；`wan/modules/tokenizers.py:56–58`：启用 truncation/max_length；`wan/modules/t5.py:503–508`：special tokens 和配置预算。
- `.../repos/StoryMem/wan/configs/shared_config.py:11`：同样512；`pipeline.py:147,240,286–288`：逐 shot 获取并传入 prompt。
- `.../repos/HoloCine/diffsynth/prompters/wan_prompter.py:98,124,169`：512默认与整体编码；`diffsynth/pipelines/wan_video_holocine.py:560`：当前实际 encode_prompt 路径。另一个 separate 函数仍有最终512截断，不能当成绕过方案。
- HoloCine 官方 [README / Prompt Format](https://github.com/yihao-meng/HoloCine#prompt-format) 明确提醒超过512会截断；[Wan官方配置](https://github.com/Wan-Video/Wan2.2/blob/main/wan/configs/shared_config.py) 和 [StoryMem配置](https://github.com/Kevin-thu/StoryMem/blob/main/wan/configs/shared_config.py) 与本地相符。

不要通过静默截断、拆少 shots、改时长或私自扩大 encoder 配置，来掩盖输入不适配。

## 已有 benchmark 的直接依据与边界

1. **EntityBench，§5.1**：明确将统一结构化 story scripts 转换为各方法原生 prompt 格式，例如人物名／抽象实体ID，并把 entity schedule 解析为模型需要的输入表示。这是采用“统一任务语义＋原生格式适配”的直接证据。公开论文没有给出足以复现其超长文本512压缩规则的详细说明，不声称它实行本文的共同精简预算或证明所有转换完全无损。[论文](https://arxiv.org/html/2605.15199v1#S5.SS1)
2. **MSVBench，§3.1–3.2**：使用统一的 global priors → scenes → shots，包含人物／环境描述、shot状态和动作、取景信息；实验覆盖不同生成范式。这支持共享结构化任务描述，不足以断言它逐模型采用完全相同字符串或完全相同 token 预算。[论文](https://arxiv.org/html/2602.23969v1#S3.SS1)
3. **MSAVBench，§3.2、§4.1**：在数据构造阶段进行统一 prompt enhancement，得到 global-to-shot scripts，再经过专家筛选；实验区分原生多镜头、逐镜头生成后拼接等方式。构造阶段的统一改写，不等于允许测每个模型时自由添加场景实体。[论文](https://arxiv.org/html/2605.20183v1#S3.SS2)
4. **StoryEval（CVPR2025）**：官方 README 要求新模型使用发布的同一套423条 prompts 生成视频。这是固定文本套件的明确例子，但它主要评测短故事事件，不能直接解决本项目的多镜头全局／局部接口差异。[官方仓库](https://github.com/ypwang61/StoryEval#unified-name-of-generated-videos)

上述研究没有形成所有 benchmark 都相同的“最短上下文模型决定一切”的统一规则。本文选择共享精简内容，是结合本项目对 bound/unbound 身份划分与四维 prompt alignment 的额外要求作出的建议。

## 为什么仅 schedule 相同不够

例如，同一shot都安排“女子、桌子、杯子”，但只有某个模型的版本要求“红杯放在桌子左边”，则实体出场 schedule 相同，appearance/spatial 的任务仍不同。若另一个版本额外写了“窗边有植物”，该植物又会从原本的 unbound 候选变成 prompt-bound。

需要同时保持：完整的 prompt-mentioned 实体范围、身份和数量、逐shot范围、已规定外观、动作及状态变化、空间关系及参照系、镜头要求、显式否定和可见性／时间量词。原始 `prompt_entity_ids` 不完整覆盖文字中的背景物体，不能仅用其集合相等证明语义等价。保留未说明对象的开放性；未提及不自动等于禁止出现。

## 推荐处理步骤

1. **原始数据归档不动。** 保留 episode_id、原始 global/per-shot、hash、来源和100/200/400成员；适配结果写sidecar，不覆盖原数据。
2. **每个episode只编写一份共同精简稿。** 优先去掉重复五秒套话、重复全段摘要和冗余形容表达；把可共享的身份／外观定义集中保存。保留所有实际要求和实体指代，镜头描述保持既有多样性。原始源观察中没有进入 prompt 的内容不能被重新注入生成文本。
3. **从同一份内容做格式适配。** Holo用 `[global caption]…[per shot caption]…[shot cut]…`；Wan/Story只展开当前shot适用的场景、实体定义和当前动作，保留同一shot文字。跨场景事实不能泛化成全episode恒定事实；实体定义不等于每shot都必须出场。Wan的独立生成和Story的视觉记忆作为各自方法特征记录，不额外提供源视频参考图。
4. **以最终输入实测token。** 先以Holo最终完整输入不超过480 tokens为软目标，含分隔符和special tokens；硬检查任何生成文本不超过512。Wan和Story对每个最终完整shot文本分别检查。预算可按shot复杂度分配，不平均砍句、不强制给每shot加镜头句。检查Holo每shot span仍完整、尾镜头未丢失。
5. **冻结共同稿，再双路并行。** 逐条完成原文→共同稿→三种实际输入的内容核对并冻结hash，即可开始视频生成，同时从同一冻结共同稿构建完整registry/schedule和四维claims。正式合同在评分前冻结；编译过程不能依据已生成视频补写要求。若文本/合同核对发现实际生成输入缺失要求，应修复输入并标记受影响生成失效，不能事后降低要求迁就结果。
6. **分批推进。** 从Core100队列的首20条开始（12×4shots、6×6shots、2×8shots），检查后立即放行生成，再处理下一批；无需等400条schedule全部完成。相同episode在三个模型中共享同一语义版本，逐条保存实际prompt、token计数、adapter版本和生成配置。

共同精简是否能完整容纳所有8shot样本尚未验证。若只靠去重和重写无法保留全部要求：记录为适配例外，不静默删减Holo要求。需要用户另行决定统一修订该episode的共同要求（所有模型和评测合同一起版本化）或采用单独标记的扩展实验；不擅自替换已冻结ID、改变shot数／时长或修改评测规则。

## 与 unbound 直接相关的额外输入控制

- 建议主实验关闭会新增内容的自动 prompt expansion；如需测试官方增强器，单列扩展设置并保存实际改写文本。
- 建议三个模型采用同一套经过检查的负向文本政策。现有Wan系示例包含“杂乱的背景”“背景人很多”等，可能抑制本项目关注的自然背景实体；不能让不同模型各自悄悄加“不要额外物体”等限制。建议共同使用不新增此类场景排除的质量负向词；具体文本尚待选定，当前推理配置未改。
- 不因某个模型表现不好而为它额外补写提示；各自原生最佳prompt的比较可作为补充实验，不能与共享语义主表混用。

当前仅调研和保存方案：额外流水线模型调用0、tokens0、API USD0（不含主对话／检索服务）。未改动正式数据、推理prompt、生成器或评测器。
