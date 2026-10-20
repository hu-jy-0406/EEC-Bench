# Study2 / Study3 / Study4 — revised temporal_v2 fresh runs

全新 WeDetect、聚类、逐帧几何、镜头内评估、身份/配准和端点评估。地毯类过滤；原版空间 prompt/逐轴复核；空间分按确认异常对数/总实体对数计算。RoMA+FPS32，Astra/medium。

| 测例 | 秒 | Token | 调用 | Shot1/2/3 实体数 |
|---|---:|---:|---:|---|
| study2 | 1893.46 | 1,366,323 | 15 | 20 / 6 / 20 |
| study3 | 2127.27 | 1,359,719 | 15 | 20 / 6 / 20 |
| study4 | 1925.53 | 1,156,967 | 15 | 18 / 9 / 13 |

| 测例 | 范围 | 存在性分 | 空间分 | 确认异常对 / 总对数 |
|---|---|---:|---:|---|
| study2 | shot1 | 100.00 | 100.00 | 0 / 190 |
| study2 | shot2 | 100.00 | 100.00 | 0 / 15 |
| study2 | shot3 | 100.00 | 100.00 | 0 / 190 |
| study2 | shot1_tail_to_shot3_head | 84.62 | 96.43 | 1 / 28 |
| study3 | shot1 | 100.00 | 100.00 | 0 / 190 |
| study3 | shot2 | 100.00 | 100.00 | 0 / 15 |
| study3 | shot3 | 100.00 | 100.00 | 0 / 190 |
| study3 | shot1_tail_to_shot3_head | 91.67 | 97.22 | 1 / 36 |
| study4 | shot1 | 100.00 | 100.00 | 0 / 153 |
| study4 | shot2 | 100.00 | 100.00 | 0 / 36 |
| study4 | shot3 | 100.00 | 100.00 | 0 / 78 |
| study4 | shot1_tail_to_shot3_head | 100.00 | 100.00 | 0 / 15 |

## 确认异常

- study2 / shot1_tail_to_shot3_head / presence: Desk lamp — The reverse endpoint shows the same desk without the lamp. No person or other object conceals its expected support area or tall silhouette; absence is pixel-grounded, not inferred from missing detections.
- study2 / shot1_tail_to_shot3_head / presence: Tissue packet with protruding tissue — The packet appears on a shared, exposed tabletop. Its central support area is not concealed by the mug, holder or lamp in the source endpoint. The conclusion does not rely on the registered numerical position.
- study2 / shot1_tail_to_shot3_head / spatial: Dark mug | Pencil holder | Dark green mug | White pencil cup — 杯筒身份及大桌g05、固定暖气片g14的对应成立。以同一桌中心至暖气片中心的水平向量定义v，并以物理向上定义u，两镜头的首减次沿u分别为负、正；沿v均为负，垂直序保持未知。原图中的直立筒身、可见口沿和底缘、共同承托及桌面透视共同支持水平中心序，不要求完整足迹分离。全局配准重投影中位误差约94像素、5像素内点率为零且无独立留出验证，故负余弦-0.2699本身不能证明冲突，也不表示精确180度反转。但独立局部参考下的u符号变化不依赖该全局变换；合理中心重建误差不能解释已支持的水平反序。相机反向观察会同时改变锚点和物体的投影，不会改变此相机不变的局部符号，因此同一物理摆放不能解释两个边界状态。冲突仅证明至少一个端点的摆放不连续。
- study3 / shot1_tail_to_shot3_head / presence: Tissue packet — Both exact endpoints support an addition on the same observable tabletop. The source absence is established from pixels, not missing detections or transformed coordinates; reversal cannot reveal a packet hidden at this open location.
- study3 / shot1_tail_to_shot3_head / spatial: Dark green mug | Pencil cup | Dark green mug | Pencil cup — 确认的是局部水平u轴中心顺序改变。统一采用g02绿杯减g07笔筒：Shot1为负，Shot3为正；v轴两镜头均为负，垂直轴保持未知。Shot3单镜头记录的subject/object与端点顺序相反，其正文中“笔筒减杯”的u负、v正，换算至明确声明的统一端点顺序后，与保存的order及汇总一致，无需改动提取结果。两镜头均由杯身比例、口沿、可见底缘、重力方向及同桌支撑约束中心，合理隐藏筒身范围不足以逆转所支持的水平顺序。相同桌体至固定暖气片及物理上方向构成可对应的局部参考；真正反向拍摄会同时变换物体与参考轴，不能使同一物理关系的点积符号改变。全局配准中位重投影误差约71.86像素、5像素内点率为零，故负余弦-0.388本身不能证明冲突，也不表示精确180度反转；此处结论由独立局部证据成立。至少一个端点的摆放不连续，不能推断两者均移动或交换位置。

## 执行与审计

完成 3/3；总调用 45；总 token 3,883,009。
原图哈希、过滤候选记账、等权无剔除配准、评分分母与异常数、阶段与调用 token 对账见 audit.json。每阶段耗时/token 见 stages.csv，全部事件见 events.csv。无外观评分和合成总分。


执行补充：首次节点预检发现设备被其他任务占用，未启动推理，记录见 preflight_attempt1。正式运行在已有分配200798/node209。Study3在boxer_shot2启动前因上一阶段短暂残留146MB显存被保护拦下；设备释放并复查后仅续跑未完成阶段，已完成的新推理未重复执行。首次记录见study3/guard_stop_attempt1和initial_coordinator_status.json；最终三组均成功，见status.json。Study3耗时包含保护退出及恢复间隔。


## API 等价费用估算（2026-09-20）

按 GPT-6 Astra 标准 API 公开单价：普通输入 $10/M、缓存输入 $1/M、输出 $50/M。各请求输入均低于272K（最高223224），缓存写入为0；缓存读取按优惠价计算。服务等级与实际账单未记录，以下为标准API等价估算，不是实际扣费。

| 测例 | Tokens | 估算 USD |
|---|---:|---:|
| study2 | 1,366,323 | $16.16 |
| study3 | 1,359,719 | $16.35 |
| study4 | 1,156,967 | $14.49 |
| 合计 | 3,883,009 | $47.00 |

价格来源：https://developers.openai.com/api/docs/models/gpt-6-astra 。逐项记账见 api_cost_estimate.json。仅含本次45个流水线模型调用，不含GPU计算或其他对话。
