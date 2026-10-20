# 商业视频API：同类benchmark的实测依据（2026-09-22）

用户要求依据同类benchmark实际测过的商业生成模型重新选型。未提交付费视频生成，未构造正式400条商业API适配输入。前一版低价Fast建议不是最终模型决定。

|工作|定位|实际评测的商业模型|
|---|---|---|
|MSVBench|直接多镜头benchmark|Sora2、Veo3.1；Table3/4/7，未细分Veo的Fast/Quality SKU|
|FilmBench|电影语言/连续性；大量多镜头prompt|T2V：Seedance2.0、HappyHorse1.1/1.0、Kling3.0/3.0Omni、Veo3.1、GrokImagineVideo、ViduQ3Pro、Hailuo2.3。R2V：Seedance2.0、HappyHorse1.1/1.0、Kling3.0Omni、Veo3.1、GrokImagineVideo、ViduQ2Pro|
|AVGen-Bench|邻近的文本到音视频benchmark，不是专门长多镜头benchmark|Veo3.1Fast/Quality、Sora2、Wan2.6、Kling2.6、Seedance1.5Pro；v1论文Table2。当前官方仓库另增Seedance2.0，不与v1混淆|
|EntityBench|长程多镜头实体一致性|主实验无商业生成API；HoloCine、CineTrans、StoryMem和作者EntityMem|

MSVBench正文/附录中检查到的设置没有提供足够复现Veo整段拼接、扩展或逐shot调用的细节，不能从结果表推断其支持原生20–40秒联合生成。FilmBench说明使用官方API/公开权重默认设置、每prompt一个视频；这不等于当前4/6/8shot×5秒协议。AVGen-Bench明确多数模型10秒、Veo8秒、Sora12秒、Wan2.2管线5秒，大多数720p、MOVA360p。它提供的是披露原生限制差异的先例，不是本项目可以任意改时长的授权。

ViStoryBench主要评测故事图像可视化，不能把GPT4o/NanoBanana图像模型误列为视频API。FilmBench未明确的KlingStandard/Pro及VeoFast/Quality档位不能自行补全。

修订建议：论文可比性优先则Veo3.1列第一梯队，考虑预算可选Fast（AVGen明确测过Fast）；低成本且有论文实测依据则Seedance1.5Pro优于仅按价格推荐的1.0ProFast；结构化分镜输入则Kling3.0有FilmBench依据，但具体SKU需固定。不得宣称这些模型和HoloCine质量接近，实体/空间/出现约束上的能力差距需本项目实测。

## Veo预算及限制

当前Gemini API公开720p价格：Standard音视频0.40美元/秒，Fast0.10美元/秒，Lite0.05美元/秒。三者不能混标。普通生成4/6/8秒，不支持5秒；参考图/extension及1080p等模式要求8秒。不能将本数据10000秒直接乘价格当作可执行报价。

仅作逐shot独立生成的预算场景：2000shot×6秒=12000付费秒，Fast约1200美元，Standard约4800美元；2000shot×8秒=16000秒，Fast约1600美元，Standard约6400美元。均为一遍、不含税/重生成/评测，尚未采用该协议。Fast按8秒计算100/200/400累计约400/800/1600美元。延长/参考条件路线另定协议和费用；不能把逐shot预算冒充多镜头联合生成报价。不能静默裁掉动作终态、缩短镜头或修改原始prompts/contracts。

本次0个付费视频生成调用，生成费用0美元。正式适配与试跑仍待选型/协议明确。

## 原始来源

- MSVBench论文/Table3：https://arxiv.org/html/2602.23969v1#S4
- MSVBench正式出版：https://aclanthology.org/2026.findings-acl.1203/
- MSVBench代码：https://github.com/HITsz-TMG/MSVBench
- FilmBench§5.1和Tables7/8：https://arxiv.org/html/2607.24241v1
- FilmBench工具：https://github.com/Neo-yk/FilmOps
- AVGen论文§4.1/Table2：https://arxiv.org/html/2604.08540v1
- AVGen当前榜单：https://github.com/microsoft/AVGen-Bench
- EntityBench主实验：https://arxiv.org/html/2605.15199v1#S5.SS1
- Google当前价格：https://ai.google.dev/gemini-api/docs/pricing#veo-3.1
- Google输入限制：https://ai.google.dev/gemini-api/docs/veo

