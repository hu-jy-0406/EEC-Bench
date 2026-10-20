# Gs consistency v1.2

冻结空间关系扩展的源码依赖闭包、提示词、真实三次取证调用、固定 Gs/存在性分数输入、测试、数值回放、敏感性分析及离线原帧网页。旧几何版本与 v1.1 的全部已固定文件哈希复核通过。

本例杯子/笔筒局部中心顺序反转通过几何与原帧条件，分数由 88.89 降到 77.78，覆盖率 33.3%；互补项仍不扣分。两个端点分别计参与冲突，不证明两个物体都移动。方向容差扩大到 ±30° 时该空间结论退回未知。详见 payload/EECBench/docs/gs-consistency-v1.2.md。

从本目录在已有 CPU 空闲的 Slurm 计算节点回放，不发起模型调用、不需要外部原始文件：

```bash
python payload/EECBench/scripts/replay_gs_spatial_consistency.py payload/EECBench/experiments/study_inconsistent_3/gs_relations_20260914/run01
```

21 项测试在工作源码和冻结源码分别通过；数值及分数完全复现。网页数据检查通过，浏览器运行未测试。原始 code_snapshot 保持推断时版本；最终源码的无关结果修复见 post_run_changes.json。
