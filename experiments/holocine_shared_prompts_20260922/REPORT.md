# HoloCine改用Wan2.2 / StoryMem共用未压缩输入

用户明确选择：用压缩前、与Wan2.2和StoryMem一致的prompt；按实际最大token数设置默认上限。

完成400episodes / 2,000shots。每条shot逐字等于当前Wan有效输入input_queue_400.v2.jsonl中的wan_prompt_en及StoryMem的video_prompts，包含既有已验证上下文补全；global逐字等于当前共同摘要。仅加入HoloCine原生分隔标记，没有压缩/重写/新别名。所有原始contract、alignment_contract、schedule及64,724claims保持不变。

完整episode实际UMT5长度：最短472，最长1519，包括分隔标记与EOS。全400统一配置prompter.text_len=1519、tokenizer.seq_len=1519，所有输入完整、无截断、所有shot span保留。最长episode：JWUrJ-zH7fw_s00012_n8_clean_v3_alt8。按镜头数统计：{"4": {"count": 240, "minimum": 472, "maximum": 1107}, "6": {"count": 120, "minimum": 607, "maximum": 1354}, "8": {"count": 40, "minimum": 905, "maximum": 1519}}。

以前报告的1215是更早source正文拼接的最大值，不包含Wan/StoryMem既有上下文补全；917属于压缩候选。它们都不作为本次共享输入的配置依据。较早241/159分组及1024压缩版方案保留为历史记录，本次全400均通过输入检查。

官方论文报告60秒/最多13镜头；已测官网13镜头演示prompt为425tokens，因此多shot本身不意味着超512。当前发布默认512是可配置预处理限制，官方未声明本次加长值的质量验证。模型T5相对位置、CrossAttention和shot mask沿实际sequence长度构造；真实官方代码tiny随机CPU权重的512/1519结构验证通过，含越过512/1024后的token可达性和对应shot隔离。共享checkout保持不变，由text_context.py在本次pipeline实例中显式配置两个长度。

没有运行预训练完整文本encoder/14B视频生成或画质对照；增加文本长度的实际GPU成本与生成质量尚待视频实验。不得把结构和tokenizer检查说成完整视频质量验证。实际模型权重、采样器、视频镜头参数均未改变或启动。

交付：holocine_shared_prompts_contracts_400.zip；deliverables/ready_queue.jsonl；profile.json；input_audit.json；dynamic_context_validation.json；package_validation.json。包内verify_bundle.py已通过完整读回哈希与合同映射校验。新增API调用0、计费API tokens0、API费用USD0（历史压缩费用独立保留）。

官方来源：https://arxiv.org/html/2510.20822v1#S4.SS1 ；https://github.com/yihao-meng/HoloCine#prompt-format ；https://holo-cine.github.io/ 。
