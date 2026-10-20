# Study3：全实体跨 shot 身份测试

状态：**success**；Slurm作业 `191764`。

本轮本地模型使用CPU/FP32，判断调用仍为配置的Astra/medium；设备精度差异另记，不声称与GPU逐数相等。
输入为 Study2 原 Shot1/Shot2 和指定的新 Shot3；沿用正常剧情。所有检测、聚类、几何、动静、配准、身份调用重新执行；不复用旧推理结果。Shot2 为走廊单shot场景，仅独立检测/聚类。

模型仅接收正常输入与原始证据，不接收生成指令、预期异常或指定台灯对应。执行到 aligned identity，未运行 appearance、存在性或空间评分。

阶段耗时：3890.81s；7 次模型调用；366,651 tokens（缓存已含输入，不重复累计）。

最终身份组：{'unmatched': 21, 'matched': 10, 'scope_mismatch': 1}。

## 台灯对应

- `g03` / **matched**：shot1/e3 Black desk lamp；shot3/e4 White desk lamp
  同一主桌上的圆底座、细弯金属杆、钟形灯罩及顶部接头支持延续同一台灯；黑白变化和位置变化单独记录，不据此拆分。

这里只报告模型身份结果，颜色变化未量化为appearance分数。单次新测例不代表一般准确率。

## 全部对应

|组|状态|Shot1实体|Shot1运动|Shot3实体|Shot3运动|
|---|---|---|---|---|---|
|g01_a|unmatched|Framed landscape painting|static|||
|g01_b|unmatched|||Framed landscape painting|static|
|g02|matched|Dark green mug|static|Dark green mug|static|
|g03|matched|Black desk lamp|static|White desk lamp|static|
|g04|matched|Woman wearing a gray sweater and dark trousers|moving|Woman wearing gray sweater and dark trousers|moving|
|g05|matched|Large wooden desk|static|Large wooden table|static|
|g06|unmatched|Small framed picture on bookshelf|static|||
|g07|matched|Pencil cup|static|Pencil cup|static|
|g08|unmatched|Row of books on lower shelf|static|||
|g09|matched|Trailing plant by window|static|Trailing plant by window|static|
|g10|unmatched|Dark bookcase|static|||
|g11|unmatched|Trailing plant on bookshelf|static|||
|g12|matched|Patterned rug|static|Area rug beneath table|static|
|g13|unmatched|Red hardcover book|moving|||
|g14|matched|Wooden chair|static|Wooden chair|static|
|g15|matched|Radiator beneath window|static|Radiator|static|
|g16|unmatched|Books on top shelf|static|||
|g17|matched|Plant pot by window|static|Plant pot on windowsill|static|
|g18|unmatched|Small pot on bookshelf|static|||
|g19|scope_mismatch|Black pen in pencil cup|static|Writing instruments in pencil cup|static|
|g20_a|unmatched|Small wooden side table|static|||
|g20_b|unmatched|||Wooden console table|static|
|g21_a|unmatched|Plant on side table|static|||
|g21_b|unmatched|||Trailing plant on console table|static|
|g22|unmatched|||Larger framed hallway picture|static|
|g23|unmatched|||Framed botanical picture|static|
|g24|unmatched|||Smaller framed hallway picture|static|
|g25|unmatched|||Tissue packet|static|
|g26|unmatched|||Plant pot on console table|static|
|g27|unmatched|||Stack of books|static|
|g28|unmatched|||Hallway rug|static|
|g29|unmatched|||Small hallway cabinet|static|

完整证据：`run_cpu02/matching_initial.json`、`run_cpu02/identity_review.json`、`run_cpu02/matching.json`；CSV：`all_identities.csv`；审计：`audit.json`。

## 配准质量与复核变化

冻结scale、rotation、translation全部保留。原锚点g01因不同端墙的不同画框被拒绝；g05、g15保留，原局部原点和参考不变。训练中位误差118.2px、留出120.3px，桌组中位误差127.8/144.7px且5px内比例为0，说明当前全局配准不能用于精确可见性或位移判定。暖气片贴合较好不意味着全场正确。未使用关系分数，未依据距离优化身份，未重拟合。

初始 13 组 matched 经复核变为 10 组 matched：风景画 g01、边桌 g20、边桌植物 g21 各拆为两个单侧组。最终共 32 组（10 matched、21 unmatched、1 scope_mismatch）；unmatched 不等于实体缺失或一致性失败。笔筒中的单支笔与工具集合为 scope_mismatch。

运动实体也参与本次身份对应：女子 g04 保持 matched；红色书本 g13 为单侧 unmatched。Shot1 的 21 项与 Shot3 的 22 项全部且恰好出现一次，Shot2 的 7 项仅聚类。

运行于已有 allocation 191764 的 auh7-1b-gpu-306，4 个 CPU 核（12–15），所有 GPU 隐藏；原排队作业 200642 已取消。阶段总计 3890.81 秒（64.85 分钟），其中 CPU RoMa 为 2732.83 秒。耗时不包含输入准备与零推理的首次启动失败。7 次 Astra/medium 调用全部成功，366651 tokens；本轮未计算 appearance、presence 或 spatial 分数。

## 配准可视化

见 [俯视图及中心距离](registration_visualization/alignment_overview.png)、[原图上的跨 shot 盒投影](registration_visualization/anchor_reprojection.png) 和 [读图说明](registration_visualization/README.md)。全部使用原冻结结果，无新拟合或模型调用。
