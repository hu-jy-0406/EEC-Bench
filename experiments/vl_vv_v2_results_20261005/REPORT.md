# Current v2 evaluator on all 14 tested videos — 2026-10-05

Page: https://claude.ai/artifact/1HJ6ew9LeuZ2FdEtVKKe8g (private until shared
from its Share menu). Companion old-vs-new page:
https://claude.ai/artifact/TNDgZ1ENrvLzdDPbH699eS.

## What was run

All 14 videos evaluated so far with the new pipeline (10 episodes, 5 models),
three runs each with the current version (discovery v2 with explicit
dual-label rules and the transition gate → review v2 → scoring v3), through
`run_vl_vv_pipeline.py --mode from-registry --discovery-protocol v2` on the
frozen first-200 detection cases.

- 9 videos: the 27 runs of `../vl_vv_old_vs_new_20261005/runs/v2/` (reused).
- 5 videos (#014 HoloCine, #032 Wan2.2, #047 StoryMem, #069 Wan2.1, #165
  CineTrans) previously had only older-prompt validation runs; 15 new runs here
  (`run_remaining.py`, `launch.sh`), all successful, on existing allocation
  236651 / node270 (checked load ≈0.13, API-only, no GPU).

## Page content

Per video: episode ID, generation model, shots/duration and generation mode,
full prompt, web copy of the evaluated video with shot buttons, scores of the
three runs (median and old historical score), verified key artifacts × runs
with evidence frames and jump-to-frame buttons, R1 issues (labels, verdicts,
severities, checklist items, English summary and assessment, original text),
R2/R3 issues, R1 checklist audit and continuity record, usage per run.
Overview table with model filter.

## Results (assistant-verified key artifacts; 57 artifacts + 2 controls)

Found and confirmed in 81 of 171 artifact-runs (47%): cross-shot 44/63 (70%),
transitions 9/15 (60%), V-L 19/54 (35%), within-shot 9/39 (23%). Controls:
StoryMem #014 consistent courtyard left alone in 3/3 runs; HoloCine #014
sub-second late cuts flagged in 1/3 runs (counted as a false alarm), rejected
in 2/3. The selection includes known evaluator failures; this is not a
random-sample estimate.

## Cost (standard GPT-6 Luna API estimates, not bills)

All 42 runs shown: 143 calls, 8,742,302 input (5,332,681 cached), 262,855
output; ≈ USD 0.53 with the cache hits of these runs, ≈ USD 1.01 if no input
were cached (USD 0.024 per run). New runs made for this page: 15 runs, 50
calls, 2,865,169 input (1,714,401 cached), 82,658 output, ≈ USD 0.17
(≈ USD 0.33 uncached). Detection front end not included.

## Files

`results_reference.json` (14 videos), `results_annotations.py` →
`results_annotations.json` (5 new videos; the other 9 use
`../vl_vv_old_vs_new_20261005/annotations.json`), `build_images.py`,
`build_videos.py` + `fix_timing.py` (web videos, exact frame timing),
`build_results_page.py`, `results_template.html`, `page/`.
