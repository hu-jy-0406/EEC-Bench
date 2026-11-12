# Switch of the model API to OpenRouter (2026-11-11)

Times are Dubai time. Owner: "先暂停一下，需要改一下api调用" ... "我要换成openrouter api，我目前有api key，告诉我怎么配置".

## Configuration

- Key: one line in `/vast/users/guangyi.chen/causal_group/jinyuan.hu/.config/eecbench/openrouter.key` (mode 600),
  written by the owner with vim; never printed, logged or put on a command line.
- `scripts/openrouter_env.sh <command>`: like `openai_api_env.sh`, sets `EECBENCH_API_PROVIDER=openrouter`.
  `scripts/openai_api_env.sh` keeps direct OpenAI.
- `scripts/eec_api_codex_shim.py`: the same Responses API request goes to `https://openrouter.ai/api/v1/responses`
  with model `openai/<model>` and `provider: {order: [openai], allow_fallbacks: false, require_parameters: true}`
  (only OpenAI serves the call, only an endpoint that supports every parameter). OpenRouter's Responses API is
  stateless and rejects `previous_response_id`; the shim refuses a continuation and the repair loop
  (`vl_vv_repair_loop.py`) goes straight to its existing full resend. The billed cost OpenRouter returns is recorded
  as `usage.cost_usd` in every call's status. Error text keeps the "OpenAI API <code>" prefix that the transient
  retry matches. Tests `tests/test_openrouter_transport.py`.

## Smoke test (`smoke/`, node 304, 15:0x)

Three calls with `openai/gpt-6-luna`, effort low, one labelled keyframe, strict JSON schema: all valid outputs.
Prompt caching works: the same developer-role request with a `prompt_cache_key` sent twice had 1,183 of 1,186 input
tokens cached the second time.

Billed amounts: USD 0.000156925 (1,172 input, 21 output), 0.000158675 (1,186 / 21, cache miss), 0.00002263
(1,186 with 1,183 cached / 21). They match uncached input at USD 0.125 per million (the listed cache-write price;
direct OpenAI standard price 0.10), cached input 0.01 and output 0.50. At the full first-200 C run's token mix this is
about 18% more than the direct standard price (before any OpenRouter credit fee, which is outside the per-call cost).

## Cut-off replies (16:4x Dubai)

In the 40-video validation one matching call (priority_048__wan21, `case/global_match_v2/attempts/attempt_00`)
returned a reply cut off mid-string after 768 output tokens, so the stage failed on invalid JSON. Over all 2,885
OpenRouter calls of the run there is no output cap (maximum 12,020 output tokens; 919 calls above 768), so this was a
one-off. The shim now writes `api_response_meta.json` (id, status, incomplete_details) and raises "OpenAI API
incomplete (...)" when the status is not `completed` or the output is not complete JSON; that prefix is in
`run_wedetect_shot_entities.TRANSIENT_API_ERROR`, so the existing transport retry (10/30/60 s) resends the call.
Test `test_a_cut_off_response_is_a_retryable_transport_failure`; 347 VL/VV and transport tests pass.
