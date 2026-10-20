# Old (v1) vs new (v2) evaluator on representative failure cases — 2026-10-05

Page: https://claude.ai/artifact/TNDgZ1ENrvLzdDPbH699eS (private until shared from its Share menu).

## Request

Keep both pipelines runnable; fix the prompt-labeling gaps and the batch
controller protocol mismatch; rerun cases where the old pipeline missed
artifacts or mis-categorized V-L/V-V; compare side by side (detections, misses,
labels, scores, visual evidence) on a shareable page.

## Fixes (both pipelines preserved)

- `prompts/vl_vv_issue_discovery_v2.txt`: explicit dual-label rules for a
  missing required cut / broken continue (always V-V cross
  `transition_realization` + V-L `shot_structure`) and for within-shot changes
  the text contradicts. `run_vl_vv_issue_discovery.py` now rejects a
  `transition_realization` issue without V-L `shot_structure` (repair loop
  applies). v1 prompt untouched.
- `experiments/vl_vv_multimodel_first200_20260926/run_batch.py`:
  `--discovery-protocol v1|v2`; success check accepts only that chain's scoring
  protocol; chain recorded in `progress.json`; legacy directories resume as v1
  without a flag; mismatched flag refused; new directories must choose.
  `run_vl_vv_pipeline.py --discovery-protocol v1|v2` unchanged (default v2).
- Tests: 50 pass (`test_vl_vv_checklist_v2`, `test_vl_vv_batch_protocol`,
  discovery, scoring, pipeline, repair loop). Pre-change copies in
  `source_before/`.

## Design

Nine cases (`reference.json`): owner examples #002 Wan2.1 (categorization),
#014 Wan2.1 (background), #028 Wan2.2 (clothing); StoryMem #014 control;
transition failures #028 and #180 CineTrans; #047 Wan2.1 (swaps/duplicates);
#015 CineTrans (within-shot); #068 HoloCine (hard case). For each case the
assistant listed 3–5 key artifacts verified on the original keyframes, with
expected labels and evidence frames (37 artifacts + 1 control).

Runs: both pipelines through `run_vl_vv_pipeline.py --mode from-registry` on
the same frozen detection case. Old = historical first-200 run + 2 fresh
reruns; new = 3 fresh runs; 45 fresh runs, all succeeded, executed as three
API-bound streams in an overlapping step of existing allocation 239124
(node257, checked load ≈5/128 cores, no GPU). #002's historical run used an
earlier v1 prompt revision; all other historical runs used the current v1
prompts. Matching of issues to artifacts and the English summaries are
assistant judgments (`annotations_draft.py` → `annotations.json`).

## Results (artifact × 3 runs per pipeline)

| | Old (v1) | New (v2) |
| --- | ---: | ---: |
| Key artifacts found and confirmed | 31/111 (28%) | 59/111 (53%) |
| Artifacts missed by the historical v1 run | 13/90 | 42/90 |
| Artifacts v1 filed as V-L only | 4/6 | 6/6 |
| Artifacts the historical v1 run found | 14/15 | 11/15 |
| Found with both labels when both apply | 1/13 | 31/33 |
| Control (consistent courtyard) | silent 3/3 | proposed, rejected by review 3/3 |

