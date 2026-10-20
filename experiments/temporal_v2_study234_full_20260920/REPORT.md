# Study2 / Study3 / Study4 — temporal_v2 完整实验

三个测例均从新的 WeDetect 检测开始，独立完成全部三个 shot 的推理；使用 roma_fps32 优化配准。仅复用原始输入关键帧、正常叙事 prompt 和预训练权重，不复用历史检测、几何、身份或配准结果。

Study4 对应原始目录 `experiments/study3-concise-mtd-local/`。每个 shot 内比较全部关键帧组合；跨 shot 只评估同场景 shot1 尾帧和 shot3 首帧。Shot2 是独立场景，仍做 shot 内评估。

| 测例 | 完整耗时（秒） | Token | API 调用 | 各 shot 实体数 |
|---|---:|---:|---:|---|
| study2 | 1968.32 | 1,512,536 | 15 | 21 / 7 / 22 |
| study3 | 2003.44 | 1,491,777 | 15 | 21 / 7 / 22 |
| study4 | 2005.03 | 1,380,996 | 16 | 20 / 9 / 15 |

耗时包含 WeDetect、RoMA、几何和 API；单测例内部有阶段重叠，三个测例并行，不能用阶段耗时之和替代端到端耗时。Token 为输入（含缓存）加输出，详见每个测例的 calls.csv。

| 测例 | 范围 | 存在性 | 空间 | 存在性 C/K/U/E | 空间 C/K/U/E |
|---|---|---:|---:|---|---|
| study2 | shot1 | 100.00 | 100.00 | 9/0/6/6 | 0/0/171/39 |
| study2 | shot2 | 100.00 | 100.00 | 5/0/1/1 | 0/0/15/6 |
| study2 | shot3 | 100.00 | 100.00 | 19/0/0/3 | 0/0/210/21 |
| study2 | shot1_tail_to_shot3_head | 84.62 | 100.00 | 8/2/3/19 | 0/0/36/0 |
| study3 | shot1 | 100.00 | 100.00 | 10/0/6/5 | 0/0/190/20 |
| study3 | shot2 | 100.00 | 100.00 | 5/0/1/1 | 0/0/15/6 |
| study3 | shot3 | 100.00 | 100.00 | 14/0/4/4 | 0/0/210/21 |
| study3 | shot1_tail_to_shot3_head | 92.31 | 100.00 | 9/1/3/19 | 0/0/45/0 |
| study4 | shot1 | 100.00 | 100.00 | 11/0/7/2 | 0/0/190/0 |
| study4 | shot2 | 100.00 | 100.00 | 1/0/6/2 | 0/0/28/8 |
| study4 | shot3 | 100.00 | 100.00 | 9/0/3/3 | 0/0/91/14 |
| study4 | shot1_tail_to_shot3_head | 100.00 | 100.00 | 7/0/7/13 | 0/0/24/4 |

C=确认兼容，K=确认冲突，U=不确定，E=合理运动/遮挡等豁免。沿用原评分公式；空间 100 分可能伴随低覆盖率，不代表所有关系均已确认一致。不存在虚构的跨范围总分。

## 确认冲突

- study2 / shot1_tail_to_shot3_head / presence: Black desk lamp; [{"shot_id": "shot1", "frame_id": 120}, {"shot_id": "shot3", "frame_id": 0}]; Only the notebook is removed and no one rearranges the study. Reversing the camera cannot hide a standing lamp from an exposed tabletop.
- study2 / shot1_tail_to_shot3_head / presence: Tissue packet with protruding tissue; [{"shot_id": "shot1", "frame_id": 120}, {"shot_id": "shot3", "frame_id": 0}]; Only the notebook is taken, no one enters or rearranges the study, and the woman returns empty-handed. Nothing supplies or places a tissue packet.
- study3 / shot1_tail_to_shot3_head / presence: Tissue packet; [{"shot_id": "shot1", "frame_id": 120}, {"shot_id": "shot3", "frame_id": 0}]; Only the notebook is handled, nobody rearranges the study, and the woman returns empty-handed. No supported action places tissues on the desk.

## 每阶段耗时与 token

