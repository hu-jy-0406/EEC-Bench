# Entity displacement integration validation

Frozen Study2/3/4 frontend, motion, final identity, registration and boundary review reused. No fresh frontend/GPU/model run.

| Study | Within position score | Boundary position score | Episode position score | Scored records |
|---|---:|---:|---:|---:|
| Study2 | 60.679845 | 63.227605 | 61.110942 | 46 |
| Study3 | 62.809068 | 71.232577 | 64.237027 | 48 |
| Study4 | 54.559374 | 80.093012 | 55.686057 | 33 |

Per-entity round-trip precision r_e, raw means/maxima or boundary distances, medians, original/aligned centers and within-frame distance pairs are retained in study*/results.json and entities.csv.
Study4 Shot1 historical mean/max values and Study3/4 frozen endpoint distances reproduce to <1e-12; all source hashes unchanged; pooled RMS independently recomputed.
No old model calls are replayed. New module/API expense: 0 model calls, 0 tokens, USD 0.
Scores are relative geometric deviation, not confirmed visual errors: known outdoor-pot detection errors can score poorly. Small cross-boundary populations and median self-normalization remain limitations.
Production temporal_v2 spatial/full now includes the CPU stage; identity/presence early stops do not. Existing relationship/presence/appearance scoring and registration unchanged.

60 focused tests passed (9 displacement,23 temporal,4 scheduling,7 appearance integration,17 prompt alignment).
