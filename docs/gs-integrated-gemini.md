# Gemini 3.5 Flash experimental GS pipeline

`scripts/run_gs_integrated_gemini.py` is an independent entrypoint based on the
current complete Flow1 implementation, including all-entity identity matching,
single presence judgment and spatial evaluation. The original Codex entrypoint
and selected runtime configuration are unchanged.

All six model-bearing stage types use `gemini-3.5-flash`, medium reasoning:
within-shot clustering, isolated motion, initial identity, aligned identity
review, presence, and isolated spatial observations/final relation review.
`run_gs_gemini_stage.py` intercepts only the final model transport; it never
executes Codex. Non-model subprocesses keep the existing execution path.

The existing decision prompts, compact payloads, canonical output schemas,
witness gates, inventory checks, candidate box selection and scoring code are shared. Each
Gemini request has exactly one fresh user message, original image bytes in
attachment order, and no tools or prior conversation. The backend uses Google's
official OpenAI-compatible API, with no implicit retries. Failed or incomplete
responses stop the pipeline and retain their available usage.

Aligned identity review uses `required_identity_group_index_form_v1` for Gemini.
`initial_group_reviews` is an object whose keys are every frozen initial group
ID, dynamically declared in both schema `properties` and `required`, with no
extra keys allowed. Each value is constrained to its fixed zero-based index
(single-value integer enum) in `initial_group_review_rows`. The model fills
these rows with ordinary JSON objects; all original decision/evidence fields
remain required, with the group ID supplied by the key. The decoder checks
exact row count and fixed indices before restoring the canonical array and
running the original schema and semantic validators. No decisions or witnesses
are filled by code. Unchanged, single-sided, moving and geometry-missing groups
are all included.

The shared row schema is sent once. Repeating the full nested row schema under
29 keys, or enforcing 29 rows via schema minItems/maxItems, was rejected by the
endpoint (HTTP400). A JSON-string form was accepted but produced malformed inner
JSON; it is not used. The final indexed form requires all IDs at the API level
and enforces exact row count in code. Final unmatched IDs depend on the model's
decisions, so `noncommon_checks` completeness remains under the original semantic
validator. Decision prompts and evidence remain intact, with an added form
instruction before the evidence.

## CPU entrypoint

From an existing owned compute allocation, after inspecting its CPU load:

```bash
EECBench/scripts/gemini_env.sh /vast/users/guangyi.chen/anaconda3/bin/python \
  EECBench/scripts/run_gs_integrated_gemini_cpu.py \
  --manifest /absolute/manifest.json --narrative /absolute/narrative.json \
  --output /absolute/new-case --cores 21,22,23,24
```

The four explicit cores must belong to the current allocation and pass an idle
sample. All GPUs are hidden; local models run in FP32, four threads, with a
24 GiB stage process-tree RSS cap. The CPU implementation reuses inspected CPU
adapter code from `experiments/study3/cpu_adapters`, never its inference results.
RoMa is sequential on CPU. Precision and scheduling differ from GPU runs, so
cross-backend runtime and numerical differences are not a pure VLM ablation.
The default completes spatial scoring; `--stop-after identity/presence` is also
supported. Optional Shot2 receives detection/clustering only.

## Records

Canonical inputs and responses, wire inputs/responses, exact prompt/schema,
image hashes, served model, provider, raw API response and usage are preserved.
`gemini_response.json` and `gemini_usage.json` contain the provider response and
token accounting; request metadata contains no credentials or base64 images.
The exact request can be reconstructed from the saved prompt/schema and original
images. For identity forms, `gemini_prompt.txt`, `gemini_output.schema.json` and
`gemini_form_response.json` preserve the actual wire format; `prompt.txt`,
`output.schema.json` and `response.json` retain the canonical interface.
Request metadata records separate canonical/wire hashes and required group IDs.
`events.jsonl` uses provider-tagged normalized completion events solely
for compatibility with existing accounting; these are not Codex CLI events.

Google's compatibility endpoint may include unitemized thinking tokens in
`total_tokens` but omit them from `completion_tokens`. Recorded normalized output
is `total_tokens - prompt_tokens`; raw fields remain available. Any price estimate
uses output including thinking, is separate from setup probes, and is not a
claim about the account's actual invoice.

Official references: [model](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash),
[API compatibility](https://ai.google.dev/gemini-api/docs/openai),
[pricing](https://ai.google.dev/gemini-api/docs/pricing).

This branch is experimental. Equal final scores alone do not establish equal
per-entity quality. The original Astra pipeline remains the default.

## Study2 validation outcome (2026-09-19)

The first CPU experiment reached registration but stopped at aligned identity
review. Two byte-identical API requests returned schema-valid JSON but reviewed
only 4/29 and 20/29 initial identity groups, respectively. Existing semantic
validators rejected both; no final presence or spatial score was produced.
Do not treat this branch as a validated replacement for Astra. See
[the complete failure report](../experiments/study2_gemini35_cpu_20260919/REPORT.md).

The subsequent required-ID repair passed a frozen-evidence Study2 aligned
identity replay: 29/29 initial reviews and 18/18 final unmatched checks, with
the unchanged semantic validator passing. Eight adapter regression tests and
the representation/provenance audit passed. The final indexed form took one
call (186.40 seconds, 262277 tokens); rejected schema variants and a failed
JSON-string-form call are retained separately. Presence/spatial were not rerun.
This validates the repair on this case, not full-pipeline or general model
quality. See the [repair report](../experiments/study2_gemini_required_form_20260919/REPORT.md).
