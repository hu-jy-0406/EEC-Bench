# 多 shot 配准实测：两例4-shot、一例8-shot

本轮实验已完成，三张借用 GPU 已全部归还 HoloCine，并核验新 worker 的模型加载记录、心跳、原模式、CPU 和 GPU UUID。借用前这三个 worker 都已完成当前 episode、处于阶段屏障等待，没有中断生成中的视频。

**主要结果：现有优化流程在三例中均没有得到可拟合的点集；直接 Codex 得到两对候选变换，但还不能证明准确性更好。没有任何案例实现所有 shot 的统一坐标系。** 这次实测定位到的主要瓶颈是静止锚点的覆盖及其可用像素对应，尚未进入数值优化的精度比较。

| 场景 | 优化方法最终分组 | 直接 Codex 最终分组 | 关键原因 |
|---|---|---|---|
| 停车场4-shot | {1} {2} {3} {4} | {1,3} {2} {4} | 旧锚点规则限固定结构/大型家具，静止车辆被排除；Codex 用车给出低置信候选 |
| 卧室4-shot | {1} {2} {3} {4} | {1} {2} {3} {4} | 找到 Shot2/4 的床，但没有通过筛选的 RoMa 点；Codex 全部弃权 |
| 餐厅8-shot | {1} {2} {3} {4} {5} {6} {7} {8} | {1,2} {3} {4} {5} {6} {7} {8} | Shot1/2 桌子可匹配，但 RoMa 点不足；其余视角家具缺检、局部范围或身份不确定 |

## 筛选失败发生在哪里

两个真正调用 RoMa 的 shot 对均使用原设置36个帧对、每对5000个匹配：

| 配对 | 原始采样匹配 | 两端落在同一锚点有效区域 | 再通过置信度和 cycle 筛选 | 可拟合3D点 |
|---|---:|---:|---:|---:|
| 卧室 Shot2/4 | 180000 | 9 | 0 | 0 |
| 餐厅 Shot1/2 | 180000 | 21 | 0 | 0 |

卧室 Shot2 的床仅尾帧80有保留检测，另外5帧缺框；没有补框或借用融合框代替。原结构区域还会扣除其他实体遮挡区域。这里记录的是筛选计数，未凭此断言每个丢点的物理原因。FPS32和既定无平方距离和优化目标均未获得可拟合输入，因此不能将结果描述成“优化算法算得不准”。停车场未调用 RoMa，其0.03秒是提前跳过耗时，并非成功配准速度。

全局初始身份已直接连上卧室 Shot1/3 女子、Shot2/4 床和人物，无需中间镜头出现。餐厅人物也连接了非相邻镜头；身份可对应不等于坐标可以可靠配准。桌子 Shot5/6 只露窄条、身份仍不确定，未强行并入 Shot1/2。

## Codex 候选及端点诊断

变换采用 new→root：s·Rz·point+t。停车场 Shot3→Shot1：s=0.68，yaw=160°，t=(-0.04,0.55,-0.08)，模型置信度low；餐厅 Shot2→Shot1：s=0.95，yaw=190°，t=(-0.04,-0.81,0.01)，置信度medium。二者均主要靠一个物体，缺少独立固定地标约束，置信度不是实测误差。

原始尾帧80→首帧0的共同静止实体中心距离：停车场车辆0.105129，餐厅桌子0.029452（各自根镜头重建单位，不是米，两个数不能直接横比）。各对仅一个共同静止实体，除以静止实体位移中位数必为re=1，**不提供区分度，也不能验证配准正确**。所有原始位移及re仍保存。

停车场三个共同端点实体产生3个cosine，其中2个负值；餐厅3个cosine全部为正。相关配对涉及运动人物，且使用初始身份和未经验证的变换；仅保存为几何候选，不能当作已确认空间错误或最终评分。没有有效 RoMa 3D点池，因此两方法同点残差对比为空，绝不是误差为0。

## 对后续方案的判断

当前实验不足以选出精度赢家。优先研究锚点可用性、缺检及有效区域覆盖，再比较优化器和直接 Codex 的准确度更有价值。停车场暴露了“固定结构/家具”范围排除静止车辆的问题；卧室/餐厅则暴露了语义匹配成功但像素几何不足的问题。本轮没有擅自放宽锚点规则、删掉cycle筛选、补检测框或强制 Codex 输出变换。直接 Codex 虽多得到两对候选，整体分组仍很碎，不能据此替换生产方法。

## 实测开销

共16个shot、96原始关键帧，共享新跑检测、聚类、GeoCalib、Pi3X/Boxer和独立运动分类。每例全局初始身份与直接配准并行，优化等待初始身份；三例并行。

