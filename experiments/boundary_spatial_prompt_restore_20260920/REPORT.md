# Restore original spatial review for temporal boundary targets

User authorization (2026-09-20): restore original spatial prompts; judge entities at preceding tail/following head while allowing other keyframes as evidence. Do not independently modify prompts or decision semantics in future.

## Implementation

- `scripts/gs_boundary_spatial_review.py` reuses `prompts/gs_flow1/gs_relation_shot_v1.txt` and `verify_cosine.txt` verbatim, plus a separately identified endpoint-scope adapter. Both base texts were verified as exact prefixes of the archived successful Study2 FPS32 requests under `alignment_full_four_20260919`.
- Original `SHOT_SCHEMA` and Flow1 `VERIFY` schema restored, including independent per-axis center-order reliability. A reliable horizontal reversal is not vetoed by unknown vertical order. Original support, geometry, viewpoint, causal-prompt and witness checks remain.
- Original >=2 distinct witness frames per side retained, including endpoint witnesses. All original keyframes/own-shot frame evidence are available for determining center order and resolving occlusion. Local reviewers remain isolated by shot.
- All numerical comparison geometry remains the exact tail/head frame geometry. The graph's top-level geometry sent to these reviewers now explicitly equals its target-frame geometry; full frame_evidence is retained separately. No fused-box substitution, missing-endpoint filling, transform refit, score-formula change, or static-only population filter.
- Boundary presence review still uses existing temporal presence rules. Spatial review is now separate and uses the original spatial-only schema rather than the combined presence/spatial CHECK schema. Boundary joint-presence gate remains. Within-shot processing is unchanged.
- Run artifacts store original prompt hash, full adapted prompt hash, original per-axis responses and final verification. Event summary fields remain report-compatible. Historical outputs, snapshots and unused temporal_local_order_v2 prompt are untouched; the latter is no longer called by boundary processing.

## Validation

27 CPU tests passed on existing owned allocation196093/node197, one CPU, nice19, GPUs hidden: 19 original temporal tests plus8 new spatial-restore tests. New tests cover original-prompt preservation, endpoint rather than fused geometry, all-keyframe evidence and shot isolation, independent axis reliability, endpoint witnesses plus contextual witnesses, missing references, prompt exemption, joint presence, original schema routing, and the boundary-stage aggregation/report interface. Model calls were mocked in tests. Source text matches archived requests. Git diff whitespace checks passed.

No new model calls or GPU inference. No fresh Study2 result or recovered-detection claim. Historical graph populations still include rugs; the separately authorized floor-covering filter applies to new entity discovery.
