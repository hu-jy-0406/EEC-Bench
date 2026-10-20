# 多shot同场景身份设计：数据审计与Wan测例

状态：设计及数据审计完成；生产pipeline未修改，未运行新检测/配准/身份模型。范围为当前实际使用的400episode/2000shot有效Wan输入，与当前StoryMem导出索引及全部400份contract哈希核对。源数据哈希见summary.json。

统计单元为 `(episode_id, source_scene_id)`，同一scene在时间轴上分开出现仍计为一个scene；不同episode的Scene1不合并。场景归属来自数据集标注，不是逐一人工核验400条生成画面的物理空间一致性；生成模型发生场景漂移不在本次被重标注。仅episode总shot数≥3不能替代本统计。

全量400episodes中318（79.5%）至少有一个scene≥3shots；749个episode-local scenes中336个满足。当前Wan完成202条完整episode中195（96.53%）满足，对应202个scene≥3shots。

202个完整episode共1008shots；先前暂停报告1038done shots另包含30个尚未成完整episode的片段，不是统计矛盾。完成判断结合当前queue全部shot done、episode.mp4/episode.json存在，并交叉核对暂停时完整清单；非候选视频本轮不重复全量解码/哈希。

## Episode分布：按其中最大的scene shot数分桶，互斥且不重复计数

| 最大scene shot数 | 全量episode | Wan完整episode |
|---|---:|---:|
| 2 | 82 | 7 |
| 3 | 73 | 16 |
| 4 | 153 | 108 |
| 5 | 21 | 12 |
| 6 | 51 | 44 |
| 7 | 4 | 3 |
| 8 | 16 | 12 |

## Scene分布：每个scene单独计数

| Scene shot数 | 全量scene | Wan完整episode内scene |
|---|---:|---:|
| 1 | 281 | 30 |
| 2 | 132 | 18 |
| 3 | 88 | 23 |
| 4 | 156 | 108 |
| 5 | 21 | 12 |
| 6 | 51 | 44 |
| 7 | 4 | 3 |
| 8 | 16 | 12 |

符合条件的318episodes自身总shot数分布：4shot=172，6shot=108，8shot=38。注意这与“同一个scene有几个shot”是两个不同口径。

全量相邻scene-pair数量1251；同scene全组合2839（2.27倍）。Wan完整子集758→1914（2.53倍）。因此不建议把全部非相邻组合直接展开为完整RoMa/复核/评分流程。场景级统一身份、按需配准与固定边界列表详见 ../../docs/scene-global-identity-v2-design.md。

schedule有对象“前后列出、中间未列出”的episode为262，其中已完成Wan为176。这只是选例线索，不是中间视频/检测里实际缺失的统计；不计入上述scene定义。

## 推荐真实Wan测例

- `_6fzoABYwyk_s00021_n4_clean_v2`，generation priority39。
- 4shots全部Scene1，正常prompt明确同一dim teal bedroom；实际Wan四片段共324frames/16fps=20.25秒，prompt目标20秒。
- Shot1/3：奶油色门口的黑衣女性、门及小幅画；Shot2/4：床上的两人、格纹毯、橙色台灯、问号图案。
- 已查看Wan产物每shot首/中/尾三张原有contact图。床边物体在Shot2与Shot4清晰可见，Shot3预览为门口视角；适合验证跨过无共同可见物的中间shot。画面有床型、人物与物体位置/外观差异，不能据此事先规定最终评分或强制身份真值。
- 第一轮可优先检查Shot2→Shot4的橙色台灯/床/问号图案，辅以Shot1→Shot3门口女性；格纹毯还受非刚体形态及集合粒度影响，作为次级对象。
- 尚未跑WeDetect，不声称Shot3已测得“无检测”，不声称新匹配或坐标配准已成功。

`test_case/selection.json`记录视频路径、SHA256、每shot解码元数据和选择边界；manifest.json含每shot6张832×480JPEG，帧0/16/32/48/64/80，共24帧；narrative.json使用确切Wan输入文本及shot作用域；原contract/alignment_contract/entity_schedule/story_script与wan_input均已保存，未改写评分参照。参考contract保留原schema，不能把它误当成当前集成runner自动接受的prompt_alignment_b_v1输入；正式实验需显式适配并核对。

## 文件和执行

summary.json / episodes.csv / scenes.csv / schedule_gaps.csv保存所有计数和逐项溯源，audit.py可复现。test_case用于后续实验；设计文件说明未实现的global初始匹配、按需配准、global复核、约束与回退。

复用已有206117/node306检查低负载CPU，GPU全部隐藏，无新资源申请。首次素材准备因compute节点缺少PATH中的ffprobe失败，部分文本保存在prepare_attempt_missing_ffprobe；改用Wan既有vace/imageio-ffmpeg完整解码，不影响原视频。此处未生成新视频，未改队列，未改生产pipeline。0次新增推理API调用/0计费API tokens/USD0推理API费用；本轮只做本地审计/解码和当前助手的图像观察。
