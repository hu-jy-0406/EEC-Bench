# Study2 全流程独立重跑（Shot1 / Shot3）

模型：所有 Codex 调用均为 `gpt-6-astra / medium`。流程：`gs-consistency-two-scores-v1 / post_alignment_identity_review_v1`。

实体一致性 **86.67**；空间关系一致性 **96.43**。
总墙钟耗时 **30.12 分钟**，实际 **11 次** Codex 调用，**1,127,920 tokens**（input 1,068,173 + output 59,747；cached input 0 已包含在 input 中）。

## 从头运行范围

原始 JPEG 直接作为输入，不重新抽帧或重新编码。WeDetect 候选、Codex 聚类、GeoCalib 重力、Pi3X 相机姿态/深度、Boxer 框、动静标签、初始匹配、RoMa 点、变换、对齐后身份复核、存在性和关系复核全部重新计算。只复用实现代码、环境、预训练权重与原始输入。原剧情 Prompt 按既有评测口径取正常剧情条款，剔除制作测试视频时写入的预期错误/答案指令；详见 narrative_provenance.json。

## 阶段消耗

| 阶段 | 墙钟秒 | Codex 次数 | Input tokens | Output tokens | Total tokens |
|---|---:|---:|---:|---:|---:|
| WeDetect-Anything | 55.27 | 0 | 0 | 0 | 0 |
| Codex independent shot clustering | 186.51 | 2 | 42,211 | 11,182 | 53,393 |
| GeoCalib | 61.90 | 0 | 0 | 0 | 0 |
| Pi3X Shot1 | 90.67 | 0 | 0 | 0 | 0 |
| Boxer Shot1 | 23.41 | 0 | 0 | 0 | 0 |
| Pi3X Shot3 | 90.32 | 0 | 0 | 0 | 0 |
| Boxer Shot3 | 16.41 | 0 | 0 | 0 | 0 |
| Independent motion + static graph fusion | 158.95 | 2 | 72,813 | 9,642 | 82,455 |
| Initial cross-shot identity matching | 113.45 | 1 | 133,049 | 3,408 | 136,457 |
| RoMaV2 36 frame-pair matching | 179.09 | 0 | 0 | 0 | 0 |
| Point filtering and lifting | 4.18 | 0 | 0 | 0 | 0 |
| Gravity-constrained Sim3 registration | 5.02 | 0 | 0 | 0 | 0 |
| Post-alignment identity review | 405.83 | 1 | 85,765 | 12,988 | 98,753 |
| Presence consistency (two independent reviews) | 297.51 | 2 | 452,686 | 17,269 | 469,955 |
| Cosines + local evidence + final Prompt review | 118.24 | 3 | 281,649 | 5,258 | 286,907 |

并行调用按阶段墙钟计时，未把两个并行调用的时间相加当作总耗时。表内GPU阶段含安全检查和模型加载；纯逐帧推理时间另见原始日志。总墙钟还包含输入组装/阶段切换；调用自身时间见 calls.csv。Token 来自 CLI 实际 usage 事件，未另行累加其子项。

## 检出与身份复核

```json
{
  "shot1": {
    "entities": 19,
    "static": 17,
    "moving": 2,
    "unknown": 0
  },
  "shot3": {
    "entities": 22,
    "static": 21,
    "moving": 1,
    "unknown": 0
  }
}
```
- g01（Framed landscape painting / Framed landscape painting）：split → g01_a: exempt/viewpoint；g01_b: exempt/viewpoint。
  原帧身份依据：shot1画靠书架、处于窗右侧墙段；shot3画在门旁宽桌上方、处于窗另一侧的背景墙。画面虽均为树木水岸，但树冠与岸线布局存在差异。
- g09（Trailing plant on bookshelf / Plant at far left edge）：uncertain → g09: unknown/none。
  原帧身份依据：shot1内部层板的垂藤与shot3边缘盆栽没有足够可比枝叶；家具支撑关系也未确认。
- g16（Small wooden side table against wall / Small wooden console table）：split → g16_a: exempt/viewpoint；g16_b: exempt/viewpoint。
  原帧身份依据：shot1末帧展示窗右角窄桌及窄抽屉面；shot3门旁桌的横向台面、抽屉面明显更宽，且位于窗另一侧墙段。
