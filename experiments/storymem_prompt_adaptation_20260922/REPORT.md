# StoryMem prompt 数据：400 条完成

每条 episode 一份 `deliverables/episodes/<episode_id>/story_script.json`，可直接作为官方 `pipeline.py --story_script_path` 的输入。保留原 400 条优先队列、2,000 个 shot、每 shot 5 秒目标时长，以及 Core100 ⊂ Priority200 ⊂ Full400。

沿用已独立复核的 Wan 上下文补全：1,084 个 shot 的 1,644 项补充逐字保留。采用当前原始 prompt 修订版；3 条 episode 中更新 1 处 shot 正文和 2 处全局摘要。1,999 个最终 shot 文本与此前 Wan 输入逐字相同。最终生成脚本只含当前文本，没有旧矛盾版本或修改解释。

## 输入和映射

- 原生字段：`story_name`、`story_overview`、`scenes`；每个 scene 包含 `scene_num`、`video_prompts`、`cut`。
- `story_overview` 保存当前 global 摘要，官方生成模型只读取当前 `video_prompts` 项。已补全正文直接使用，不要再次追加 global、其他 shot、实体表或 claims。
- 当前数据集由独立镜头组成，全部 `cut` 为 JSON 布尔值 `true`，保留跨镜头视觉记忆，不强制从上一段末帧平滑延续。同一场景切换机位也保持 `true`。
- 按连续场景片段顺序编号，共 959 个原生 scene 条目。113 条 episode 有离开后返回同一场景的情况，保留原始镜头顺序。StoryMem 的序号表示生成顺序；评测的持久场景身份和 contract schedule key 保存在索引中，不从该序号重新推断。
- `deliverables/index.json` 和各队列 JSONL 记录脚本相对路径、原始 Shot ID、原始 scene ID、contract schedule key、原生镜头编号、预期视频文件名、文本及合同 hash。队列文件是调度索引；每个 `story_script.json` 才是模型原生输入。
- Core100 后只追加 `stage2_additional_100.jsonl`，再追加 `stage3_remaining_200.jsonl`；`priority_200.jsonl` 是累计集合。

## 校验

全量独立读回审计通过：400 个原生 JSON 使用官方同款 JSON5 parser 加载；T2V 首镜头与 M2V 后续迭代保持全部 2,000 个镜头顺序。当前原文、contract 文本、保留补充、1,821 条前文引用、场景及镜头映射、各子集和文件 hash 均通过检查。

使用实际 StoryMem tokenizer wrapper，以及已部署 T2V 和 I2V checkpoint 各自的 UMT5 tokenizer，在离线单 CPU 上分别验证。最终每 shot 含 special tokens 的长度为 62–364，平均 145.081；超过 512 的为 0。模拟实际 512 padding/truncation 后的全部有效 token IDs 与不截断编码完全一致。`token_audit.csv` 提供逐 shot 结果。

本次为确定性复用、版本同步和格式转换；语义补全依据已有完整独立模型复核，未重新进行模型语义审查，也不等同独立人工标注。现有评测 contract 和旧 Wan 生成历史保持其版本记录；StoryMem 使用本次交付的新输入。

本次新增模型调用 0、计费 API tokens 0、API USD 0（不含父对话及既有 Wan 补全费用）。CPU-only，复用已有 allocation206117/node306 的一个已检查空闲 CPU，未运行视频生成或申请新资源。

详细检查：`independent_validation.json`；来源与 tokenizer hash：`build_audit.json`。原始配置和代码依据为本地已测试 StoryMem checkout；原生示例见 https://github.com/Kevin-thu/StoryMem/blob/main/story/black.json 。