Clear gains: missing cuts (#028, #180, #015: new finds them in 8 of 9 runs, old
never), merged/swapped characters (#028 CineTrans, #047), cross-shot identity,
clothing, prop and setting changes (#002, #014, #028 Wan2.2), consistent dual
labels. Old reruns showed v1 filing the same change inconsistently (V-L only,
V-V only, or twice in both lists).

Regressions and remaining misses: the #014 wide-brim hat (old 2/3, new 0/3) and
one #014 start-pose run; within-shot defects are only partly caught (dress
flicker tie, first-frame flashes 4/9 new runs vs 0 old, #068 vanishing and
woman→man morph missed by both, #015 plant pop-in missed by both); some face
changes (#047 Sleeveless man) missed by both; #068 static take missed by all
runs here (found in an earlier validation round). False positives seen in new
displayed runs: one within-shot "cut" in #028 Wan2.2 R1 (smooth reframing);
debatable: StoryMem scarf pattern (also confirmed by old R3), #047 training-room
walls, #068 dark-frame outfit details.

Median scores (V-L / within / cross), old → new: #002 75/100/81.25 →
28.13/100/30.47; #014 Wan2.1 56.25/100/100 → 38.09/100/37.5; StoryMem #014
100/100/100 → 100/100/100; #028 Wan2.2 75/100/75 → 60.94/100/37.5; #028
CineTrans 18.75/100/100 → 18.75/100/25; #180 25/100/100 → 25/90/25; #047
37.5/100/100 → 42.19/100/28.13; #015 37.5/100/81.25 → 10.55/100/42.19; #068
28.13/100/100 → 28.13/90/56.25.

## Cost (standard GPT-6 Luna API estimate, not a bill)

Prices USD 0.10/M uncached input, 0.01/M cached input (subset of input),
0.50/M output. Old reruns: 18 runs, 54 calls, 2,775,782 input (1,043,778
cached), 35,479 output, USD 0.201377 (0.011188/run). New runs: 27 runs, 93
calls, 5,877,133 input (3,618,280 cached), 180,197 output, USD 0.352167
(0.013043/run). Total 147 calls, USD 0.553544 (`usage_summary.json`). Historical
v1 runs are reused, not re-billed.

## Videos on the page (version 2)

Each case shows the evaluated generated video: shot clips joined in prompt
order for Wan2.1/Wan2.2/StoryMem, the single episode video for
CineTrans/HoloCine. `build_videos.py` re-encodes them for the web (H.264
CRF 26, same 832×480 frames, 16 fps, no audio; 9.71 MB total), run on node257
with 4 threads; originals are only read. `page/video/timing.json` holds shot
starts (from exact frame counts) and keyframe times; evidence buttons seek to
the frame the keyframe extractor used (first frame at or after the keyframe
timestamp). A frame extracted from the web video at a computed time matched the
original keyframe.

## Files

`run_comparison.py`, `launch.sh`, `events_stream*.jsonl`, `runs/{v1,v2}/…`
(full pipeline outputs), `collect_runs.py` → `runs.json`, `reference.json`,
`annotations_draft.py` → `annotations.json`, `build_images.py`,
`build_page.py`, `page_template.html`, `page/` (published HTML and images).

## Token usage and API cost, old vs new (`cost_comparison.py` → `cost_comparison.json`; projection in `cost_projection.json`)

Basis: the same nine cases and frozen detection data, GPT-6 Luna low for both;
18 fresh v1 runs vs 27 fresh v2 runs, every recorded call including repairs.
Prices USD/M tokens: uncached input 0.10, cached input 0.01 (subset of input),
output 0.50 (includes reasoning). Standard-API estimates, not bills.

| Mean per run (evaluation stages) | Old (v1) | New (v2) |
| --- | ---: | ---: |
| API calls | 3.00 | 3.44 |
| Input tokens (cached in these runs) | 154,210 (57,988) | 217,672 (134,010) |
| Output tokens (reasoning) | 1,971 (666) | 6,674 (819) |
| Cost, all input uncached | USD 0.01641 | USD 0.02510 (+53%) |
| Cost with the caching observed here | USD 0.01119 | USD 0.01304 (+17%) |

The observed cache hits come from re-sending the same case several times within
minutes; the production first-200 batch had ~1.4% cached input, and the
historical v1 runs of these cases cost USD 0.01594/run uncached. Use the
no-cache figure for planning.

By stage (no-cache, per run): discovery USD 0.01207 → 0.02009 (calls 1.00 →
1.41; input 115,978 → 177,001; output 948 → 4,775); review 0.00398 → 0.00447;
scoring 0.00036 → 0.00055. Of the USD 0.0087 increase, repair rounds account
for ~72% (11 extra discovery calls in 27 runs, each re-sending ~138k tokens;
19 of 25 triggering errors were shot_scan links to issues whose scope omits the
shot), the longer first discovery answer for ~20% (output 948 → 3,450), and
review/scoring for the rest. By model family: clip models 1.20×, episode models
(CineTrans/HoloCine) 1.87×.

Projection to the 1,000-task first-200 batch (family ratios applied to the
recorded v1 costs): evaluation USD 15.54 → ≈ 22.87 (+47%); detection front end
unchanged at USD 15.13; full pipeline USD 30.67 → ≈ 38.00 (+24%). Projection
from nine cases only.
