# HoloCine configurable long text context: static execution-path review

Reviewed source: official checkout commit `0a7630ba448e13ddc7b872638b578e5618208c45` under `EECBench/experiments/generation_feasibility_20260921/repos/HoloCine`. No shared source or default was changed by this review. The CPU script has been written but not executed by this reviewer.

## Finding

The active 512-token truncation is the prompter/tokenizer configuration. No further fixed 512-element truncation or learned absolute-position table was found in the active T5, text projection, cross-attention or shot-mask path. Therefore increasing the scoped prompter and tokenizer length is structurally plausible; this is not evidence that pretrained long-context quality has been validated. The final requested target is the measured maximum across all400 original Wan/StoryMem-shared global-plus-shot inputs, not a fixed1024 cap. The test defaults to the historical observed maximum1215; the operator must supply the newly audited maximum with `--text-len`.

## Exact execution path

Paths below are relative to the official checkout.

1. `diffsynth/pipelines/wan_video_holocine.py:38` instantiates `WanPrompter` with its default length. `diffsynth/prompters/wan_prompter.py:98` defaults to `text_len=512`; line106 transfers that value into `HuggingfaceTokenizer.seq_len`. Its lines57–62 use `padding=max_length`, `truncation=True`, and `max_length=self.seq_len`. A scoped override must affect both current object values, or construct the prompter/tokenizer with the requested length from the outset.
2. Pipeline units select `WanVideoUnit_PromptEmbedder` at line53. Its line560 calls `encode_prompt`, whose lines169–174 encode the entire hierarchical prompt; lines180–199 derive global and shot spans from the retained token offsets. Truncation can erase later shots before mask construction.
3. `wan_prompter.py:208` calls the text encoder. `diffsynth/models/wan_video_text_encoder.py:245–254` derives sequence dimensions from input IDs. `T5SelfAttention` lines139–143 derives relative positional bias from `x.size(1)`. `T5RelativeEmbedding` lines158–169 dynamically constructs the full position matrix; its bucket table is a relative-distance table, not a 512-position absolute embedding. Larger distances share buckets by design; that is not a sequence-length truncation.
4. `diffsynth/pipelines/wan_video_holocine.py:1123` applies `dit.text_embedding`. `diffsynth/models/wan_video_dit.py:568–572` is a feature-dimension MLP; it does not shorten the text dimension.
5. `wan_video_holocine.py:1185–1241` builds window cross-attention masks. Line1189 derives `L_text_ctx=context.shape[1]-num_img_tokens`; global/shot tables, padding flags, and bias tensors all use that dynamic length. The mask includes tokens beyond512 when retained spans reach them.
6. `wan_video_holocine.py:1292` sends the mask and context to the DiT block. `wan_video_dit.py:484` calls `CrossAttention`; its lines423–436 project all supplied text rows. `AttentionModule` lines366–368 forwards the mask to official `flash_attention`. Its lines78–85 use PyTorch scaled-dot-product attention directly for a masked call, with dynamic query/key lengths. This branch is distinct from sparse inter-shot video self-attention.

## Other length-related code

- `wan_prompter.py:320–328`: the unused-by-default separate encoder concatenates embeddings and truncates to `self.text_len`, so it is not an independent workaround. A configured larger `self.text_len` also raises that cap.
- `wan_video_dit.py:753`: another literal `text_len:512` appears in `WanModelStateDictConverter.from_diffusers` configuration for one particular historical hash. It is not a forward-path slice; the active `WanModel.__init__` at lines530–551 has no `text_len` argument. Do not blindly rewrite that mapping as though it were a second runtime truncation.
- `wan_video_dit.py:289,297,308`: `end=1024` belongs to video/shot rotary frequency preparation, not the text-encoder context limit.
- The original mask uses `g1+1` and `s1+1` slicing although `encode_prompt` emits end-exclusive spans. This existing boundary convention is preserved by the proposed validation and must not be silently altered under a length-only change.
- The mask code catches exceptions and falls back to no mask at lines1243–1249. The structural test executes the exact try-body but lets errors fail the test, preventing a false pass via that fallback.

## Validation script and limits

`test_dynamic_context.py` directly imports the official standalone T5 module and executes unchanged AST definitions for official `CrossAttention`, `AttentionModule`, `RMSNorm`, and `flash_attention`. It extracts and executes the actual inline mask try-body rather than replacing it with a handwritten approximation. Only dimensions, random initialization, input IDs and synthetic shot spans are test fixtures.

On an allocated CPU node, test both512 and the selected target length. Verify dynamic T5 outputs/relative biases, exact512-prefix bias and mask equivalence, masks retaining token700 and `max(1024,text_len-24)` for their designated shots, and actual attention output sensitivity to those tokens only in the allowed shots. The target must exceed1024 so both former512 and candidate1024 boundaries are crossed. No pretrained checkpoints, GPU kernels or video quality are tested. A passing result must be described as structural validation, not a completed HoloCine generation test.

The output defaults to `dynamic_context_validation.json` with machine-readable `status: "pass"`, baseline and target lengths, tested token indices, source hashes and measurements. `--output` can direct it into the final original-input task directory; this intermediate directory name does not select the context length.

Suggested command, after applying the normal allocation/CPU-affinity policy:

```bash
python EECBench/experiments/holocine_text1024_20260922/test_dynamic_context.py --threads 1 --text-len 1215 --output /absolute/path/to/final/task/dynamic_context_validation.json
```
