# Study2 / Study3：FPS32 与纯 Codex，四次独立完整评测

从 WeDetect-Anything 起重新执行各自前端、身份匹配及后续评测。Shot1/Shot3 同场景参与评分；Shot2 单独检测与聚类。外观评分未运行。

存在性与空间分数沿用当前静止实体评测口径；跨 shot 身份匹配包含运动、未知状态实体。失败或未完成的实验不填最终分数。

|实验|状态|存在性|空间|墙钟秒|Token|RoMA 秒|配准阶段秒|
|---|---|---:|---:|---:|---:|---:|---:|
|study2_fps32|completed|88.2353|96.4286|1,309.93|701,394|130.70|0.79|
|study2_codex_direct|completed|84.6154|96.4286|1,343.56|756,632|—|28.29|
|study3_fps32|completed|91.6667|97.2222|1,452.57|696,393|131.31|0.49|
|study3_codex_direct|completed|92.8571|97.2222|1,330.11|748,753|—|21.77|

Token 为四次实验实际调用的输入＋输出，缓存输入已包含在输入中。阶段存在重叠，不将阶段时间求和当作墙钟；RoMA 时间已包含在各自墙钟中。详见 calls.csv / stages.csv。
各实验独立检测、聚类、动静判断和身份匹配，实体总体可能不同；结果差异不能全部归因于配准。四次单次运行也不足以估计随机性。

## study2_fps32

实体总体：`{"shot1": {"detected_entities": 21, "identity_entities": 21, "motion_counts": {"static": 19, "moving": 2}}, "shot2": {"detected_entities": 7, "identity_entities": null, "motion_counts": {}}, "shot3": {"detected_entities": 22, "identity_entities": 22, "motion_counts": {"static": 21, "moving": 1}}}`。
完整身份组：`{"unmatched": 21, "matched": 9, "ambiguous": 1, "scope_mismatch": 1}`；匹配的运动/未知组：`["g04"]`。

存在性计数及覆盖：`{"score": 88.23529411764706, "coverage": 0.5882352941176471, "N": 17, "C": 8, "K": 2, "U": 7, "E": 13, "identification_interval": [47.05882352941177, 88.23529411764706]}`。

存在性确认冲突：
- Black desk lamp ↔ ∅；unexplained_missing；以同桌两端和完整支承面对应定位，反向画面的可见范围覆盖原灯占位及其上方；两帧直接排除人物遮挡和漏检。灯的消失不符合故事。
- ∅ ↔ Tissue packet with protruding tissue；unexplained_added；以同桌边界和中部支承面对应定位，投影约[608,257]仅作辅助；原图相关桌面及周围均无纸巾包，两侧各两帧排除遮挡和漏检。该新增不受故事授权。

空间计数及覆盖：`{"score": 96.42857142857143, "coverage": 0.03571428571428571, "N": 28, "C": 0, "K": 1, "U": 27, "E": 0, "identification_interval": [0.0, 96.42857142857143]}`。

空间确认冲突：
- Dark green mug ↔ Dark green mug / Pencil cup ↔ Pencil cup；；cosine=-0.200685；negative_cosine_and_independent_local_opposite_order_and_visual_gates_and_prompt_motion_excluded

审计状态：**passed**。

## study2_codex_direct

实体总体：`{"shot1": {"detected_entities": 21, "identity_entities": 21, "motion_counts": {"static": 19, "moving": 2}}, "shot2": {"detected_entities": 7, "identity_entities": null, "motion_counts": {}}, "shot3": {"detected_entities": 22, "identity_entities": 22, "motion_counts": {"static": 21, "moving": 1}}}`。
完整身份组：`{"unmatched": 21, "matched": 9, "ambiguous": 1, "scope_mismatch": 1}`；匹配的运动/未知组：`["g04"]`。

存在性计数及覆盖：`{"score": 84.61538461538461, "coverage": 0.7692307692307693, "N": 13, "C": 8, "K": 2, "U": 3, "E": 17, "identification_interval": [61.53846153846154, 84.61538461538461]}`。

存在性确认冲突：
- Black desk lamp ↔ ∅；unexplained_missing；以同一桌体四角、长边及窗侧椅定位桌端；反向镜头覆盖整个支撑面及灯高范围，无须依赖不可靠的中心投影。两侧各两帧排除了遮挡及漏检，台灯属无解释缺失。
- ∅ ↔ Tissue packet with protruding tissue；unexplained_added；以同桌边界、窗侧椅和桌心支撑面对应定位，使用覆盖位置不确定性的空区框，不把杯筒偏移或粗投影当作精确坐标。shot1两帧该区域无物且无遮挡，shot3两帧明确有包；红本运动不能解释新增纸巾包。

空间计数及覆盖：`{"score": 96.42857142857143, "coverage": 0.03571428571428571, "N": 28, "C": 0, "K": 1, "U": 27, "E": 0, "identification_interval": [0.0, 96.42857142857143]}`。

空间确认冲突：
- Dark green mug ↔ Dark green mug / Pencil cup ↔ White pencil cup；；cosine=-0.442464；negative_cosine_and_independent_local_opposite_order_and_visual_gates_and_prompt_motion_excluded

审计状态：**passed**。

## study3_fps32

