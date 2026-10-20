# 源视频与 prompt 提取试验（2026-09-20）

本目录是数据构造试验，不是生成模型的正式评测结果。源视频已下载 SF20K 20 段、MuSS 20 段；40 段全部通过来源/文件哈希/容器/时长审计及完整解码。原视频未裁短或改写。

完整结果、实际 API 费用与限制见 [REPORT.md](REPORT.md)。

## 数据入口

- `videos/sf20k/<video_id>/original.mp4`：SF20K 官方 train URL 清单中的原始短片。
- `videos/muss/<video_id>/original.mp4`：MuSS 官方年度来源 ID 清单中的电影片段。
- [DOWNLOADS.md](DOWNLOADS.md)：实际数量、体积、时长、频道分布、失败原因和依赖版本。
- [acquisition_manifest.json](acquisition_manifest.json)：全部成功与失败尝试、原始来源及文件校验值。
- [acquisition_audit.json](acquisition_audit.json)：40 条独立下载完整性审计。
- `metadata/`：保留官方原始元数据、获取地址与 SHA-256。

## 窗口与提取结果

- `media-pilot/`、`media-rest-sf20k/`、`media-rest-muss/`：40 段源视频的完整解码、原始 PTS/帧号、切镜提案、候选窗口与关键帧联系表，共 111 个自动候选。自动候选不等于合格脚本。
- `candidate_windows.jsonl`：111 个基础候选的统一索引。`supplemental_candidate_windows.jsonl` 单独记录重分镜/补帧变体，不将它们算成新增独立源视频。
- `media-adaptive-MTY/`：单个已知漏切样本的独立修复验证，保留原试验结果；不是全体视频的重切镜版本。
- `prompt-trial-01/`：第一轮 6 个机械筛选窗口，保留实际提取、独立复核及失败记录。
- `prompt-trial-02/`：第二轮 6 个经源画面筛查的窗口，两来源各 4/6/8 镜头。
- `prompt-trial-03-dense/`：同一个 WIt 窗口补至约 2 fps 的独立提取/复核；不是新增独立样本。
- `corrections/os1_occurrence_v2/`：有原帧依据的玻璃杯出现记录修订副本，保持待审核状态。
- `pilot_summary.json`：运行 `summarize_pilot.py` 后的汇总；以其 `tested_construction_variants` 和 `windows[].trial` 判断已包含哪些完成试验。
- `prompts_all_validated_schema.jsonl`：通过结构检查的全部脚本，包括待修改/拒绝条目；不能不筛选就提交生成。
- `prompts_sparse_audit_pass.jsonl`：同时通过现有构造与独立稀疏帧审核门槛的条目；正式集仍需人工完整窗口审核和冻结。

每个窗口目录保留 `canonical_source_input.json`、原图哈希、`extraction.json`、`audit.json`（通过结构门槛时）、`review.md` 及原始模型调用记录。被结构门槛拒绝的原始回复留在 `calls/`，其费用仍计入试验总额。

## 已验证的边界与限制

1. 初始 FFmpeg `.30` 阈值明显漏切；降低至 `.10` 可恢复一部分切点，但仍有漏切/误切。全体 111 个窗口仅是提案。
2. PySceneDetect Adaptive 在已知 MTY 漏切处有效，在另外两段又出现误切和漏切，未推广为默认真值。详见 [切镜对比](preprocess/SCENEDETECT_COMPARISON.md)。
3. Movieclips 片尾推广、字幕/片头、动画风格与渐变转场需要显式筛查；不能仅按时长最接近目标选择窗口。
4. 构造用 3 帧/shot 无法穷尽验证持续运镜、短暂动作和所有切点。存在歧义时需回看源片或补充原始帧，不能通过简化文字消除证据问题。
5. 此处实体表是构造脚本的来源事实表，不能替代生成视频的 WeDetect 实体发现或充当生成异常真值。生产评测代码和评分规则未修改。

## 复现

在已有低负载的计算节点运行；不要在登录节点下载/解码/批处理。本次使用既有 Slurm job `196092`，不申请 GPU。各次实际命令及日志保存在 `preflight/`。

- 来源下载：[acquisition/README.md](acquisition/README.md)
- 分镜与抽帧：[preprocess/README.md](preprocess/README.md)
- Prompt 提取：[extraction/README.md](extraction/README.md)
- 三轮完成后汇总：`python summarize_pilot.py --trials prompt-trial-01 prompt-trial-02 prompt-trial-03-dense`

费用以 `pricing.json` 的已核验标准 API 单价结合实际 usage 换算，区分普通输入、缓存读写和输出；不是账单，不含本对话、视频生成或正式评测费用。