此前价格比较见video-api-budget-20260922.md；Fast未确认为正式第四模型。


## 追加：global与per-shot输入的代码/数据核查

2026-09-22检查公开仓库树和少量实际prompt，未运行下载的代码或提交生成调用。

- MSVBench仓库commit309318bf29594fe21a487d4fd78284faef0d777b：主要是评测代码和依赖；非vendor根层包括MSVBench.py/sh、Tools/gemini_api.py等。该Gemini工具用于文本/图像/视频理解和图像生成，没有generate_videos。论文§3.1确有全局人物/环境、场景、逐shot描述/镜头指令；附录A的prompt是评价器prompt，并非Veo生成适配模板。未找到Veo专用合并、分段、记忆或延长实现。
- AVGen-Bench仓库commit1049eabac472d479fe5feeb1ee202961f8e0982a：prompts/movie_trailer.json有20项，单项字段content/style/prompt；首例REDLINE PROTOCOL的一个prompt字符串包含整体预告片要求和四个编号shot。generation/runner.py的127/137行读取并保存item.prompt，189行将task.prompt交给video_generation；其他字段作为额外kwargs传递，不应断言style另被拼入文本。create_client当前没有Veo分支，所以这证明已发布prompt布局与通用runner行为，不能冒充已复现Veo专用调用。论文§4.1明确Veo输出8秒：单个短视频容纳多镜头是与其公开数据一致的理解，不是每个shot必须8秒。
- FilmBench：公开filmbench_videos.csv/data viewer中的Veo3.1 t2v-1条目，zh_prompt是一个包含镜头1至4的字符串，场景和人物信息写在分镜段落中。后补的filmbench_prompts_en.csv有1169项，字段uid/task/movie_type/en_prompt/reference_url，没有单独global_prompt和shots数组。英文表在2026-08-02新增；README说明7月31日修正过一批视频manifest的prompt错配。因此可以核实当前发布的脚本文本布局，但不能保证英文表就是论文实验时Veo原始请求，也不能把修正后manifest当作原始请求日志。FilmOps仓库commitad60f5b0a9481d3c260793d190e9068058b4219e主要提供评测operator，没有发现Veo生成adapter。

可借鉴的序列化方式是把整体背景/人物设定与按顺序的Shot1...ShotN放在同一prompt字符串。Veo官方参数也是单一prompt，而不是HoloCine式global_caption/shot_captions双通道。具体Global/Shot标题属于我们的表示选择，不是论文强制格式。

重要澄清：4/6/8秒是Veo普通调用的总clip长度，不是内部每个镜头必须占满这么久。此前2000shot×6/8秒的1200/1600美元只是逐shot独立方案的估计，不是上述benchmark已验证的通用做法。一次8秒生成全部分镜可让400请求基础费约320美元（Fast720p0.10美元/秒），但会改变本项目20/30/40秒及每shot5秒要求，不能直接采用或声称等价。全局与局部文字合并的问题已有参考，完整时长/切镜/实体出现约束仍需单独验证。

直接证据：
- https://github.com/microsoft/AVGen-Bench/blob/1049eabac472d479fe5feeb1ee202961f8e0982a/prompts/movie_trailer.json
- https://github.com/microsoft/AVGen-Bench/blob/1049eabac472d479fe5feeb1ee202961f8e0982a/generation/runner.py#L124-L139
- https://github.com/microsoft/AVGen-Bench/blob/1049eabac472d479fe5feeb1ee202961f8e0982a/generation/runner.py#L180-L192
- https://huggingface.co/datasets/skylenage/FilmBench
- https://huggingface.co/datasets/skylenage/FilmBench/resolve/main/filmbench_prompts_en.csv
- https://arxiv.org/html/2602.23969v1#S3.SS1
- https://arxiv.org/html/2604.08540v1#S4.SS1
