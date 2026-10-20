# Prompt绑定条件schema：正式修复

已完成。正式入口默认使用OUTPUT_SCHEMA，未改变原prompt、Astra/medium、判断逻辑、身份或评分门槛。

## 原因

旧请求schema只限制字段类型，允许unknown记录填写fact_ids；后处理materialize却拒绝该组合。模型引用不确定候选的情节出处，能通过旧schema却无法通过业务校验。这是输出接口与后处理约束不一致，不是三维配准或简化身份输入导致的错误。

## 修改

- 三个互斥状态的结构化输出：bound必须有prompt ID、facts和自身见证，且没有候选列表；unbound必须没有prompt ID/facts/候选；unknown必须没有确认ID/facts，可保留候选。
- 输出schema与此前已实测的Study4严格schema逐值一致。正式call默认使用它；历史结构SCHEMA和materialize原规则保留。显式传入的alignment/compiler schema继续各自生效。
- API返回后按实际请求schema校验，再记录成功。后续语义或来源校验失败也会记录failed及具体validation_phase，保留原始响应和用量，不自动改字段、重试或增加模型调用。

## 验证

51项相关测试通过，含48种状态/字段组合与既有materialize接受范围的穷举对照、历史兼容、错误见证、其他调用的自定义schema及失败费用保留。初次测试命令缺少tests模块搜索路径，有1个导入错误；修正PYTHONPATH后全部通过，原日志保留，无模型调用发生于该错误。

历史两份Study4失败响应均被新schema拒绝；Study2/3及Study4严格版本合法响应均通过。

正式生产函数（无实验monkeypatch）新跑一次Study4绑定成功：33实体，11bound/12unbound/10unknown；91.132秒，30,991tokens，USD0.418750标准API等价估算。输入28,270、其中缓存0、输出2,721；缓存为输入子集。沿用记录的Astra每百万10/1/50美元计价，非实际账单。CPU/API在既有206117/node306、已检查空闲CPU1–2，GPU隐藏；未新申请资源。

本次11/12/10与先前11/13/9存在一项unbound/unknown波动，不据此宣称模型判断恒定或人工正确性。修复针对结构约束，保留证据/实体校验；没有重新运行其他评分分支。最简身份输入默认未在本次切换。所有task进程结束。

代码：EECBench/scripts/gs_prompt_binding.py；测试：EECBench/tests/test_gs_prompt_binding.py；规范：EECBench/docs/prompt-binding-v1.md。
