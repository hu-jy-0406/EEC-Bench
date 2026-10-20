# 简化流程整合验证

整合入口：`EECBench/scripts/run_gs_integrated.py`。从新检测开始，到单次 B 分类结束。

- 7 项整合测试通过：调用顺序、GPU guard、失败停止、token 统计、原框接口、拒绝覆盖、单次 B 终点。
- 8 项单次 B 测试通过。
- 使用已有候选框前端作为离线测试数据，输入内容完全一致；12 张原图、Shot1/Shot3 各19/21个静态实体可进入跨 shot Eval。
- 动静判断与融合函数 AST 和原实现一致，只更换入口路径。
- Skill 校验和计划模式检查通过。

详见 `audit.json` 和 `check_interfaces.py`。本验证没有新模型调用/token/GPU工作，未进行完整新推理，也没有新分数或性能结论。
