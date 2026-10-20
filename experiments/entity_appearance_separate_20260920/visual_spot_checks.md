# 原图人工抽查记录

这只是少量抽查，不是带标注测试集，未用来改 prompt 或重跑取得更好分数。

1. Study2/ge0017 笔组：派生 crop 明确包含多支笔，而不是只选一支；原始候选框仍保留在 input.json。
2. Study2/ge0004 人物：对照 shot1_f0、shot1_f72、shot3_f72、shot3_f96，原图可见 Shot1 更贴身的深色裤装、浅色接缝与门襟；Shot3 腰髋部出现较宽松的纵向前褶。支持 Codex 对裤装外观改变的定性描述，未校准其75分的绝对数值。人物的发髻、上衣和主体比例仍相近。见 study2_person.jpg。
3. Study3/ge0003 台灯：对照 shot1_f0、shot1_f120、shot3_f0、shot3_f120，灯罩和底座由黑色变成白色，金属弯杆仍为黄铜色，镜头内各自稳定。这是观察到的跨shot外观变化，可用于核对待返回的模型判定；没有把这条结论提供给评分调用。见 study3_lamp.jpg。

人工抽查待复核项：Study2/ge0009植物的扣分理由主要涉及盆体，但花盆另有ge0016实体，存在同一花盆变化重复归因的风险。尚无精确实体范围标注，故标为potential_scope_leakage，而非已确认误报。本轮保留全部原始分数，没有见到结果后改prompt/重跑。详见manual_review_flags.json及visual_spot_checks.md。