| 案例 | 共享前端秒 | 全局初始身份秒 | 优化分支秒 | Codex分支秒 | 单例总秒 | 全部API tokens | 估算USD |
|---|---:|---:|---:|---:|---:|---:|---:|
| parking4 | 326.00 | 53.67 | 0.24 | 65.54 | 404.45 | 282,205 | 2.992810 |
| bedroom4 | 381.53 | 84.43 | 138.27 | 46.43 | 617.05 | 338,029 | 3.486578 |
| diner8 | 505.25 | 77.50 | 137.08 | 106.38 | 731.08 | 676,277 | 7.050650 |

从最早实验启动到最后结果，实测并行耗时 **745.96秒（12.43分钟）**，含HIP探测，排除此前资源排队/失败启动、选样准备及最后报告整理/worker恢复。全48次模型调用成功，共 **1,296,511 tokens / USD13.530038标准API等价估算**，不是账单；GPU费用未知。两次数值拟合退出是没有输入点的预期配准失败，不是API失败。此前GPU启动失败未产生模型调用。

输入1,279,047（含缓存14,848），输出17,464；按已记录Astra单价每百万未缓存输入USD10、缓存输入USD1、输出USD50计算，缓存未重复计数。原始逐调用记录见comparison.json，汇总及恢复证据见final_audit.json和restore/verified.json。

本轮为配准组件实验：保留 GeoCalib，生产入口未改；没有完成配准后身份复核和空间冲突确认，也没有运行完整一致性评分。以下附自动生成的英文数值表、原帧和图。

---

# Three-episode multi-shot registration comparison

Fresh common frontend; independent incremental optimization and pure Codex registration. Initial scene-wide identities are frozen for diagnostics. This is NOT a full consistency-scoring run or ground-truth accuracy benchmark.

| Case | Method | Coordinate groups | Attached shots | Comparable shot pairs | Method wall seconds |
|---|---|---:|---:|---:|---:|
| parking4 | optimization | 4 | 0 | 0/6 | 0.03 |
| parking4 | direct | 3 | 1 | 1/6 | 65.26 |
| bedroom4 | optimization | 4 | 0 | 0/6 | 138.02 |
| bedroom4 | direct | 4 | 0 | 0/6 | 46.15 |
| diner8 | optimization | 8 | 0 | 0/28 | 136.87 |
| diner8 | direct | 7 | 1 | 1/28 | 106.15 |

Numeric attachment is provisional. More connected shots does not by itself mean better registration. Optimization acceptance checks do not use a calibrated residual threshold; direct acceptance is the model’s register/abstain judgment.

## Same-point registration diagnostics

Mean Euclidean residual divided by target point-cloud RMS radius. Same anchor/RoMa pool for both methods; FPS32 fit points come from this pool, so it is NOT independent validation. Null/missing comparisons are unavailable, not zero error.

| Case | Shot pair | Method | Point count | Normalized mean residual |
|---|---|---|---:|---:|

## Usage

All recorded model calls: 1,296,511 tokens; estimated standard API equivalent USD 13.530038. Not actual billing. Includes common clustering/motion/initial identity and direct registration. Startup failures had no API calls. Cluster cost unavailable.

## Visuals and detailed records

### parking4

![Original first frames](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/multishot_registration_ab_20260922/inputs/parking4/overview.jpg)

![Registration comparison](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/multishot_registration_ab_20260922/shared/parking4/registration_topviews.png)

[Raw entity center distances and re](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/multishot_registration_ab_20260922/shared/parking4/entity_distances.csv) · [All cosine proposals and point diagnostics](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/multishot_registration_ab_20260922/shared/parking4/comparison.json)

### bedroom4

![Original first frames](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/multishot_registration_ab_20260922/inputs/bedroom4/overview.jpg)

![Registration comparison](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/multishot_registration_ab_20260922/shared/bedroom4/registration_topviews.png)

[Raw entity center distances and re](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/multishot_registration_ab_20260922/shared/bedroom4/entity_distances.csv) · [All cosine proposals and point diagnostics](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/multishot_registration_ab_20260922/shared/bedroom4/comparison.json)

### diner8

![Original first frames](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/multishot_registration_ab_20260922/inputs/diner8/overview.jpg)

![Registration comparison](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/multishot_registration_ab_20260922/shared/diner8/registration_topviews.png)

[Raw entity center distances and re](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/multishot_registration_ab_20260922/shared/diner8/entity_distances.csv) · [All cosine proposals and point diagnostics](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/multishot_registration_ab_20260922/shared/diner8/comparison.json)

Distinct coordinate groups are offset only for plotting and never compared numerically. Overlays project the same original 3D box corners onto each method’s XY plane; silhouettes need not be rectangles. Entity position differences can be real generated changes, detection noise or registration error. Negative cosines here are proposals, not confirmed spatial violations. Final aligned identity/spatial review and appearance/prompt scoring were outside this registration experiment.
