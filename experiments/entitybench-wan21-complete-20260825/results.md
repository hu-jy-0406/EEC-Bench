# Wan2.1 EntityBench complete one-episode evaluation

Date: 2026-08-25 UTC

## Scope and comparability

This is the complete three-pillar evaluation pipeline on one fixed easy
EntityBench episode (10 shots), matching the earlier EECBench integration
smoke scope. It is not the canonical 140-episode / 2,491-shot benchmark.

Wan configuration: Wan2.1-T2V-1.3B, 832x480, 81 frames, 16 fps, 20 sampling
steps, UniPC, shift 8, guidance 6, base seed 20260825. The published table uses
the full benchmark and a different Gemini judge version, so the comparison
below is diagnostic only and must not be interpreted as a leaderboard ranking.

The canonical judge requested by the repository, Gemini 2.5 Pro, returned 404
for this new account. Google required migration to Gemini 3.1 Pro Preview.
The successful run therefore used `gemini-3.1-pro-preview`,
`reasoning_effort=low`, one unique API key, and three client streams.

## Full 51-metric result and paper reference

| Group | Metric | Wan2.1 local | EntityMem | StoryMem | HoloCine | CineTrans |
|---|---|---:|---:|---:|---:|---:|
| P1 | subject_consistency | 0.9553 | 0.881 | 0.759 | 0.860 | 0.968 |
| P1 | temporal_flickering | 0.9875 | 0.976 | 0.838 | 0.957 | 0.979 |
| P1 | motion_smoothness | 0.9918 | 0.988 | 0.849 | 0.964 | 0.990 |
| P1 | dynamic_degree | 0.6000 | 0.657 | 0.562 | 0.721 | 0.688 |
| P1 | aesthetic_quality | 0.6255 | 0.593 | 0.475 | 0.518 | 0.596 |
| P1 | imaging_quality | 65.5771 | 66.00 | 56.41 | 49.97 | 68.57 |
| P3 presence | character | 0.8500 | 0.967 | 0.849 | 0.882 | 0.796 |
| P3 presence | object | 0.9167 | 0.888 | 0.893 | 0.723 | 0.776 |
| P3 presence | location | 0.0000 | 0.687 | 0.681 | 0.624 | 0.651 |
| P3 character fidelity | overall | 0.4700 | 0.740 | 0.452 | 0.349 | 0.327 |
| P3 character fidelity | face | 0.5000 | 0.607 | 0.424 | 0.369 | 0.366 |
| P3 character fidelity | hair | 0.4950 | 0.684 | 0.485 | 0.482 | 0.413 |
| P3 character fidelity | clothing | 0.4600 | 0.802 | 0.504 | 0.339 | 0.378 |
| P3 character fidelity | build | 0.4750 | 0.726 | 0.539 | 0.449 | 0.521 |
| P3 object fidelity | overall | 0.5267 | 0.601 | 0.618 | 0.267 | 0.384 |
| P3 object fidelity | shape | 0.5850 | 0.712 | 0.701 | 0.373 | 0.508 |
| P3 object fidelity | color_texture | 0.5067 | 0.691 | 0.709 | 0.331 | 0.480 |
| P3 object fidelity | proportions | 0.5783 | 0.728 | 0.715 | 0.383 | 0.539 |
| P3 object fidelity | details | 0.5483 | 0.573 | 0.598 | 0.256 | 0.371 |
| P3 location fidelity | overall | 0.4000 | 0.555 | 0.504 | 0.306 | 0.428 |
| P3 location fidelity | layout | 0.4100 | 0.603 | 0.529 | 0.354 | 0.474 |
| P3 location fidelity | color_mood | 0.4900 | 0.706 | 0.627 | 0.474 | 0.588 |
| P3 location fidelity | landmarks | 0.3800 | 0.562 | 0.522 | 0.305 | 0.429 |
| P3 location fidelity | perspective | 0.4100 | 0.557 | 0.520 | 0.346 | 0.488 |
| P3 action | overall | 0.6400 | 0.618 | 0.547 | 0.569 | 0.273 |
| P3 action | depicted | 0.7000 | 0.519 | 0.446 | 0.458 | 0.124 |
| P3 action | subject_identity | 0.7000 | 0.706 | 0.595 | 0.606 | 0.478 |
| P3 action | subject_action | 0.6300 | 0.697 | 0.626 | 0.695 | 0.323 |
| P3 action | object_interaction | 0.7250 | 0.781 | 0.712 | 0.616 | 0.346 |
| P3 action | motion_quality | 0.6500 | 0.716 | 0.723 | 0.772 | 0.528 |
| P2 DINO | cs_face | 0.8054 | 0.737 | 0.792 | 0.751 | 0.772 |
| P2 DINO | cs_object | 0.8463 | 0.798 | 0.839 | 0.803 | 0.794 |
| P2 DINO | transition_boundary | 0.3172 | 0.738 | 0.663 | 0.498 | 0.508 |
| P2 LLM face | accuracy | 0.0000 | 0.406 | 0.226 | 0.228 | 0.091 |
| P2 LLM face | mean | 0.4000 | 0.426 | 0.234 | 0.242 | 0.145 |
| P2 LLM face | face | 0.3667 | 0.381 | 0.216 | 0.223 | 0.145 |
| P2 LLM face | hair | 0.4000 | 0.447 | 0.248 | 0.282 | 0.175 |
| P2 LLM face | clothing | 0.3333 | 0.464 | 0.241 | 0.242 | 0.143 |
| P2 LLM face | build | 0.5000 | 0.489 | 0.260 | 0.285 | 0.217 |
| P2 LLM object | accuracy | 0.2000 | 0.164 | 0.203 | 0.088 | 0.092 |
| P2 LLM object | mean | 0.3800 | 0.202 | 0.222 | 0.094 | 0.145 |
| P2 LLM object | shape | 0.5200 | 0.232 | 0.239 | 0.104 | 0.180 |
| P2 LLM object | color_texture | 0.3800 | 0.235 | 0.243 | 0.104 | 0.190 |
| P2 LLM object | proportions | 0.5800 | 0.238 | 0.244 | 0.105 | 0.195 |
| P2 LLM object | details | 0.3000 | 0.184 | 0.209 | 0.087 | 0.124 |
| P2 LLM scene | accuracy | N/A | 0.309 | 0.398 | 0.304 | 0.119 |
| P2 LLM scene | mean | N/A | 0.659 | 0.671 | 0.616 | 0.432 |
| P2 LLM scene | layout | N/A | 0.697 | 0.684 | 0.641 | 0.449 |
| P2 LLM scene | color_mood | N/A | 0.716 | 0.724 | 0.669 | 0.619 |
| P2 LLM scene | landmarks | N/A | 0.603 | 0.637 | 0.563 | 0.346 |
| P2 LLM scene | perspective | N/A | 0.727 | 0.696 | 0.713 | 0.467 |

