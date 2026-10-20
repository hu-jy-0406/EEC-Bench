# Appearance scoring v6 — selected cost trade-off

用户明确要求允许修改评分规则、不要引入新的核实机制。最终方案完整恢复 compact-v3 模型阶段，只增加本地评分后处理；v4 核实/事件机制与 v5 改写prompt候选均不选用。

## 最终默认

现已接入 `run_gs_integrated.py` 的默认 `temporal_v2 --stop-after full`；两种配准方式均支持。
全局实体表之后自动执行 appearance 准备、DINO、原 compact-v3 Codex、v6 本地汇总。
输出和提前停止规则见 [完整流程接入说明](gs-integrated-appearance-v6.md)。下列独立入口继续可用。

入口 `scripts/gs_entity_appearance_scoring.py`：`prepare` / `score` 原样委托 v3 的 `gs_entity_appearance_minimal.py`，原 `entity_compact_v2.txt`、六字段 schema、Astra/medium、基础角色、全部appearances及每实体一次调用完全不改；`report` 仅读取已完成v3结果，计算新分数并审计输入。没有新核实字段、事件表、额外复核或模型调用。保留v3原有索引/schema校验，不引入v4语义门槛。

令有效属性分为 `s`，先计算原来的 `m=mean(s)`。若最低属性分为0或25（原定义中严重/根本不一致），实体分 `C=min(m,min(s))`；其他情况仍取原均分 `m`。全部null时返回null。这样明显主体变色不能被其他属性100抵消；50/75等局部或中度扣分不被直接升级为实体最低分。没有改动原属性分的含义。

Episode Codex主分为 `100-sqrt(mean((100-C)^2))`，同时报告普通实体均分与未知数量。DINO独立、公式和数值不变。全部计算都在本地，无模型token。模型输出中的旧实体均分与新后处理分均保留；不要把新规则伪称为原模型直接输出的总分。

## 命令

在已检查的现有Slurm allocation内运行CPU/API阶段，不申请新GPU。

```bash
python EECBench/scripts/gs_entity_appearance_scoring.py prepare --source CANONICAL --out COMPACT
python EECBench/scripts/gs_entity_appearance_scoring.py score --runs COMPACT --workers 3
python EECBench/scripts/gs_entity_appearance_scoring.py report --runs COMPACT --out NEW_REPORT_DIRECTORY
```

已有v3输出直接执行最后一步，不需重新调用模型。新canonical来源依旧由原 `gs_entity_appearance.py` 准备appearance和DINO；不依赖历史VLM。report要求新目录、拒绝混入v4/v5响应，保留历史结果不覆盖。

## 本轮结果与真实成本

最终报告 `experiments/entity_appearance_scoring_20260920/REPORT.md`。基于原v3的67次既有模型判断离线重算：Study2主分93.75、普通均分98.1618；Study3主分85.4031、普通均分95.8333。Study3台灯81.25→25，其他实体原均分不变。DINO0.910026/0.911623不变。33项测试及71实体/474appearance完整审计通过。此重算新增0模型调用、0token、$0API。

原v3历史用量429878tokens/$3.389308标准API等价，不是本次新消费或未来账单保证。此轮曾实际测试v5短prompt候选67次，424531tokens/$4.072702（输出17400），但花盆在承认光照贡献不明时仍被打25；不选用该候选，不挑选其单项结果。候选费用作为本次实际验证费用单独记录，不从总账删除。原始证据/源代码/调用均保留在 `experiments/entity_appearance_budget_20260920`。

此前v4相较v3费用多$1.024382，其中缓存折扣减少贡献$0.744192（约73%），无缓存token量/构成差异贡献$0.280190。v4输出18344其实少于v3的19196；不能把30%成本上涨主要归因于事件输出变长。未来同一模型结构仍受随机输出和缓存命中影响，只能承诺本地公式不引入模型负担，不能保证固定美元价格。

## 明确取舍

最终不包含v4消除存疑扣分的能力保证：v3植物/花盆/木桌的少量原始扣分仍保留，未用人工改分或新核实去修正；RMS仍可能放大误判。舍弃事件级诊断和新门槛，换取模型阶段完全回到原精简版。Study2没有设计异常也可能有真实附带生成漂移；不得强制其100分。当前为开发样本离线诊断，不是独立人工校准。
