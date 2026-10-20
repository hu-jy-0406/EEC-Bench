# Wan2.2 原始 prompt 可用性检查（2026-09-21）

当前原始 per-shot 英文文本可以直接作为 Wan2.2-T2V-A14B 的单次文本输入：2,000 个 shot 均未超过当前 512-token 限制。正式逐 shot 生成前，建议补齐部分依赖前文的实体/场景描述。长度兼容不代表每条文本已经自包含，也不代表跨镜头身份一致性有保证。

## 实测长度

使用本地已测试 Wan2.2 的 wan/modules/tokenizers.py::HuggingfaceTokenizer、本地 google/umt5-xxl 文件、生产路径相同的 whitespace 清洗和 add_special_tokens=True。关闭截断计算长度，再逐项比较生产截断设置下的实际 token IDs；两者全部一致。Transformers 5.5.4，实际类 T5Tokenizer。

| 子集 | Episode | Shot | 原始单 shot 平均 tokens | 最长 | 超过 512 |
|---|---:|---:|---:|---:|---:|
| Core100 | 100 | 500 | 129.75 | 225 | 0 |
| Priority200（累计） | 200 | 1,000 | 128.305 | 227 | 0 |
| Full400 | 400 | 2,000 | 125.3055 | 227 | 0 |

Full400 范围 62–227，包含特殊 token。额外诊断 global_prompt + 单个 shot 最长 281，也无截断；这不是推荐的正式适配方式。Global 中可能有其他 shot 的动作顺序，而且人物定义也可能只存在于前面的 per-shot 文本。不能仅凭长度通过就把整段 global 无条件拼入每个 shot。

这里的 512 是单次生成输入限制。当前 Wan 基线逐 shot 独立生成后按顺序拼接；不是把整集所有 shot 文本一次传入并期望模型精确执行分镜。

## 已核实的上下文依赖例子

Core100 第一条 74Od5-Fmf60_s00006_n4_clean_v2：Shot2 定义 Suited man 的 wavy brown hair、dark suit、pale pink striped shirt、red tie、matching pocket square；Shot3 只称 Suited man，并描述站在桌后、做手势等动作，没有重复完整外观。Global 只有四镜头剧情概述，也没有这些外观定义。独立调用 Shot3 时，Wan 不会自动获得 Shot2 的文字。

建议的最小适配：保留本 shot 原文和镜头风格；从原始 episode prompt 中提取、展开当前 shot 确实适用的已有实体/场景定义，并解析指代。不要把仅存在于源视频元数据的事实升级为要求，不引入新实体，不将其他 shot 动作或其他场景实体带入当前 shot，不通过额外可见性要求改变 entity schedule。最终输入重新检查 512 限制并保存原文到适配文本的对应关系。此建议尚未实施。

只抽查了上下文语义，未逐条完成自包含性审查。CSV 的词汇标记（same/remain 等）只是候选线索，1,153 个标记不能解释为 1,153 个错误或实际需要修改的 shot。

## 产物、资源及边界

- audit.py：可复现脚本；audit.json：长度、逐项检查、文件哈希和运行信息；per_shot.csv：全部 2,000 行。
- 原始数据 SHA256：e124ff566333309b1c1a667408b8aaabb506f4ae9f224253f9f2d6e200c08fb9，检查前后未变。
- 复用 guangyi.chen 已有 allocation 206117 的 node306；运行前核实低负载和 CPU60 空闲，单 CPU affinity、nice10、禁用 Torch/TF/并行分词和联网下载。脚本内部耗时 14.630 秒，不是生成耗时。
- 0 模型/API 调用，0 计费 API tokens，API 费用 USD0；表中的 token 数是离线输入长度。无 GPU、无模型权重加载、新分配或视频生成。
- 未修改原始 prompt、冻结的 100/200/400 队列、生成配置或评测流程。尚未编译正式 entity schedule。

官方接口/限制参考：[generate.py](https://github.com/Wan-Video/Wan2.2/blob/main/generate.py)、[shared_config.py](https://github.com/Wan-Video/Wan2.2/blob/main/wan/configs/shared_config.py)。审计以本地实际部署的代码及 tokenizer 为准，其哈希见 audit.json。
