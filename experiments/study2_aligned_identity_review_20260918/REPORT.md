# Study2 对齐后身份复核测试

## 实际范围

保留2026-09-16原身份区域筛选的RoMa配准，未采用后来的无身份全图变换。复用检测、独立单shot动静判断、3D框、初次对应和原配准；新运行对齐后身份复核、两次独立存在性判断、两次隔离单shot局部关系观察和按需最终原帧+Prompt复核。原历史实验文件未覆盖。

## 身份复核结果

| 原组 | 原实体 | 动作 | 新分组及最终存在性分类 |
|---|---|---|---|
| g01 | Framed landscape painting on wall / Framed landscape painting | split | g01_a: unmatched, exempt/viewpoint; g01_b: unmatched, exempt/viewpoint |
| g09 | Trailing plant on bookcase shelf / Plant at far left edge | uncertain | g09: ambiguous, unknown/none |
| g16 | Small wooden plant stand against wall / Small wooden console table | split | g16_a: unmatched, exempt/viewpoint; g16_b: unmatched, exempt/viewpoint |
| g17 | Trailing plant on small wooden stand / Trailing plant on console table | split | g17_a: unmatched, exempt/viewpoint; g17_b: unmatched, exempt/viewpoint |

模型同时收到12张原JPEG、初次身份假设、全部静态框在共同坐标系的位置、各初始配对中心差异、逐帧对侧中心投影、原配准误差和正常剧情Prompt，另附全实体对齐图。提示词检查全部组，无“小木桌必须拆分”等目标名单，也未输入cosine或预期冲突结果。坐标差异不是硬阈值；保持同一物体真实移动仍可被后续空间判断检出。

## 新旧结果

| 指标 | 原实验 | 加入复核后 |
|---|---:|---:|
| 实体分 | 88.23529411764706 | 86.66666666666667 |
| 空间关系分 | 98.18181818181819 | 96.42857142857143 |
| 合理共同静态实体 | 11 | 8 |
| 无序空间对 | 55 | 28 |
| 负cosine候选 | 31 | 7 |

实体C/K/U/E=8/2/5/13；空间C/K/U/E=0/1/27/0。
分组变化会改变计分分母；分数变动不能直接当作视频质量变化。复核拆分与视角免罚是两个判断，视角原因由下游两次判断核实，证据不足仍unknown。

## 确认冲突
- 存在性 g03: ['以同一主桌的桌沿、四角和窗侧关系作支撑面对应：shot1远端灯位在反向镜头转为近端区域。shot3两帧连同整个桌面及其上方都可检查，排除整灯被小型桌面物品遮住或仅漏检。无需采用误差较大的投影中心即可确认无解释缺失。', '以同一主桌的边沿、四角及反向端部关系定位，而非采用失准投影点。两侧各两帧显示灯存在与对应桌面无灯，排除人物遮挡及检测漏项；故事无法解释消失。']
- 存在性 g22: ['以同一主桌四角、长边与窗侧关系对应桌面中央开放区域，反向后左右方向改变。shot1两帧该区域及周围桌面均无纸巾包，红本和杯筒不遮挡此区域；shot3两帧直接显示包体和突出纸巾，排除漏检。判为无解释新增，不采用冻结投影的精确落点。', '由共同主桌的边沿和桌面内部支撑区域对应位置；shot1两帧覆盖其反向对应的桌面区域，且整片可见桌面均无该物。无需依赖失准的单点投影，像素排除漏检与遮挡，剧情不支持加放。']
- 空间 pair_g02_g06: cosine=-0.543758721; 身份和桌面共同支撑成立，同一木桌中心、固定暖气片中心与物理向上提供可对应的局部参考。统一使用绿杯中心减笔筒中心，独立观察支持u序由负变正，v序两镜头均为负；垂直序均未知，不用于冲突判定。数值候选采用相反的端点减法，但两镜头一致，不影响方向分歧。122.94度仅表示钝角，并非精确反转。全局配准确有明显问题：桌组训练及留出中位误差约139和114像素，不能据负余弦直接定案。不过，本例局部水平序由每镜头至少两帧的器形、口沿、底缘、共同桌面和实体参考联合支持，未依赖全局旋转正确。笔筒部分遮挡未使合理体形补全能够反转该局部序。同一物理中心关系在参考锚点和向上一起随视角转换时应保持符号，因此单纯反向拍摄不能解释u符号改变。冲突仅证明至少一个端点的摆放不一致，不证明两者均移动或精确交换位置。

## 配准及审计
原配准文件哈希完全不变。被移除的旧结构参照及原有效点数：{'g01': 0, 'g16': 0}。未重新拟合。
7项身份契约测试通过：允许大差异保持身份、拆分守恒、重复/丢失实体拒绝、双shot拆分证据、失效参照拒绝及原帧坐标范围。校验新空间总体只含复核后合理共同实体，关系计数正确，未变对应的cosine精确重现旧值。

## 消耗
新增模型调用6次；input=824799，output=38302，total=863101 tokens。调用时间跨度15.52分钟（包含阶段间等待/开发）；累计调用耗时20.35分钟（并行部分重复计入），均不含复用历史阶段成本。所有新调用gpt-6-astra/medium，实际计量见usage.json。

## 证据文件

- study2/identity_review.json：完整逐组原帧身份复核及初步单侧原因
- study2/matching_initial.json 与 matching.json：初始/修正对应
- study2/presence.json：两次独立判断及最终原因
- study2/spatial.json：全部空间关系与最终Prompt复核
- study2/calls/：各次请求、原始响应、事件与token记录
- study2/identity_review_alignment.png：提供给模型的中性对齐图


## 同一原组的存在性分类变化

- g05: exempt/viewpoint → unknown/none
- g08: exempt/viewpoint → unknown/none
- g14: exempt/viewpoint → unknown/none
- g23: unknown/none → exempt/viewpoint
- g25: unknown/none → exempt/viewpoint

存在性分母17→15同时受到身份拆分和以上可见性重判影响；确认冲突仍为2项。空间分母55→28，确认冲突仍为1对。原帧身份示意图见study2/identity_changes.png。