- g17（Small trailing plant on side table / Trailing plant on console table）：split → g17_a: exempt/viewpoint；g17_b: exempt/viewpoint。
  原帧身份依据：未随g16自动拆分：独立比较后，shot1小冠丛较疏、细藤分散，shot3大冠丛较密且左侧有长藤帘；两株在窗相反侧的不同桌上。

## 全部存在性分类

| 实体组 | 实体 | 分支 | 原因类别 | 最终状态 |
|---|---|---|---|---|
| g01_a | Framed landscape painting | noncommon_static | viewpoint | exempt |
| g01_b | Framed landscape painting | noncommon_static | viewpoint | exempt |
| g02 | Dark green mug | common_static | none | compatible |
| g03 | Black desk lamp | noncommon_static | inconsistency | conflict |
| g04 | Large wooden desk / Large wooden dining table | common_static | none | compatible |
| g05 | Small framed picture on bookshelf | noncommon_static | none | unknown |
| g06 | Light-colored pencil cup / White pencil cup | common_static | none | compatible |
| g07 | Trailing plant by window / Trailing plant on windowsill | common_static | none | compatible |
| g08 | Dark wooden bookcase with lower cabinet | noncommon_static | none | unknown |
| g09 | Trailing plant on bookshelf / Plant at far left edge | unresolved | none | unknown |
| g10 | Patterned area rug beneath desk / Large patterned rug under dining table | common_static | none | compatible |
| g11 | Wooden slat-back chair / Wooden dining chair | common_static | none | compatible |
| g12 | White radiator beneath window / White radiator under window | common_static | none | compatible |
| g13 | Terracotta plant pot by window / Windowsill plant pot | common_static | none | compatible |
| g14 | Small pale ceramic vessel on bookshelf | noncommon_static | none | unknown |
| g15 | Dark pen leaning right in pencil cup / Cluster of pencils in white cup | unresolved | none | unknown |
| g16_a | Small wooden side table against wall | noncommon_static | viewpoint | exempt |
| g16_b | Small wooden console table | noncommon_static | viewpoint | exempt |
| g17_a | Small trailing plant on side table | noncommon_static | viewpoint | exempt |
| g17_b | Trailing plant on console table | noncommon_static | viewpoint | exempt |
| g18 | Larger framed hallway picture | noncommon_static | viewpoint | exempt |
| g19 | Framed botanical print beside window | noncommon_static | viewpoint | exempt |
| g20 | Small narrow framed hallway picture | noncommon_static | viewpoint | exempt |
| g21 | Small dark hallway cabinet | noncommon_static | viewpoint | exempt |
| g22 | Tissue packet with protruding tissue | noncommon_static | inconsistency | conflict |
| g23 | Stack of books on console | noncommon_static | viewpoint | exempt |
| g24 | Patterned hallway runner rug | noncommon_static | viewpoint | exempt |
| g25 | Console plant pot | noncommon_static | viewpoint | exempt |

## 配准质量

正尺度 1.017101239；yaw 131.487212°；平移 [-0.34794980733402014, 0.17465918594154853, 0.23279732089835214]（模型场景单位）。留出点对称重投影中位误差 25.656 px，5px内点比例 10.16%。全局配准仍有明显误差，坐标差仅作复核证据；冲突判定还需原帧和局部参照支持。

## 确认扣分

### 存在性

