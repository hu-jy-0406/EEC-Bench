# 视频 API 选型与400条预算（2026-09-22）

状态：价格/接口文档调研，未提交视频生成调用，未生成新的400条适配输入。用户认为 Seedance 2.5 太贵，希望选择与现有 HoloCine 等模型更适合比较的、支持多镜头的商业 API。原先暂定的 Seedance 2.5 不再作为首选。当前推荐候选是 Seedance 1.0 Pro Fast；实际能力与 HoloCine 的差距未经同输入实验验证。

## 冻结数据与预算口径

读取 `EECBench/experiments/source_video_priority_20260921/generation_queue_400.jsonl` 得到：

|累计子集|20秒 / 4 shots|30秒 / 6 shots|40秒 / 8 shots|总秒数|
|---|---:|---:|---:|---:|
|100|60|30|10|2500|
|200|120|60|20|5000|
|400|240|120|40|10000|

以下均为 USD、每个请求生成一个样本、保留每 shot 5秒的基础视频生成预算；不含税、额外失败/重生成、源素材制作、GPU租赁或 UEC-Bench 下游评测费用。不是实付账单。账户实际价格和返回的 usage 优先。

## 候选与成本

|模型 / 服务|设定|400条基础费用估计|接口长度限制|
|---|---|---:|---|
|Seedance 1.0 Pro Fast / fal|480p、16:9|约97–101美元|2–12秒|
|Seedance 1.0 Pro Fast / fal|720p、16:9|约206–216美元|2–12秒|
|Seedance 1.5 Pro / fal|480p、关闭音频|约117–121美元|4–12秒|
|Kling 3.0 Standard / fal|关闭音频|840美元|3–15秒，支持结构化 multi_prompt|
|Seedance 2.5 / BytePlus 官方|480p、纯文本输入|约1040–1100美元|4–30秒；40秒方案未验证|
|Seedance 2.5 / BytePlus 官方|720p、纯文本输入|约2311美元|同上|

Seedance 1.0 Pro Fast 的公开价格为1美元/百万视频 tokens。计算式为 `width * height * fps * duration / 1024 * rate / 1e6`。以864×480、24fps、10000秒计算：97.2百万视频 tokens / 97.2美元；若实际编码尺寸为864×496则100.44百万 / 100.44美元。720p按1248×704至1280×720估计为205.92–216百万 / 205.92–216美元。尺寸区间用于估算，不代表已测得该 API 的实际编码输出。

Seedance 1.5 Pro 关闭音频价格为1.2美元/百万视频 tokens：同样480p尺寸假设约116.64–120.528美元。Kling Standard 关闭音频为0.084美元/秒。

Seedance 2.5 官方无视频输入价格10.7美元/百万视频 tokens；以480p864×496计算100.44百万 / 1074.708美元，720p1280×720计算216百万 / 2311.2美元。该行是假设10,000秒纯T2V分段输出的量价估计；延长若计费输入视频或重复输出前缀，需要另外加上相应时长，不能视为已验证的完整40秒连续生成报价。fal 的2.5挂牌价是21.4美元/百万视频 tokens，不能与 BytePlus 官方单价混用。

给 Fast 480p 的建议准备金为约120美元（约20%额外生成余量），100/200/400累计基础预算分别约25/50/100美元。Fast 720p建议准备约250–260美元。额外余量不是测得的失败率，也不表示允许按生成质量反复挑选结果。

## 多镜头与完整 episode 的区别

Seedance 1.0官方技术报告/主页确认原生多镜头能力；Fast接口是较便宜的1.0系列候选，但其精确切换时间、镜头遵循程度和实体连续性仍需试跑。不能用模型系列的宣传代替对当前端点的实测。

保留5秒/shot时，Fast可以尝试两镜头组成一个10秒请求：20/30/40秒episode分别需要2/3/4次，共1000次请求。不会因这种分组增加目标生成秒数，但独立请求间没有原生的整段联合生成上下文。仅拼接不能证明跨组身份/场景连续。给后段补充指代、使用生成帧作为I2V条件、或者视频延长都需要单独明确协议，不能静默改变输入条件。尤其不能把整段4/6/8镜头压缩到10–12秒，或删除镜头以节省费用。

Kling的15秒结构化多镜头接口在保留时长时也需要分组：20=10+10，30=15+15，40=15+15+10，共840次请求。它的成本高于Fast，但镜头输入结构更明确。上述分组均为方案，尚未实际采用或生成适配文件。

若要求每条20–40秒一次性联合生成，Fast/1.5/Kling这些端点不能原样满足。选择低价候选前必须接受并冻结分组或递归条件协议，保存原始 episode/shot ID、entity schedule和所有新增条件的来源，并在论文中披露。不能宣称价格便宜且同时保持与HoloCine完全相同的上下文能力。

Seedance Lite 的 fal 页面当前明确标记弃用并将请求重定向至Pro Fast，因此不能使用Lite名称提交后仍将结果标为Lite。

当前缺少新服务凭据，未发生外部生成调用（0调用，实际生成费用0美元）。待选型和分组策略明确后，先做小规模可行性试验，再构造完整400条适配输入；原始prompts和contracts保持不变。

## 核对来源

- Seedance 1.0原生多镜头与技术报告入口：https://seed.bytedance.com/en/seedance
- Fast当前价格：https://fal.ai/models/fal-ai/bytedance/seedance/v1/pro/fast/text-to-video
- Fast输入schema：https://fal.ai/models/fal-ai/bytedance/seedance/v1/pro/fast/text-to-video/api
- Seedance 1.5价格、音频开关与长度：https://fal.ai/models/fal-ai/bytedance/seedance/v1.5/pro/text-to-video
- BytePlus计费公式/1.x示例：https://docs.byteplus.com/docs/ModelArk/1099320 （搜索索引可读，当前打开重定向至JS页面）
- BytePlus 2.5当前官方价格：https://ai.byteplus.com/en
- fal 2.5计费公式与尺寸示例：https://fal.ai/models/bytedance/seedance-2.5/text-to-video
- Kling 3 Standard价格：https://fal.ai/models/fal-ai/kling-video/v3/standard/text-to-video
- Kling结构化多镜头schema：https://fal.ai/models/fal-ai/kling-video/v3/standard/text-to-video/api
- Lite弃用/重定向状态：https://fal.ai/models/fal-ai/bytedance/seedance/v1/lite/text-to-video

后续选型更新：用户要求依据同类benchmark实际测过的模型选择；见 `video-api-benchmark-evidence-20260922.md`。Fast仅为低价候选，未确认为正式第四模型。
