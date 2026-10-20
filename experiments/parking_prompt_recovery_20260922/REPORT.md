# 停车场：逐 shot prompt 绑定与 Grounding DINO 补检

已完成四个 shot 的组件测试。原 WeDetect 检测和独立聚类显式复用，未重跑生成视频；新跑逐 shot 绑定、24帧 Grounding DINO 定向补检和独立候选审核。保留所有原始框，只有检测器新候选能新增实体或填补空帧。不是完整 GPU pipeline/配准/评分重跑。

## 结果

| Shot | 实体数：前→后 | 柱子检出帧：前→后 | 新增有效观测 |
|---|---:|---:|---:|
| Shot1 | 4 → 6 | 0/6 → 6/6 | 11 |
| Shot2 | 4 → 5 | 0/6 → 6/6 | 9 |
| Shot3 | 6 → 7 | 不要求，未补检 | 8 |
| Shot4 | 4 → 7 | 0/6 → 6/6 | 13 |

Shot1新增柱子和肩带；Shot2新增柱子，填补面具/肩带空帧；Shot3新增耳饰，面具仍仅第16帧有观测；Shot4新增柱子、车和肩带，车辆只检出首帧。Shot4旧肩包整体实体保持unknown，新的肩带部件单独保留，不将二者强制合并；这是仍需关注的整体/部件重叠诊断。缺口不等于物体不存在。

黄色柱子在Shot1/2/4的原prompt明确出现。本次按原文引用冻结prompt_registry_v1（8项实体及4-shot schedule），不是假称旧配准实验已有结构化schedule。Shot3未要求柱子，所以不因同场景自动补建。

## 实现与下游接口

run_gs_integrated.py 默认 --prompt-recovery auto：有registry/align contract时，在初检聚类之后、GeoCalib/三维实体输入之前执行；--prompt-recovery off恢复旧流程。--prompt-recovery-device cuda默认，cpu可显式选择。无registry时不凭空生成schedule，保持原流程。本次CPU运行避开等待中的HoloCine GPU，GPU时间未测。

prepare_gs_integrated.py、全局实体表、appearance均读取审核后的实体及候选路径；原初检目录保持不变。跨shot身份不由prompt ID强制合并；最终全局绑定复用一致的shot绑定，unknown/冲突才再次评估。失败补检阻断下游，不输出假完整结果。验证了4shot几何输入确实包含补检实体，使用旧calibration作接口验证，未推理新3D框。

## 失败与修复

Shot4首轮审核试图把肩带框补入绑定unknown的旧肩包整体，语义校验拒绝。原回复和成本保留为Shot4_review_failed1。将已有规则写入逐候选schema：existing目标只能是已bound且该帧缺框的实体。仅重跑Shot4审核后通过，其他三个审核及检测复用；原非法回复对新schema的拒绝检查通过。未手改模型结果或放宽规则。

## 实测开销

全部9次API调用（含1次被拒绝审核）：159,817 tokens，USD 1.807730 标准Astra API等价估算，非账单。失败审核：18,719 tokens / USD 0.222110。
Grounding DINO CPU单次加载＋24帧：163.91秒。首个绑定启动到最后纠正审核完成：415.77秒，含排查与修改等待，不是优化后生产耗时。检测本身0API tokens/USD0 API成本，CPU/GPU资源费用未计；独立环境探针额外1帧，约8.74秒（不含Python导入），不计为正式24帧补检。
计价沿用已核实Astra标准每百万tokens：输入USD10、缓存USD1、输出USD50；缓存是输入子集，不重复计费。逐调用原始usage在calls目录，汇总audit.json。

## 图像证据

![Shot1/Shot2补检柱子](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/parking_prompt_recovery_20260922/visuals/Shot1_Shot2_recovered_pillars.jpg)

![Shot1六帧柱子](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/parking_prompt_recovery_20260922/visuals/Shot1_pillar_all_frames.jpg)

![Shot2六帧柱子](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/parking_prompt_recovery_20260922/visuals/Shot2_pillar_all_frames.jpg)

![Shot4六帧柱子](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/parking_prompt_recovery_20260922/visuals/Shot4_pillar_all_frames.jpg)


## 回归验证

74项测试全部通过（补检、prompt绑定、全局实体表、integrated、temporal）。原始框/检测候选来源审计和四shot几何输入接口检查通过。Shot1/2首帧柱子可视化已人工式检查，框对应目标柱子。
