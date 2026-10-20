# Re-segmenting CineTrans and HoloCine episode videos at their inference cuts — 2026-10-05

## Request

For all evaluated HoloCine and CineTrans outputs (first-200 batch: 200 videos
each), determine the cut positions actually used at inference from the run
records, re-segment each episode video into shots at those positions instead of
the nominal 5-second grid, and resample the keyframes of each shot.

## Inference records

| Model | Record | Cut definition |
| --- | --- | --- |
| CineTrans-DiT (`hf_dataset`, official multi-shot script) | `source_snapshots/ERCBench-CineTrans-400/episodes/<id>/metadata.json` → `mask.mask_info` (latent frames per shot) | Wan2.1 VAE: latent 0 → frame 0, latent t≥1 → frames 4t−3…4t; shot k starts at frame 4·Σ(mask_info[:k]) − 3 |
| HoloCine (`local_accepted`, official `generate_episode`) | `holocine_generation_200_20260922/attempts/<id>/<n>/input.json` → `cuts`, passed as `shot_cut_frames` (`campaign.py`) | shot k starts at `cuts[k-1]` |

Checks (all 400 pass): recorded frame count = decoded frame count (321 / 481 /
641 for 4 / 6 / 8 shots); recorded shot count = contract shot count; HoloCine
recorded video SHA-256 = evaluated file.

Both models used the same plan: shot 1 = frames 0–80 (81 frames), each later
shot 80 frames, starting at 81, 161, 241, … (5.0625 s, 10.0625 s, …). The
previous keyframe sampler used the nominal grid (frames 80, 160, 240, …), one
frame early, and put frame 0 of each later shot exactly there.

## Visible change at the recorded cuts (`collect_cuts.py` → `cut_records.json`)

Per-frame mean absolute grayscale change at 208×120; a clear cut is ≥10× the
video's median change and ≥5 gray levels.

- HoloCine: 731 of 800 boundaries show a clear cut; it appears 0–3 frames after
  the recorded start (3: 417, 2: 198, 1: 65, 0: 46; −2: 3; 6–7: 2). Each latent
  decodes into 4 frames, so the first frames after the recorded start can still
  show the previous shot.
- CineTrans: 45 of 800 boundaries show a clear cut, all exactly at the recorded
  start; elsewhere the change at the boundary is faint (its frequent missing
  cuts).
- Abrupt changes away from planned cuts are content defects, not shot
  boundaries, and are kept in the keyframes: first-frame glitches (CineTrans 35
  videos, HoloCine 10), flicker/black-frame bursts or mid-shot jumps (HoloCine
  26 videos, CineTrans 2).

## Re-segmentation and keyframes (`resegment.py`)

- Segments: shot k = frames [start_k, start_{k+1}) from the records; the last
  shot runs to the end of the video.
- Keyframes: six frames evenly spaced over [a, b], extracted by exact frame
  index (one ffmpeg pass per video, JPEG `-q:v 2` as before):
  - a = 0 for shot 1 (first-frame defects stay visible);
  - a = start_k + 4 for later shots (skips the first decoded latent group); if
    a clear visible cut occurs later but within 8 frames of the recorded cut,
    a = visible cut + 1 (applies to #054 HoloCine Shot2 and #088 HoloCine
    Shot5);
  - b = end_k − 1 − 4 (≈0.25 s end margin, as before).
  - 4-shot example: Shot1 0,15,30,46,61,76; Shot2 85,99,113,128,142,156; …
- Output: `keyframes/<model>/<episode_id>/ShotN/frame_00000K.jpg` (12,000
  frames, 449 MB) and one `keyframe_manifest.json` per video (schema
  `vl_vv_keyframes_v2`: segment frames/seconds, per-frame `frame_index`,
  timestamps, SHA-256, record provenance). `segments.json` lists all segments.
  A manifest was test-prepared with `run_vl_vv_detection.py prepare`
  successfully (scratch case, removed).

## Verification (`verify.py` → `verification.json`)

- Frame identity: 12 random videos, 336 keyframes matched against an independent
  full decode: 335 exact; the other is pixel-identical to its neighbor
  (static scene).
- First keyframe of shots 2+ after the visible clear cut: CineTrans 45/45,
  HoloCine 731/731 (old sampling: 0/45 and 3/731).
- Visual before/after: `qa/p014_holocine_old_vs_new.jpg`,
  `qa/p028_cinetrans_old_vs_new.jpg`, `qa/p054_holocine_old_vs_new.jpg`.

## Not done

Detection, entity matching and evaluation have not been rerun on the new
keyframes; all existing v1/v2 results for these 400 videos still use the old
nominal-grid keyframes. Clip-based models (Wan2.1, Wan2.2, StoryMem) are
unaffected. `prepare_case.py` of the batch still samples episode videos on the
nominal grid.

Compute: CPU only, on existing allocation 236651 / node270 (checked idle), 2–4
threads; no GPU and no API calls.

## Enforcement for all later evaluations (user decision, same day)

- Shared module `EECBench/scripts/episode_shot_segments.py` (record lookup for
  CineTrans Hugging Face metadata, CineTrans local run configs and HoloCine
  attempts; keyframe rule; frame-index extraction; manifest guard). It
  reproduces all 400 keyframe plans exactly, and on a real HoloCine task the
  batch preparation produces byte-identical keyframes.
- `experiments/vl_vv_multimodel_first200_20260926/prepare_case.py`: episode-scope
  tasks are segmented at recorded cuts (manifest `vl_vv_keyframes_v2` with a
  `segmentation` block); `--legacy-nominal-keyframes` keeps the old sampler for
  reproduction only.
- Guards: `run_vl_vv_detection.py prepare`, `run_vl_vv_pipeline.py`,
  `run_vl_vv_issue_discovery.py`, `run_vl_vv_issue_review.py` refuse
  grid-sampled episode manifests unless `--allow-legacy-nominal-keyframes`.
  Clip-model cases are unaffected. Historical CineTrans/HoloCine cases are now
  refused by default (verified by dry run).
- Tests: `tests/test_episode_shot_segments.py` (8, including a real ffmpeg
  extraction); 58 focused tests pass. Pre-change copies in `source_before/`.