The six scene cross-shot values are N/A, not API failures: no location
appearance passed the cross-shot fidelity gate. The gate admitted 16/29
character/object/location appearances and excluded 13; all 61 logical Gemini
calls completed successfully.

Additional gap-decay curve (not part of the 51-row paper table):
gap 2 = 0.5892 (4 pairs), gap 4 = 0.5133 (5), gap 6 = 0.5823 (2),
gap 8 = 0.4643 (2).

## Timing

| Stage | Wall time |
|---|---:|
| Wan inference, 10 shots | 34:19.34 |
| EntityBench Pillar 1 command | 03:39.01 |
| Pillar 1 measured episode body | 03:25.82 |
| subject_consistency (includes DINO init) | 00:35.10 |
| temporal_flickering | 00:01.57 |
| motion_smoothness | 01:09.90 |
| dynamic_degree | 01:06.47 |
| aesthetic_quality | 00:12.23 |
| imaging_quality | 00:20.53 |
| Pillar 2/3 command | 48:57.34 |
| shared GroundingDINO pass | 01:10.85 |
| Pillar 3 prompt alignment | 40:54.67 |
| Pillar 2 local metrics | 00:03.04 |
| Pillar 2 Gemini + gap metrics | 06:37.87 |
| EntityBench evaluation total (P1 + P2/3 commands) | 52:36.35 |
| Successful inference + evaluation pipeline | 1:26:55.69 |
| Actual start-to-final wall time including API migration/debug | about 3:00:34 |

The sum of successful Gemini request durations is 6,873.46 seconds, larger
than wall time because three requests could be in flight concurrently.

## Gemini usage and cost

Formal successful run (exact from returned usage):

- logical calls: 61/61 successful;
- input tokens: 87,259;
- visible completion tokens: 4,292;
- inferred thinking tokens: 25,443;
- billable output tokens: 29,735;
- total tokens: 116,994;
- list-price equivalent: 87,259 × $2/M + 29,735 × $12/M =
  **$0.531338**.

The original manifest recorded $0.226022 because Google's OpenAI-compatible
response omitted thinking from `completion_tokens_details`; the exact thinking
count is recoverable as `total_tokens - prompt_tokens - completion_tokens`.
The evaluator has been fixed to use the larger valid output count.

Three interrupted compatibility/debug runs returned 41 additional successful
responses before cancellation: 51,388 prompt tokens and 2,622 visible output
tokens (54,010 known tokens; $0.134240 visible-token lower bound). Their
per-response total/thinking fields were not logged before the processes were
cancelled, so an exact all-debug token total cannot be reconstructed locally.
Thus the exact formal cost is $0.531338; the known minimum including debug is
171,004 tokens and $0.665578. Failed 404/503 responses returned no usage.

## Artifacts

- `generated/`: ten Wan videos.
- `eval_results/pillar1_vbench/`: Pillar 1 report and manifest.
- `eval_results/pillars23_gemini31_low_c3_retry30m/`: successful Pillar 2/3
  report, episode audit, and manifest.
- `logs/`: generation, evaluation, API-retry, and timing logs.