- Black desk lamp：unexplained_missing。用同一主桌的长边、短端和反向观看关系，将shot1远端灯位对应到shot3近端桌区；不采用失准的中心投影。两侧各两帧支持灯存在与对应桌区空缺，整灯不可能被小道具遮住，也不是漏检。正常剧情不解释其消失。；依据同桌两端及反向视角作区域对应，不采用误差较大的投影点。原灯所在桌端在shot3近端可观察，且整张桌面复查也没有灯；两侧各两帧排除人物遮挡和检测遗漏。指定动作只涉及红本，故为未解释缺失。
- Tissue packet with protruding tissue：unexplained_added。按同一桌面的边界与长轴，将shot3纸巾所在中央桌区对应到shot1中央可见木面，使用区域对应而非失准投影点。两侧各两帧可核对；shot1该区没有人物或道具遮挡，原图确无纸巾包。其在返回前已出现，不能由空手返回或红本搬运解释。；以主桌边界、窗边座位侧及反向视角作区域对应：shot3中央偏非座位侧的包体位置，对应shot1中央偏右裸露木面；不用不可靠的冻结投影点。两侧各两帧显示空面与实物，且shot1周围可见桌面复查未见纸巾，排除遮挡及漏检。叙事没有引入该物的因果动作，判为未解释新增。

### 空间关系

合理共同静态实体 8 个；全部无序实体对 28；负 cosine 6；进入最终复核 1。
- Dark green mug ↔ Light-colored pencil cup / White pencil cup：cosine = -0.605892007。确认的是局部水平中心序冲突。两容器身份、共同桌面及同一桌—暖气片参考对应均有原图支持。统一采用绿杯中心减笔筒中心，独立观测给出u=v×up上的负→正，而v上保持负；垂直序两镜均未知，不参与确认。原图中容器轮廓、比例、可见底缘与重力方向共同支持水平中心序，不要求完整足迹分离。全局配准确实较差：桌组训练及留出中位误差约159和121像素，因此负余弦−0.606及127.3度夹角本身不能证明冲突；所给数值向量采用相反的端点减法，也不能直接当作局部符号。此处依据的是独立物理参考下的相反u序，故全局变换误差不能消除该局部证据。相同实体布局在参考锚点与上方向一起变换时应保留该符号，单纯反向观看无法解释两镜的局部异号。结论仅说明至少一个容器的摆放不一致，不证明两者都移动或精确交换位置。

存在性 C/K/U/E = 8/2/5/13；空间 C/K/U/E = 0/1/27/0。C=确认兼容，K=确认冲突，U=未知/未确认，E=豁免。
分数沿用 100×(1−K/(C+K+U))；空间无确认冲突即100。全部关系数值和分类见 all_pairs.csv。

## 实际执行 Pipeline

1. 12张原始 JPEG → 新 WeDetect 推理；两个独立 Codex 上下文分别聚类，只保留检测候选支持的实体。
2. 新 GeoCalib 重力估计；每个shot独立 Pi3X 多帧相机/深度，构建固定 Z-up 场景系；逐帧深度约束 Boxer 预测3D框。
3. 两个独立 Codex 上下文判断各shot动静；静止框融合，其他实体保留代表框和逐帧轨迹。
4. Codex 初始跨shot身份对应，确定结构参照。
5. RoMaV2 全部36帧对匹配；结构区域、置信度、循环一致性和深度筛点；重力约束正尺度+yaw+平移稳健配准。
6. 冻结变换，Codex结合全部原帧、对齐框/中心差异、反投影和Prompt逐组复核身份；拆分/修正初始对应并守恒实体清单。
7. 两次独立存在性判断；区分视角、运动、不一致，检查共同实体是否应该离开却仍出现；证据与Prompt门通过才扣分。
8. 对合理共同静态集合的每个无序实体对计算共同坐标系相对向量cosine；仅负值进入筛查。
9. 每shot独立局部支撑/顺序取证；通过门的负值进入跨shot原帧及Prompt运动复核，确认冲突按实体对扣一次。
10. 汇总两分数及逐阶段真实运行时间、实际token，检查输入哈希和调用隔离。

## 证据索引

- study2/result.json、usage.json、stages.csv、calls.csv：结果和消耗
- study2/entities/：新检测、独立聚类及原始CLI记录
- study2/calibration_new/、pi3x/、selected/：新重力、逐帧几何、静态图
- study2/registration/：新关键点和变换
- study2/matching_initial.json、identity_review.json、matching.json：初始/复核对应
- study2/presence.json、spatial.json、all_pairs.csv：分类、得分、全部cosine
- study2/calls/：下游所有新CLI请求/响应/usage
- code_snapshot/、run_spec.json、raw_manifest.json：代码与运行规范
