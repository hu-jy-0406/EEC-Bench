# 原始 pipeline 执行结果（纠正报告）

按用户要求，以未人工筛除的 optimization/results.json 和 direct/results.json 为唯一配准结果依据。先前人工排除汽车锚点后的“四组”不属于 pipeline 自动输出，不应作为实验结论。optimization_audited 和此前采用它生成的 comparison/优化顶视图仅为历史人工处理产物，不代表原始运行。

四shot、25实体三维建模完成；Shot1/2/4柱子各6帧有三维几何。

两种方法均输出3组坐标系：{Shot1,Shot3}、{Shot2}、{Shot4}。

优化法：模型选择汽车为Shot1/3锚点，代码接受；1721个有效三维对应进入候选池，以FPS32选择32点拟合。Shot3→Shot1 scale=0.10000000000000002，yaw=-23.771637884712618°，translation=[-0.27870763425071565,0.031099718385754413,0.21177116654088]，selected_solver_success=true，status=numeric_candidate。原始pipeline未排除该配准。尺度落在优化允许下限0.1，作为诊断保留，不人工改判。

柱子配准尝试Shot1/2、Shot1/4、Shot2/4均未得到有效三维点：各180000个原始匹配，分别2216/137/3820个同锚点区域匹配，但置信度及双向一致性联合筛选后均为0，无法拟合。

Codex直接法：Shot3→Shot1 scale=0.68，yaw=160°，translation=[-0.045,0.547,0.21]，模型confidence=low。Shot2和Shot4返回new_group/弃权，未估计变换。

两种方法得到相同分组但显著不同的变换，不等于准确性已验证。没有真实配准ground truth，也未运行最终空间冲突复核/评分。没有人工删除、挑选或替换本报告中的配准结果。

实测720.559870秒；258041tokens，USD2.744650标准API等价估算（非账单），不含此前补检。Holo借卡worker已恢复验证。
