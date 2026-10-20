# CineTrans cut probe: ROCm port or length? (2026-10-03)

Question: CineTrans produced cuts at only 61/800 expected boundaries in the
first-200 cohort (`../cinetrans_cut_audit_20261003/REPORT.md`). Is the local ROCm
port broken, or is the production setting outside what the model handles?

Method: four generations with the production code path (same port, weights,
LoRA, seed 42, 50 UniPC steps, shift 8, guidance 6, mask_p 0, masked layers 6-27,
`general_prompt`), each on one verified-idle card of own allocation 229942
(cards 0-3; 0% util, 0 VRAM, no KFD process before launch). `configs/`,
`logs/`, `videos/`, `analyze.py`, `cuts.json`.

| Run | Prompts | Frames (s) | mask_info | Expected cut frames | Detected | Adjacent mid-frame diff | Wall s |
|---|---|---|---|---|---|---|---|
| A | official README demo, 2 shots | 81 (5) | 11,10 | 41 | 41 | 60.1 | 634 |
| B | episode 8 shots 1-2 + global | 81 (5) | 11,10 | 41 | 41 | 78.8 | 620 |
| C | episode 8 shots 1-3 + global | 129 (8) | 11,11,11 | 41, 85 | 41, 85 | 64.5, 51.1 | 923 |
| D | episode 8 shots 1-2 + global | 161 (10) | 21,20 | 81 | none | 17.3 | 1283 |


## Conclusion

The ROCm port reproduces exact cuts at the configured boundaries, including with
episode 8's own prompts, at official lengths (5-8 s, 2-3 shots). With the same two
prompts at the production per-shot length (5 s per shot, 161 frames) the cut
disappears. The missing cuts in the cohort therefore come from running CineTrans-DiT
at 5 s per shot and 20-40 s total, beyond its demonstrated range, not from a
duplicated-prompt or port bug.

Limits: one seed per configuration; D is a single sample. Lengths between 129 and
161 frames were not probed.
