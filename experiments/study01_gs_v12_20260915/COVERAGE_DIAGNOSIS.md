# Study0 零覆盖原因追踪

## 确认的链条

1. Study0 两 shot 检测输入均无窗户候选，聚类无窗户实体；Study1 的历史实体输入有窗户，候选数为2/5，原始标签均为窗户。Study0 的大框房子候选覆盖整幅图，不能用来补造窗户。
2. 静态图与匹配阶段保留了这一差异：Study0 只有边桌和书桌两个 eligible anchors，Study1 另有窗户。两例全局 registration trusted 都是 false，因此不能把差异仅解释为全局配准是否成功。
3. Study1 的7个最终compatible项中，画、边桌、盆栽、书桌、边桌下书堆这5项的两轮review均把窗户列作local_visual参照；窗户本身也通过，椅子使用书桌+边桌通过。
4. Study0 第一轮盆栽/书堆虽然输出compatible，但 alternative_mappings_excluded=false，被确定性门槛改为unknown；第二轮18项全部unknown。因此没有通过门槛的positive-vs-unknown分歧，未触发bounded recheck。two_reviews_agree指门槛后的标签一致，并非全部原始文字判断一致。
5. 窗户缺失不是唯一解释：椅子在两例均有相近的融合高度和遮挡缩框。Study0高度0.915/0.919，IoU0.803/0.827；Study1高度0.913/0.920，IoU0.807/0.819。Study1两轮用书桌+边桌肯定局部对应；Study0两轮却要求更充分对应并弃权。记录支持判定策略不稳定，但尚未进行控制变量干预，不能量化各因素贡献。

## 执行条件与解释边界

Study0本次CPU新检测/聚类，Study1复用历史ROCm GPU检测/聚类。模型权重SHA256、上游模型源码/词表哈希、seed0和postprocessing一致；适配器差异只有路径，检测器差异为包版本记录与字体路径。输入图像不是字节相同。不能凭现有结果断言CPU导致窗户漏检；需要同图同执行条件对照。

现有比较不是仅删除台灯、其余中间表示完全固定的受控实验。背景参照漏检、依赖图内实体的局部对应门槛、同模型视觉判断不稳定，共同构成可追溯的覆盖放大链条。算法回放/隔离审计通过不代表测量稳定性或正确性通过。保留原分数，不能用这对结果宣称有效排序。

## 原始证据

- study0/entities/shots/{shot1,shot3}/input.json 与 response.json
- study1/entities/reuse.json 指向历史parallel_run01
- 两例 gs_v11/{matching.json,geometry_diagnostics.json,score.json}
- 两例 gs_v11/{witness,verification}/response.json
- runtime/EECBench/prompts/gs_consistency_check_v1.txt
- runtime/EECBench/scripts/score_gs_consistency.py：admitted与score

本次只读追踪既有证据，没有新模型调用、GPU计算或评分修改。
