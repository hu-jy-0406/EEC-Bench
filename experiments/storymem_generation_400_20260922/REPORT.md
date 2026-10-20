# StoryMem400：8 节点作业已提交

作业号 **208465**；查询时间 2026-09-22T01:10:38.644578+00:00。状态 **PENDING**，原因 **Priority**。

Slurm 当前预计启动时间：**2026-09-23T08:13:59 UTC**；预计等待 **31.06 小时**。这是会随调度变化的预估，不是启动承诺。提交前 test-only 的2026-09-24T13:29:10预估已被正式作业的当前预估取代。

## 申请与执行

- faculty / faculty-acc / bgqos；8 个独占节点，每节点8张MI210，共64个GPU worker。
- 每节点2TiB主机内存，合计16TiB；3天运行时限，允许Slurm重排队。gtqos的总作业内存上限512GiB不适合这套原版CPU-offload并行配置。
- 不同episode并行；同episode所有shots顺序生成，保留官方HPS/CLIP筛选及视觉记忆。每个episode独立输出目录，禁止混用记忆。
- 严格阶段门槛：Core100全部通过后进入新增100；累计200全部通过后进入剩余200。共400episodes/2000shots，阶段shots为500/500/1000。失败不会静默放行下一阶段。
- 使用已审计StoryMem输入，包括3条修订；原生JSON复制到inputs并冻结hash。生成前不追加global、不改写正文。
- 沿用已测试的832×480、每shot81帧/16fps、40步UniPC、CFG3.5、T2V shift12/M2V shift4、BF16 CPU offload、MI2V LoRA rank128、记忆上限10/fix3和原负向prompt。所有cut为true，保持原生跨shot记忆。
- 每次模型进程启动前校验GPU利用率、VRAM、KFD驻留进程及UUID。各worker独立本地MIOpen缓存和4个物理CPU核；实际GPU使用在分配后检查，不把当前空闲样本当作预留。

## 验证和恢复

CPU预检10项通过：全部输入hash、8进程互斥领取与重试、严格阶段阻挡、任务归属、官方参数解析、模型文件存在、完整解码/错误帧数拒绝、已有完整4shot输出的整体验证和冻结代码hash。最终预检7.242秒；复用已有206117/node306空闲CPU60–63。历史输出只用于验证器检查，没有复用为本次生成结果。

检查历史真实日志后，验证器对齐了save_video输入的批维度(1,3,81,480,832)，并以原4shot日志/图像/视频验证。未改变生成模型代码、权重、筛选或采样逻辑。所有新代码及已测试StoryMem生成代码保存在本任务目录/source_snapshot。

每条结果要求模型进程成功、原始张量有限、所有shot完整81帧解码、16fps/832×480、完整拼接和记忆仅来自本episode前面镜头。成功结果发布到videos/<episode_id>/，含原生文件名、ShotN.mp4映射、episode.mp4、接触表和校验记录。

失败尝试保留在attempts/；每episode最多2次失败尝试。重排队后保留完成结果，未完成episode从独立新attempt重做；已验证完成但来不及发布状态的结果先复核hash再恢复。任务状态以queue.json为准；complete.json只在全部400完成后创建。

本次准备/排队新增API调用0、计费tokens0、API USD0；集群GPU/内存/存储费用未取得。尚未开始本批GPU生成，不声明64卡吞吐或完整运行时间已经实测。

## 文件与查看

- submission.json：实际提交记录；submit.sbatch：8节点批处理脚本。
- scheduler_status.json：最近队列快照；queue.json：episode级执行状态。
- preflight.json：通过的CPU集成检查；manifest.json：冻结输入与代码/设置。
- logs/slurm-208465.log：分配后运行日志；workers/、launches/记录实际节点/GPU/CPU。
- 查看调度：squeue --start -j 208465；查看进度：vace/bin/python campaign.py status。
