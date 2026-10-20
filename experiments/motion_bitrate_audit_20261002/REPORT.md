# Motion and encoding audit of first-200 source videos (2026-10-02)

Script `audit.py`; outputs `motion_per_task.json` (all 1,000 tasks, 5,000 shots)
and `reencode_control.json` (40 Wan2.2 + 40 StoryMem shots). CPU only on
existing allocation 229942; no model calls; sources read only.

All five models: 832x480, 16 fps, H.264, about 5 s per shot. HoloCine mean
bitrate 0.38 Mbps versus 4.2-5.6 Mbps for the others.

## Motion (frames at 8 fps, 208x120 gray; MAD = mean |consecutive frame diff|, 0-255)

| Model | MAD mean | MAD median | first-last diff mean | shots MAD<1.0 |
|---|---|---|---|---|
| Wan2.1 | 3.83 | 2.92 | 23.57 | 14.4% |
| CineTrans | 1.53 | 1.19 | 8.93 | 41.2% |
| Wan2.2 | 5.89 | 4.35 | 31.73 | 7.4% |
| StoryMem | 6.23 | 4.55 | 31.09 | 6.9% |
| HoloCine | 4.54 | 3.50 | 40.36 | 9.2% |

HoloCine is not unusually static; it has the largest within-shot first-to-last
change. CineTrans is by far the most static model. Within each model, episode
MAD is nearly uncorrelated with V-V cross-shot score (|r| <= 0.07) except
CineTrans (r = -0.24).

## Re-encode control (imageio writer, fps 16, quality 5 = HoloCine official default)

| Sample | Mbps before -> after | MAD before -> after | first-last before -> after |
|---|---|---|---|
| Wan2.2 (40 shots) | 4.71 -> 0.52 | 6.51 -> 6.43 | 34.96 -> 34.87 |
| StoryMem (40 shots) | 4.36 -> 0.47 | 6.59 -> 6.50 | 29.11 -> 28.96 |

HoloCine's low bitrate is explained by the save setting (official
`HoloCine_inference_full_attention.py` default `quality: int = 5`), not by
static content. Re-encoding barely changes pixel-level motion statistics.

## Not measured

The effect of quality-5 compression on EEC-Bench scores themselves. HoloCine
attempts kept only the encoded mp4 (no latents), so higher-quality HoloCine
output requires full regeneration (recorded mean generation time 26,127 s per
episode under the shared-node campaign, about 1,450 GPU-hours for 200 episodes).
