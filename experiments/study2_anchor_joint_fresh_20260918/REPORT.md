# Study2 新流程独立测试：参照先行、身份与存在性一次联合判断

版本：`anchor_then_joint_presence_v1`；全部 Codex 调用 `gpt-6-astra / medium`。旧流程 `post_alignment_identity_review_v1` 原样保留，哈希审计通过。

## 新旧结果

| 指标 | 原流程完整重跑 | 新流程完整重跑 |
|---|---:|---:|
| 实体一致性分 | 86.66666666666667 | 94.11764705882352 |
| 空间关系一致性分 | 96.42857142857143 | 96.42857142857143 |
| 共同静态实体数 | 8 | 8 |
| 无序实体对 | 28 | 28 |
| 负cosine | 6 | 6 |
| Codex调用 | 11 | 9 |
| 输入tokens | 1068173 | 530033 |
| 输出tokens | 59747 | 36447 |
| 总tokens | 1127920 | 566480 |
| 流水线墙钟秒 | 1807.0196268558502 | 1121.6247856616974 |

总tokens变化：减少 49.78%；原来的初始完整对应＋对齐后身份复核＋两次存在性判断共 705,165 tokens，新参照选择＋联合判断共 146,864 tokens。
两组都从相同原始JPEG重新推理，无历史推理输出复用；只沿用代码/环境/预训练权重/原始Prompt输入。此次不是固定前端的严格消融，也不是多轮稳定性评估；时间差包含加载缓存、服务速度和系统波动，不能解释成固定加速比。

## 实际阶段消耗

| 环节 | 墙钟秒 | Codex次数 | Input tokens | Output tokens | Total tokens |
|---|---:|---:|---:|---:|---:|
| WeDetect-Anything | 31.30 | 0 | 0 | 0 | 0 |
| 独立单shot聚类 | 178.53 | 2 | 42,220 | 11,069 | 53,289 |
| GeoCalib重力估计 | 42.18 | 0 | 0 | 0 | 0 |
| Pi3X Shot1 | 51.83 | 0 | 0 | 0 | 0 |
| Boxer Shot1 | 15.14 | 0 | 0 | 0 | 0 |
| Pi3X Shot3 | 25.13 | 0 | 0 | 0 | 0 |
| Boxer Shot3 | 13.56 | 0 | 0 | 0 | 0 |
| 独立动静判断＋静态图融合 | 159.19 | 2 | 72,383 | 9,400 | 81,783 |
| 仅配准参照实体对应 | 30.61 | 1 | 41,654 | 703 | 42,357 |
| RoMaV2 36帧对匹配 | 135.64 | 0 | 0 | 0 | 0 |
| 筛点与坐标提升 | 1.54 | 0 | 0 | 0 | 0 |
| 重力约束Sim3配准 | 1.72 | 0 | 0 | 0 | 0 |
| 一次完整身份＋存在性联合判断 | 314.07 | 1 | 94,457 | 10,050 | 104,507 |
| cosine＋局部取证＋最终Prompt复核 | 118.47 | 3 | 279,319 | 5,225 | 284,544 |

总墙钟 1121.625s；阶段切换间隔 2.375s 已含在总墙钟内。并行调用按阶段墙钟计一次；GPU阶段含加载/安全检查。cached input=0，其已包含在input中，reasoning子项不重复相加。逐调用时间与usage见calls.csv和usage.json。实验准备/测试/报告整理未单列为模型推理耗时。

## 实际流程

1. 两shot各6张原始JPEG→全新WeDetect→两次隔离聚类→全新GeoCalib/Pi3X/Boxer→两次隔离动静判断及静态融合。
2. 一次Codex只选择配准参照及局部支撑参照对；未选实体尚未对应，没有“默认单侧”标签。
3. 全新RoMa 36组帧对→结构筛点/深度提升→重力约束Sim3。
4. 一次Codex读取原帧、自己的/对齐后框、对側投影、融合误差、动静清单和正常剧情，输出全部实体身份分组及存在性原因；程序执行原证据和Prompt门。
5. 合理共同静态集合的全部无序对算cosine；负值经独立单shot局部取证及最终跨shot原帧/Prompt复核。
6. 保持两个分数公式和未知/豁免口径，审计实体守恒、原帧哈希、冻结变换、cosine和usage。

## 参照及配准

- a01: Large wooden desk ↔ Large wooden dining table；两镜头均见深褐色长方木桌，斑驳木纹、厚桌沿、宽围板与方腿构造一致；与窗下暖气片及窗侧木椅的空间关系相符。
- a02: Radiator below window ↔ White radiator below window；均为白色密集竖肋暖气片，固定于白框窗台下；窗帘、窗台及桌椅共同限定其房间位置，支持同一结构身份。

