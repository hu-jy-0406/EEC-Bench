# VL/VV issue-review agent v1

The issue-review agent is the third stage of the agentic V-L/V-V pipeline. It
adjudicates every candidate from issue discovery against the original episode
prompt, full `contract.json`, and all original keyframes. Discovery candidates
remain hypotheses until this review is complete. The reviewer does not produce
a benchmark score or discover additional issues.

## Inputs

- A completed case directory containing `contract.json` and
  `raw_manifest.json`.
- A successful `vl_vv_issue_discovery_v1` JSON result supplied with `--issues`.
- All six original keyframes per shot, resolved and SHA-256 checked through the
  raw manifest.

The model receives the original prompt, complete contract, the three discovery
candidate lists, image attachment order, and all original keyframes. It does
not receive detector ledgers, DINO scores, or geometry results. It must review
each candidate separately and return exactly one review per `issue_id`.

## Review result

The raw model response is a list of per-issue reviews with:

- `verdict`: `confirmed`, `rejected`, or `uncertain`;
- `confidence`: `high`, `medium`, or `low` confidence in that review verdict;
- `critique`: concise Chinese reasoning about the candidate;
- `prompt_assessment`: whether the original prompt/contract establishes the
  claimed requirement or cross-shot comparison;
- `evidence`: original shot/frame references with `supports`, `refutes`, or
  `context` roles and visible observations.

The runner verifies exact one-to-one issue coverage, valid frame references,
and that confirmed verdicts cite supporting evidence. It preserves the
discovery candidate fields and adds a `review` object to each candidate.
`review_run` records the input hash, verdict counts, model, token usage, and
separate standard-API USD estimate. The original discovery JSON is copied
byte-for-byte to `discovery_input.json`; source images and JSONs are never
modified.

If discovery found no candidates, the runner writes a valid enriched result
with zero model calls and zero estimated cost.

## Invocation

```bash
EECBench/scripts/openai_api_env.sh \
  /vast/users/guangyi.chen/anaconda3/bin/python \
  EECBench/scripts/run_vl_vv_issue_review.py \
  --case /abs/completed-detection-case \
  --issues /abs/issue-discovery/result.json \
  --output /abs/fresh-issue-review-output
```

The stage is pinned to `gpt-6-luna` with `low` reasoning and refuses to run
unless the configured OpenAI API transport is active. Model output schema:
`schemas/vl-vv-issue-review-v1.schema.json`; review instructions:
`prompts/vl_vv_issue_review_v1.txt`.

## Scope limits

Review decisions are model judgments, not human labels or calibrated
probabilities. A confirmed issue is a reviewed finding, not by itself an
episode score. The downstream episode scorer is specified in
`docs/vl-vv-episode-scoring-v2.md`; its stronger severity penalties remain
uncalibrated against human scores. Version 1 scores are preserved separately.
