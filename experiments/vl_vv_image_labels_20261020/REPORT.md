# Shot/frame labels on attached keyframes — implementation and live check (2026-10-20)

## Request

Owner decision: put a shot and frame label on each keyframe sent to the
model, and make it the default. Motivation (branch-split report,
2026-10-09): the API request carried the prompt followed by 24–48 unlabeled
images, and the model mapped images to shots by counting positions. In #002
Wan2.1 every unlabeled run (branch chain ×2, the v1 historical run) reported
Shot3's collared shirt in Shot4.

## Change

- `scripts/eec_api_codex_shim.py`: new repeatable `--image-label`; each label
  is sent as an `input_text` part immediately before its `input_image`.
  Label count must equal image count. Recorded in `api_request.json`.
- `scripts/run_wedetect_shot_entities.py`: `image_labels()` builds
  `"<shot_id> frame <frame_id>"` labels (API backend only, every image must
  carry both IDs, `EECBENCH_IMAGE_LABELS=on|off`, default on). The
  shot-clustering review sends them; a stored response is reused only if its
  labels match.
- `scripts/gs_prompt_binding.py` (`call`, used by the repair loop for shot
  prompt binding, global entity matching, discovery v1–v5 and review v1–v6):
  sends and records the labels in `request.json`.
- `scripts/gs_shot_prompt_recovery.py`: shot binding frames now carry their
  `shot_id`, so they are labelled too.
- `scripts/run_vl_vv_pipeline.py`: records `image_labels` (`shot_frame_v1` or
  `off`) in `run.json`; transport files are added to `source_hashes`.
- Unchanged: pixels, attachment order, prompts, payloads (`image_order`),
  schemas, gates, scoring, the Codex CLI backend, the geometry (GS) pipeline.

## Tests

`tests/test_image_labels.py`: 9 tests (label construction and off/CLI/missing
ID cases, shim interleaving and count check, argument parsing, shared call
command and record, unlabeled path unchanged, shot clustering labels and
reuse guard, discovery/review keyframe rows carry both IDs). Full suite on a
compute node (existing allocation 286177, node auh7-1b-gpu-250, CPU only):
1,705 passed, 120 failed, 5 errors with the change; 1,696 passed with the
same 120 failures and 5 errors with the change stashed. The failing set is
identical (pre-existing, outside the VL/VV path: missing ffmpeg in the test
environment, a stale shot-recovery test that calls the removed
`materialize_review`, historical physical-identity tests).

## Live check (#002 Wan2.1, default chain, 3 runs)

`run_jobs.py p002`, `launch.sh 286177 p002 3`: `run_vl_vv_pipeline.py --mode
from-registry` on the same frozen case as the 2026-10-09 validation
(discovery v5 → review v6 → scoring v5). Only the labels differ from
`vl_vv_branch_split_20261009/runs/main/run_{a,b}/p002_wan21`. API only, on
existing allocation 286177 (node load checked before launch; no GPU). All 3
runs succeeded (83–106 s). Every image-bearing request carried 24 labels
(`Shot1 frame 0` … `Shot4 frame 5`).

Ground truth from the keyframes (contact sheet checked by the assistant):
Shot3 shows the collared, buttoned dark blue-gray shirt and the bright
pale-walled room; Shots 1, 2 and 4 show the T-shirt.

| | Unlabeled (2026-10-09, 2 runs) | Labeled (3 runs) |
| --- | --- | --- |
| V-L shirt issue, shot | Shot4 ×2 (wrong) | Shot3 ×3 (correct) |
| V-V shirt issue, odd shot | Shot4 ×2 (wrong) | Shot3 ×3 (correct; one run also notes Shot4's different lettering) |
| Shot3 missing dark foreground shape (V-L) | 2/2 | 3/3 |
| Face identity (V-V) | 2/2 | 3/3 |
| Hair (V-V) | 2/2 (once inside the face issue) | 3/3 |
| Shot4 sofa shape (V-V) | 2/2 | 1/3 |
| Shot2 hair not short (V-L) | 0/2 | 3/3 |
| Shot2 not an oblique view (V-L) | 0/2 | 2/3 confirmed, 1 rejected |
| Shot3 glance direction (V-L) | 0/2 | 1/3 (not checked by the assistant) |

Scores (V-L / V-V): unlabeled 56.25 / 59.38 and 42.19 / 57.62; labeled
15.82 / 60.55, 21.09 / 65.63, 31.64 / 57.81. V-L is lower because more V-L
issues were confirmed (Shot2 hair, Shot2 viewpoint), not because of the
shirt fix itself.

## Cost

22 calls; 939,078 input tokens (587,857 cached, 351,221 uncached) and 46,237
output tokens: USD 0.064 at the GPT-6 Luna standard API estimate (USD 0.10/M
uncached input, 0.01/M cached input, 0.50/M output; not a bill), USD
0.019–0.024 per run. The two unlabeled #002 runs cost USD 0.017 and 0.022;
the labels themselves add a few tokens per image.

## Limits

- One video, three runs. The fix of the motivating error is clear; whether
  labels change recall or shot attribution on other videos is not measured.
  A rerun of the 8-video reference set (16 runs, about USD 0.47) would answer
  that.
- `from-registry` runs exercise discovery and review only. Labels in shot
  clustering, shot prompt binding and global matching are covered by tests
  but run live only in `full` mode (GPU detection).
- Other new findings (Shot2 hair and viewpoint) are model verdicts, not
  human-annotated artifacts.