| 测例 | 阶段 | 秒 | Token |
|---|---|---:|---:|
| study2 | detection_and_clustering | 71.19 | 46,074 |
| study2 | geocalib | 42.75 | 0 |
| study2 | prepare_shot_inputs | 0.27 | 0 |
| study2 | pi3x_shot1 | 52.31 | 0 |
| study2 | boxer_shot1 | 15.74 | 0 |
| study2 | pi3x_shot2 | 24.00 | 0 |
| study2 | boxer_shot2 | 14.29 | 0 |
| study2 | pi3x_shot3 | 23.26 | 0 |
| study2 | boxer_shot3 | 14.39 | 0 |
| study2 | expected_motion_shot1 | 318.74 | 87,630 |
| study2 | expected_motion_shot2 | 123.29 | 42,765 |
| study2 | within_shot2 | 49.52 | 48,558 |
| study2 | expected_motion_shot3 | 311.52 | 102,580 |
| study2 | within_shot1 | 270.56 | 112,610 |
| study2 | within_shot3 | 177.35 | 125,559 |
| study2 | pair_000_prepare | 0.26 | 0 |
| study2 | pair_000_initial_identity | 109.89 | 92,277 |
| study2 | pair_000_roma_matches | 152.59 | 0 |
| study2 | pair_000_lift | 1.52 | 0 |
| study2 | pair_000_registration | 0.45 | 0 |
| study2 | pair_000_identity_review | 402.05 | 157,654 |
| study2 | pair_000_boundary | 491.74 | 696,829 |
| study3 | detection_and_clustering | 83.75 | 45,944 |
| study3 | geocalib | 42.67 | 0 |
| study3 | prepare_shot_inputs | 0.25 | 0 |
| study3 | pi3x_shot1 | 42.13 | 0 |
| study3 | boxer_shot1 | 14.17 | 0 |
| study3 | pi3x_shot2 | 23.66 | 0 |
| study3 | boxer_shot2 | 13.34 | 0 |
| study3 | pi3x_shot3 | 24.26 | 0 |
| study3 | boxer_shot3 | 13.51 | 0 |
| study3 | expected_motion_shot1 | 307.67 | 87,208 |
| study3 | expected_motion_shot2 | 124.76 | 42,785 |
| study3 | within_shot2 | 38.64 | 48,302 |
| study3 | expected_motion_shot3 | 333.76 | 99,593 |
| study3 | within_shot1 | 254.98 | 109,686 |
| study3 | within_shot3 | 165.41 | 122,254 |
| study3 | pair_000_prepare | 0.31 | 0 |
| study3 | pair_000_initial_identity | 132.31 | 92,412 |
| study3 | pair_000_roma_matches | 150.04 | 0 |
| study3 | pair_000_lift | 1.92 | 0 |
| study3 | pair_000_registration | 0.62 | 0 |
| study3 | pair_000_identity_review | 439.60 | 157,598 |
| study3 | pair_000_boundary | 490.87 | 685,995 |
| study4 | detection_and_clustering | 75.02 | 45,538 |
| study4 | geocalib | 42.37 | 0 |
| study4 | prepare_shot_inputs | 0.25 | 0 |
| study4 | pi3x_shot1 | 48.85 | 0 |
| study4 | boxer_shot1 | 15.97 | 0 |
| study4 | pi3x_shot2 | 24.34 | 0 |
| study4 | boxer_shot2 | 12.95 | 0 |
| study4 | pi3x_shot3 | 24.60 | 0 |
| study4 | boxer_shot3 | 13.08 | 0 |
| study4 | expected_motion_shot1 | 306.12 | 85,532 |
| study4 | expected_motion_shot2 | 165.93 | 44,467 |
| study4 | within_shot2 | 209.10 | 58,089 |
| study4 | within_shot1 | 263.76 | 109,857 |
| study4 | expected_motion_shot3 | 233.31 | 70,617 |
| study4 | within_shot3 | 537.51 | 183,515 |
| study4 | pair_000_prepare | 0.26 | 0 |
| study4 | pair_000_initial_identity | 97.64 | 78,393 |
| study4 | pair_000_roma_matches | 136.09 | 0 |
| study4 | pair_000_lift | 2.57 | 0 |
| study4 | pair_000_registration | 0.49 | 0 |
| study4 | pair_000_identity_review | 394.70 | 128,420 |
| study4 | pair_000_boundary | 507.44 | 576,568 |

逐事件记录见 events.csv，含确认冲突、不确定、兼容和豁免；完整 witnesses 和判断理由保存在各测例 within/*/results.json 与 pairs/pair_000/boundary/results.json。

## 关键行为与限制

- 三个测例的人物身份均正确跨 shot 匹配；study3 黑/白台灯仍归为同一实体，未做 appearance 评分。
- study4 的高杯与矮杯均参与边界比较；短杯到高杯向量 cosine = -0.9495143。正常 prompt 明确允许离镜期间交换杯子位置，因此复核为合理变化豁免，而非跳过运动实体。
- 本次没有确认任何空间冲突。所有范围的空间 coverage 都为 0；非负 cosine 不被当作已验证兼容，负候选中的几何/中心语义疑点仍保留 unknown。
- study2 的绿杯—笔筒边界 cosine = -0.2410950，但独立局部证据未排除几何与中心语义误差，最终 unknown。不能将旧版融合框评分与本次边界帧评分视为相同测量。
- 三测例各 22 个阶段全部成功，共 46 次模型调用，4,385,309 token。没有失败推理重跑。原图哈希、阶段 token 与调用 token 对账、每次实际 32 点等权无剔除均核验通过；8 个配准源码哈希与固定基线一致。
