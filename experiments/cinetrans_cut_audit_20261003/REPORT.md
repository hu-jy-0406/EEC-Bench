# CineTrans shot-cut audit (2026-10-03)

Trigger: human check of priority 8 (2hEV6a24yXc_s00017_n8_clean_v3_alt8) showed all
eight CineTrans shots looking identical.

## Prompt/config checks (no bug found)
- The 8 shot prompts are distinct (8 distinct SHA-256), passed in shot order with the
  global prompt appended last (`general_prompt: true`), `mask_info` [21,20,...,20]
  sums to 161 latent frames for 641 frames. All 200 episodes: seed 42, mask_p 0,
  masked layers 6-27 (upstream defaults; p=0 = deterministic shot-block masks).
- Local ROCm `ShotBlockMask` was checked equal to the dense official masks on
  synthetic inputs (cinetrans_dit_rocm_20260925/REPORT.md); no end-to-end comparison
  with the unmodified official attention exists (it OOMs at this length).

## Measured behaviour (`audit.py`, `cuts2.py`; 16 fps, 208x120 gray)
- Hard cuts detected (diff > max(12, 4x local median)):
  CineTrans 61 of 800 expected; 163/200 episodes contain no cut at all.
  HoloCine 830 detected for 800 expected; 754/830 within 4 frames of a boundary
  (typically 4 frames, 0.25 s, after the nominal boundary).
- Adjacent-shot middle-frame mean abs diff: CineTrans 7.2 (25.2% of pairs < 3),
  HoloCine 45.1, Wan2.2 69.6, StoryMem 65.0.
- Priority 8 CineTrans: 0 of 7 cuts; adjacent middle-frame diffs 1.7-2.0, i.e. one
  nearly static 40 s take.

## Interpretation
Not a duplicated-prompt bug. CineTrans in this setting systematically produces one
continuous take instead of shots; priority 8 is an extreme case. Cause not separated:
(a) model limitation / out-of-distribution length (official demos are 5-8 s with 2-4
shots; ours are 20-40 s with 4-8 shots), or (b) an error in the local ROCm attention
path. Its absence of cuts also makes cross-shot comparisons trivially consistent,
which likely inflates its V-V cross score (93.09).