最终yaw=130.100700°，scale=0.978178147，translation=[-0.3991601349861209, 0.18042135399284, 0.20409698782588845]；留出点中位重投影误差74.800px。
最终参照核验：[{"anchor_id": "a01", "verdict": "retained", "final_group_id": "g04", "reason": "两端仍确认同一长木桌；像素中的厚沿、斑驳桌面、宽围板和方腿及人物使用连续性支持身份。保留身份锚点不表示现有拟合准确。", "witnesses": [{"shot_id": "shot1", "frame_id": 120, "region_xyxy": [63, 209, 827, 480], "observation": "无人遮挡的桌面、围板和腿。"}, {"shot_id": "shot3", "frame_id": 0, "region_xyxy": [108, 214, 778, 480], "observation": "反向视角下同一构造木桌。"}]}, {"anchor_id": "a02", "verdict": "retained", "final_group_id": "g12", "reason": "同一窗台和盆藤下的白色竖肋暖气片，固定安装关系及双向投影均支持；遮挡裁切限制完整中心和尺寸精度。", "witnesses": [{"shot_id": "shot1", "frame_id": 120, "region_xyxy": [30, 239, 218, 412], "observation": "窗下暖气片部分被桌椅遮挡。"}, {"shot_id": "shot3", "frame_id": 0, "region_xyxy": [713, 241, 852, 424], "observation": "对应窗下暖气片，右侧出画。"}]}]
参照回退记录：{"passed": true, "inventory_conserved": true, "registration_frozen": true, "refit_requirement": {"rejected_or_uncertain": [], "point_counts": {}, "refit_required": false}, "round": 1, "model_calls_this_round": 1}。

## 全部身份及存在性判定

| 组 | Shot1实体 | Shot3实体 | 身份 | 存在状态 | 原因类别 |
|---|---|---|---|---|---|
| g01 | Framed landscape painting on wall | Framed landscape painting | ambiguous | unknown | none |
| g02 | Dark green mug | Dark green mug | matched | compatible | none |
| g03 | Black desk lamp |  | unmatched | conflict | inconsistency |
| g04 | Large wooden desk | Large wooden dining table | matched | compatible | none |
| g05 | Small framed picture on bookcase |  | unmatched | exempt | viewpoint |
| g06 | Light-colored pencil cup | White pencil cup | matched | compatible | none |
| g07 | Trailing plant by window | Trailing plant on windowsill | matched | compatible | none |
| g08 | Dark green bookcase with lower cabinet |  | unmatched | exempt | viewpoint |
| g09 | Trailing plant on bookcase shelf | Plant at far left edge | ambiguous | unknown | none |
| g10 | Patterned rug beneath desk | Large patterned rug beneath dining table | matched | compatible | none |
| g11 | Wooden slat-back chair | Wooden dining chair | matched | compatible | none |
| g12 | Radiator below window | White radiator below window | matched | compatible | none |
| g13 | Terracotta pot on windowsill | Plant pot on windowsill | matched | compatible | none |
| g14 | Small pale vessel on bookcase shelf |  | unmatched | exempt | viewpoint |
| g15 | Black writing instrument in pencil cup | Writing utensils in pencil cup | scope_mismatch | unknown | none |
| g16 | Small wooden side table against wall | Small wooden console table | ambiguous | unknown | none |
| g17 | Trailing plant on small side table | Trailing plant on console table | ambiguous | unknown | none |
| g18 |  | Larger framed picture in hallway | unmatched | exempt | viewpoint |
| g19 |  | Framed botanical print beside window | unmatched | exempt | viewpoint |
| g20 |  | Small narrow framed hallway picture | unmatched | exempt | viewpoint |
| g21 |  | Small dark hallway cabinet | unmatched | exempt | viewpoint |
| g22 |  | Tissue packet with protruding tissue | unmatched | unknown | inconsistency |
| g23 |  | Stack of books on console | unmatched | unknown | inconsistency |
| g24 |  | Hallway runner rug | unmatched | exempt | viewpoint |
| g25 |  | Plant pot on console table | unmatched | unknown | inconsistency |

## 未确认项与效果边界

