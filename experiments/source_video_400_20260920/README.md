# 400 条源视频多镜头 prompt 候选集

已完成，最终全量审计和导出文件检查均通过。SF20K/MuSS各200条；4/6/8镜头分别240/120/40条；每镜头目标5秒。共2000个逐镜头prompt，保留对应源片裁剪和证据。

- [浏览候选与源片](deliverables/review_400.html)
- [筛选表](deliverables/review_400.csv)
- [完整数据JSONL](deliverables/candidates_400.jsonl)
- [完整结果与限制](REPORT.md)
- [筛选说明](REVIEW_GUIDE.md)
- [最终审计](deliverables/final_audit.json)

交付为400条自动审核候选，供用户筛选300条；尚未完成人工选择或生成模型评测。已排除识别出的广告/片尾区间并完成独立窗口审核，不声称逐帧人工无广告认证。浏览页和source_clips目录需一起保留。