实体总体：`{"shot1": {"detected_entities": 21, "identity_entities": 21, "motion_counts": {"static": 19, "moving": 2}}, "shot2": {"detected_entities": 7, "identity_entities": null, "motion_counts": {}}, "shot3": {"detected_entities": 22, "identity_entities": 22, "motion_counts": {"static": 21, "moving": 1}}}`。
完整身份组：`{"unmatched": 21, "matched": 10, "scope_mismatch": 1}`；匹配的运动/未知组：`["g04"]`。

存在性计数及覆盖：`{"score": 91.66666666666666, "coverage": 0.8333333333333334, "N": 12, "C": 9, "K": 1, "U": 2, "E": 18, "identification_interval": [75.0, 91.66666666666667]}`。

存在性确认冲突：
- ∅ ↔ Tissue packet；unexplained_added；以同一桌板边界和桌面中段映射位置，冻结投影约[589,260]仅辅助；两侧各两帧确认对应可见区域从空到有。原图排除遮挡和漏检，正常故事不能解释新增。

空间计数及覆盖：`{"score": 97.22222222222221, "coverage": 0.027777777777777776, "N": 36, "C": 0, "K": 1, "U": 35, "E": 0, "identification_interval": [0.0, 97.22222222222223]}`。

空间确认冲突：
- Dark green mug ↔ Dark green mug / Pencil holder ↔ Pencil cup；；cosine=-0.341227；negative_cosine_and_independent_local_opposite_order_and_visual_gates_and_prompt_motion_excluded

审计状态：**passed**。

## study3_codex_direct

实体总体：`{"shot1": {"detected_entities": 21, "identity_entities": 21, "motion_counts": {"static": 19, "moving": 2}}, "shot2": {"detected_entities": 7, "identity_entities": null, "motion_counts": {}}, "shot3": {"detected_entities": 22, "identity_entities": 22, "motion_counts": {"static": 21, "moving": 1}}}`。
完整身份组：`{"unmatched": 19, "matched": 10, "scope_mismatch": 1, "ambiguous": 1}`；匹配的运动/未知组：`["g04"]`。

存在性计数及覆盖：`{"score": 92.85714285714286, "coverage": 0.7142857142857143, "N": 14, "C": 9, "K": 1, "U": 4, "E": 15, "identification_interval": [64.28571428571429, 92.85714285714286]}`。

存在性确认冲突：
- ∅ ↔ Tissue packet；unexplained_added；以共同桌板及桌面边界定位中部支撑区，低置信投影约[565,273]仅辅助。shot1两帧该区裸露且无纸巾包，shot3两帧直接见包；像素排除遮挡和漏检，正常叙事不能解释新增。

空间计数及覆盖：`{"score": 97.22222222222221, "coverage": 0.027777777777777776, "N": 36, "C": 0, "K": 1, "U": 35, "E": 0, "identification_interval": [0.0, 97.22222222222223]}`。

空间确认冲突：
- Dark green mug ↔ Dark green mug / Pencil holder ↔ Pencil holder；；cosine=-0.521493；negative_cosine_and_independent_local_opposite_order_and_visual_gates_and_prompt_motion_excluded

审计状态：**passed**。

## 两种方法是否一致

- study2：存在性分数不同；空间分数相同
- study3：存在性分数不同；空间分数相同

逐实体缺陷以各实验上方清单为准，完整身份与理由保留在 comparison.json 和原始 presence.json / spatial.json。不要仅根据分数相等断言缺陷判断一致；不同 runs 的 group_id 不可直接对应。

总审计状态：**passed**。audit.json 记录原图、独立输入、全部实体覆盖、静止投影、方法分支与源文件哈希检查。它验证执行产物，不证明模型语义判断正确。


## 完成与解释补充

四组均完成并通过最终审计。Study2两方案确认同样的存在性缺陷：台灯缺失、纸巾包新增；Study3两方案均确认纸巾包新增。四组的唯一空间冲突均为深绿色杯子与笔筒的相对位置不一致。两方案在各测例上的空间分数相同。Study3黑灯/白灯保持同一实体，未执行appearance评分。

存在性分数差异不代表确认冲突不同：Study2 FPS32与direct的C/K相同(8/2)，U为7/3；Study3 C/K相同(9/1)，U为2/4。现有公式N=C+K+U，未知项进入分母，所以分数随U变化。豁免数和身份分组也有差异，详见上文；本轮没有修改评分公式。

这是四组各自从WeDetect重跑的端到端实验，并非冻结上游的纯配准消融；相机标定、重建与模型判断均可能波动。仅每配置一次，不能据耗时或分数直接推断某方案普遍更快/更准确。

Study3FPS32的首次boxer_shot3启动被GPU空闲检查拦下（前一阶段结束后显存尚未降至阈值）；保留原失败日志与runtime，在重新核验空闲后仅继续未执行阶段。没有重复已完成推理，最终24分13秒含这次停顿。初始node306预检查也曾因其他任务占用而停止，但发生于四组推理开始之前，未计入各实验端到端时间。之后在已有allocation196092/node196的四张独立GPU上并行完成。

status_original_coordinator.json保留旧协调器将已恢复分支标failed的原始状态；status.json为四组最终成功的汇总，case pipeline_runtime.json包含完整阶段与恢复记录。没有取消或修改其他用户任务。