本次存在性分数升高不表示检出更好；需同时对照确认冲突数量和unknown。下面保留模型实际未确认的项目及理由。
- 身份未定：g01 Framed landscape painting on wall / Framed landscape painting。两者均为金褐框河岸风景画，但树群、河道及画框细节不足以确认同一实例；对齐中心相隔约5.39，互投落在画外或相机后方。已考虑室内移位，不能仅凭大位移拆分，也不能仅凭题材合并。
- 身份未定：g09 Trailing plant on bookcase shelf / Plant at far left edge。Shot3左缘植物位于深绿柜旁，可能对应Shot1柜上垂藤；但仅27像素宽，盆与完整枝形不可辨。中心差约4.02、尺寸和高度亦不符；既可能裁切与几何误差，也可能为另一株，不能强配。
- 身份未定：g15 Black writing instrument in pencil cup / Writing utensils in pencil cup。Shot1端点只含右侧一支黑笔，Shot3端点包含整束多支笔。即使该黑笔属于同一笔束，也不是相同实体范围；不拆分或合并冻结库存。
- 身份未定：g16 Small wooden side table against wall / Small wooden console table。均为承托垂藤的靠墙木桌，但Shot1可见桌体较窄，Shot3有明显宽抽屉围板；长度估计约0.39与0.86。中心差约4.17且互投出画；考虑移位后，仍缺少足够构造细节确认实例。
- 身份未定：g17 Trailing plant on small side table / Trailing plant on console table。两株均在小木桌上垂落，但叶团密度、枝条轮廓和支撑桌身份未能确认；中心差约4.15，尺寸亦不同。不能以大位移直接分离，也不能以同类植物直接合并。
- 有不一致嫌疑但未确认：g22 Tissue packet with protruding tissue。有明显新增嫌疑，但小物体要求可靠的局部对应空区。冻结投影约(659,227)接近Shot1远桌沿，桌体配准误差超过百像素；不能排除预期位置落入书本、杯筒或桌沿遮挡。故不确认冲突。
- 有不一致嫌疑但未确认：g23 Stack of books on console。小桌对应未成立，不能把另一张桌或不可见台面当作空区；无新增冲突证据，也无可靠视角豁免。
- 有不一致嫌疑但未确认：g25 Plant pot on console table。可能为库存粒度或漏列，也可能是不同支撑桌上的盆；不新增Shot1端点，不确认新增或视角豁免。

参照集合、全新前端输出、配准结果和判定上下文均可能影响上述变化；一次端到端运行不能把原因唯一归结为少了一次复核。旧版结果与默认配置保留，新版仍是实验分支。

## 确认冲突

- 存在性：Black desk lamp，unexplained_missing。用同一桌的边界、窗侧椅与反向机位定位整个桌面支撑域，Shot1远端在反拍中转向近端。近桌沿虽下裁，原尺寸灯罩与灯杆仍应伸入可见上方；两帧均无，不能由遮挡或漏检解释。未采用错误的约(171,151)中心投影。
- 空间：Dark green mug ↔ Light-colored pencil cup / White pencil cup，cosine=-0.586162135。身份、共同桌面及桌—暖气片锚点对应均获原图支持。按统一的绿杯中心减笔筒中心，独立局部观察在shot1支持u负序、shot3支持u正序；沿v均为负，竖直序仍未知，不据此追加冲突。容器直立比例、口沿、可见底缘及桌面透视共同约束水平中心，合理的隐藏筒底或杯柄修正不足以逆转所支持的u序。全局配准确实不可靠：空间留出中位误差约74.8像素，5像素内比例为零，因此负余弦及125.9度夹角不能单独证明变化。但本项局部符号由同一物理锚点与向上方向确定，不依赖该全局变换；相机反向不能使不变的物理中心关系产生相反局部符号。故至少一个端点的摆放不一致，不代表两物都移动或精确交换位置。

存在性 C/K/U/E=8/1/8/8；空间 C/K/U/E=0/1/27/0。score=100×(1−K/(C+K+U))，空间K=0时100。

## 验证与证据

12项契约测试通过：参照阶段不强制完整匹配、参照重复/掩码ID冲突、单判断保留有效惩罚、大位移不自动拆身份、实体增删/重复拒绝、Prompt/多帧/漏检门不足降未知、应离开却仍出现仅影响存在性、未确认共同存在不进入空间比较、失效参照按实际点数触发重配准、无效参照不能进入局部坐标、像素范围校验、零空间冲突100。实际运行另通过原流程哈希、全新调用、模型medium、实体守恒、全部无序对、独立重算cosine、冻结输入和token对账审计。

- study2/result.json / comparison.json：结果与比较
- study2/stages.csv / calls.csv / usage.json：完整消耗
- study2/anchors_initial.json：参照选择，未包含完整实体对应
- study2/joint_identity_presence.json：单次联合输出
- study2/matching.json / presence.json / spatial.json / all_pairs.csv：最终计分依据
- study2/calls/：原始请求/响应/实际usage
- baseline_preservation.json / code_snapshot/ / contract_validation.json：保留旧版与新实现证据
