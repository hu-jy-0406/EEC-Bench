# Qwen3-VL-Flash setup for EntityBench / EEC-Bench

This setup uses Alibaba Cloud Model Studio's OpenAI-compatible API and keeps
the private key outside every Git repository.

## Create an API key

1. Sign in to Alibaba Cloud Model Studio and activate the pay-as-you-go
   service.
2. Select the international Singapore region. API keys and Base URLs are
   region-specific.
3. Open the API Key management page and create a standard Model Studio API
   key for the workspace that can call `qwen3-vl-flash`.
4. On this server, open the pre-created private file:

   ```bash
   vim /vast/users/guangyi.chen/causal_group/jinyuan.hu/.config/eecbench/qwen.key
   ```

5. Paste only the API key on the first line, save, and quit. Do not add
   `export`, quotes, or comments. The file mode is already `600`.

Never paste the key into chat, a shell command line, a log, or a repository.

Official references:

- API key creation: <https://help.aliyun.com/zh/model-studio/get-api-key>
- Regional Base URLs: <https://help.aliyun.com/zh/model-studio/base-url>
- Qwen3-VL-Flash pricing: <https://help.aliyun.com/zh/model-studio/model-pricing>

## Validate the key

From the outer EEC-Bench workspace:

```bash
EECBench/scripts/qwen_env.sh --check
```

The check performs one tiny real chat-completion request. A successful result
prints the model name and `{"status":"ok"}`; it never prints the key.

## Use it

Load Qwen into the current Bash shell:

```bash
source EECBench/scripts/qwen_env.sh
```

Or scope the secret to one command:

```bash
EECBench/scripts/qwen_env.sh \
  /vast/users/guangyi.chen/anaconda3/envs/vace/bin/python \
  EECBench/eval/evaluate_benchmark.py --help
```

The loader selects:

- model: `qwen3-vl-flash`;
- endpoint: `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`;
- provider: Alibaba Cloud Model Studio, OpenAI-compatible API;
- three concurrent streams for the one key;
- a default per-process safety budget of USD 1;
- audited Singapore prices of USD 0.05/M input tokens and
  USD 0.40/M output tokens.

Override the safety budget only for an intentional larger run:

```bash
EECBENCH_QWEN_BUDGET_USD=5 EECBench/scripts/qwen_env.sh <command> [args...]
```

For a Beijing-region key, set `EECBENCH_QWEN_BASE_URL`,
`EECBENCH_QWEN_INPUT_USD_PER_MILLION`, and
`EECBENCH_QWEN_OUTPUT_USD_PER_MILLION` to the matching Beijing values before
loading the script. Do not mix keys and endpoints from different regions.

The cluster proxy currently denies HTTPS CONNECT to Alibaba Cloud Model Studio
endpoints, while direct outbound connections time out. If `--check` reports a
proxy failure, the key has not been tested. Ask the cluster network
administrator to allow `dashscope-intl.aliyuncs.com:443`. If using Alibaba
Cloud's recommended workspace-specific endpoint, allow and set
`{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com:443` instead.

## Comparability warning

Qwen exercises the same EntityBench code paths, prompts, images, and JSON
schemas, but it is a different judge. Its scores are not directly comparable
to the paper's Gemini-judged table until judge agreement and ranking stability
have been measured on a shared calibration set.
