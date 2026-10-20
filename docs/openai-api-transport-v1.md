# Independent OpenAI API transport

Set `EECBENCH_CODEX_BACKEND=api` to route pipeline model stages through the
Responses API instead of the locally logged-in Codex CLI. The API shim sends
only the stage prompt, stage JSON payload, attached original images, requested
reasoning effort and JSON schema. It does not send Codex system instructions,
desktop-task context, local skills or tool access.

The default API model is `gpt-6-luna`; set `EECBENCH_API_MODEL` only for an
explicit alternative. The existing `cli` mode remains the default and uses the
current Codex CLI login unchanged.

Create the private key file outside the repository with owner-only permissions:

```bash
mkdir -p /vast/users/guangyi.chen/causal_group/jinyuan.hu/.config/eecbench
chmod 700 /vast/users/guangyi.chen/causal_group/jinyuan.hu/.config/eecbench
vim /vast/users/guangyi.chen/causal_group/jinyuan.hu/.config/eecbench/openai.key
chmod 600 /vast/users/guangyi.chen/causal_group/jinyuan.hu/.config/eecbench/openai.key
```

The file contains exactly the API key on one line. Do not put it in the repo,
shell history, a command argument or Codex CLI login storage.

Launch a normal pipeline command through:

```bash
EECBench/scripts/openai_api_env.sh <existing-pipeline-command>
```

Switch back by running the same command normally, or explicitly setting
`EECBENCH_CODEX_BACKEND=cli`.
