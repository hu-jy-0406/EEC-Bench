# Gravity-free spatial pipeline v1

User-authorized experiment, 2026-09-21. The established gravity-aligned production default remains available and unchanged. Select both `--alignment-method roma_fps32_free3d` and `--runtime-profile gravity_free_v1` (the former automatically selects the latter when no runtime is specified).

## Flow

1. Fresh WeDetect and isolated shot clustering, with original candidates and boxes.
2. Skip GeoCalib entirely: neither its model weights nor its predictions are read. Pi3X runs with its existing no-prior inference. Retain its native arbitrary shot axes and the existing per-shot translation of origin; do not pretend Z is physical up.
3. Boxer uses the same weights and observations but receives an explicit camera-oriented inference frame through `gs_boxer_camera_frame.py`. This bypasses its otherwise implicit world-Z gravity alignment. The local axes are camera right, camera forward, and negative camera down; they are a model-input convention, not an estimated physical-up direction. The existing checkpoint was trained in gravity-aligned frames, so this is a quality-sensitive change that requires evaluation. Isolated whole-shot motion classification, all-entity identity matching, and raw RoMa correspondence extraction otherwise retain their settings. The matching prompt explicitly treats coordinates as arbitrary.
4. Retain the original confidence floor 0.2 and deterministic joint-endpoint FPS selection of up to 32 rows. Fit `sum_i ||s R Q_i + t - P_i||_2`, with proper full `R in SO(3)`, positive scale bounded to [0.1,10], and free translation. Every selected row has weight one; no residual rejection, squared-distance substitution, or robust loss. Kabsch plus cube rotations initialize 25 exact-objective optimizations. This is not a certificate of global optimality. Collinear/coincident inputs fail explicitly.
5. Freeze this transform before final identity review. Per-frame center vectors still generate negative-cosine proposals. Within-shot negative-only review and entity-displacement scoring remain unchanged.
6. For boundary proposals, run two isolated own-shot original-image observations concurrently. Each establishes the exact target endpoint state from at least two original frames, including the endpoint. Evidence describes positions relative to corresponding support features or independent landmarks; no prescribed up/horizontal/vertical axes, image-vertical substitution, or additional plane fitting.
7. One final cross-shot review checks original pixels, independently observed layouts, frozen identity and normal-story causes. Confirmed conflict requires common support and corresponding external-reference identities, valid center semantics, visual change, exclusion of viewpoint/geometry-error explanations, endpoint witnesses, joint presence, and no prompt-authorized causal explanation. Negative cosine alone cannot establish conflict. Unknown evidence is retained without penalty.
8. Existing spatial denominator and displacement formulas are unchanged. Full runs continue into existing downstream stages; `--stop-after spatial` tests detection through spatial/displacement without unrelated appearance or prompt-alignment calls.

## Invocation

```bash
python EECBench/scripts/run_gs_integrated.py \
  --manifest MANIFEST.json --narrative NARRATIVE.json --output NEW_RUN \
  --alignment-method roma_fps32_free3d --runtime-profile gravity_free_v1 \
  --stop-after spatial --gpu PHYSICAL_INDEX --gpu-uuid VERIFIED_UUID
```

Run inside a verified owned Slurm allocation. The runner checks GPU occupancy before every GPU stage. Original `roma_fps32` with the selected production runtime restores GeoCalib and gravity-yaw fitting. Mixed free/native and gravity/yaw configurations fail explicitly.

## Validation interpretation

Compare fixed correspondences first to isolate solver changes, then fresh Study2/3/4 runs to test the whole branch. Smaller fitted residual is not proof of correct physical registration; also inspect full-pool diagnostics, original images, identities and anomaly results. Full-pool/legacy partitions are not independent ground truth or held-out validation. Coordinate units are not calibrated meters.

The retained FPS implementation uses coordinate-wise median centering before isotropic normalization. Its selected rows can change after arbitrary independent coordinate rotations. This experiment preserves that existing algorithm; the full-rotation objective on fixed rows is gauge invariant to numerical precision. Fresh-run population and VLM variation must not be attributed solely to removing gravity.

Experiment artifacts: `EECBench/experiments/gravity_free_pipeline_20260921/`. The final report records actual completion status, known token usage and estimated API-equivalent USD separately from CPU-only solver validation.

## Completed Study2/3/4 result

See [the experiment report](../experiments/gravity_free_pipeline_20260921/REPORT.md). All three fresh spatial pipelines and 282 regression tests passed execution checks, but the branch is **not promoted**: both prior mug/holder spatial conflicts became unknown despite surviving negative-cosine proposal screening. Study4's prompt-authorized cup swap was exempted. No appearance/prompt-alignment validation was run. Full-rotation fitting improved fixed-point residuals, but this is not sufficient to establish equivalent evaluation quality. The additional Boxer coordinate-gauge probe passed; its gravity-free predictions still differ from the gravity-informed baseline.
