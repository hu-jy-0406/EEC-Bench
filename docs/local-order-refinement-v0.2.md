# Local order extraction and verification v0.2

This refinement repairs missing local-axis queries and inconsistent evidence standards. It adds `support_center_order` with explicit scope `support_centers`; historical `axis_order / support_footprints` assertions remain unchanged. Ordering representative placements does not require the two complete contact footprints to be disjoint. This is an intentional semantic distinction, not a relabeling of old assertions.

## Run

Use a low-load compute node in an existing owned allocation. No GPU is used. The configured Codex service, Pillow and jsonschema are required.

```bash
python EECBench/scripts/run_local_order_refinement.py \
  --source-run EECBench/experiments/study_inconsistent_3/partial_scene_comparison_20260912/witness_v02 \
  --out EECBench/experiments/study_inconsistent_3/local_order_refinement_20260912/new_run
```

The output must be a fresh directory. The entry accepts a completed partial-scene run, not a particular scene or named object. It makes two isolated single-shot extraction calls and one independent verification call. No entity discovery rerun, no previous relation values, no desired verdict and no continuity policy are sent to extraction. Policy is applied by deterministic comparison. Every failure/status/raw response remains on disk; there is no automatic retry.

## Evidence and coverage

`local_order_contract.py` enumerates every pair of entities assigned to a shared support by prior support assertions or an anchored order, crossed with every existing physical axis of that support. A missing earlier axis-order edge no longer suppresses a query. Missing support membership or an entirely absent anchor remains a coverage limitation and is recorded when cross-shot alignment is impossible. The planner does not choose objects by name.

All original frames are supplied. For every pair, the first/last jointly visible frames also receive deterministic detector-box-union detail crops with context padding. Crops are nearest-neighbor 2x enlargements of original pixels, not generative enhancement. Their source regions, transforms and hashes are saved. Every relation still records every original frame; a crop does not justify copying a conclusion across occluded frames.

Each observation stores:

- Verified local physical axis and shared-support applicability.
- Actual visible diagnostic-part boxes for both entities.
- Separately identified bounds on representative grounded centers, with the inference and shape assumptions in the reason.
- Witness type: visible contacts, bounded center from parts, surface-boundary constraint, or unknown.
- A set of allowed order values and whether supported alternatives can reverse order.

Known values require actual localized evidence and defensible center bounds. Partial occlusion alone does not force unknown; a hidden lower endpoint also does not authorize guessing an object's unobserved height. Whole-image box centers, rim positions, screen left/right and occlusion alone cannot replace grounded surface order. Both surface directions must be considered when interpreting projected displacement.

Extraction and verification use the same semantics. Verification returns each side in its own local direction; only code applies axis and subject/object reversals. Per-frame extraction/verification disagreements are retained. Disjoint orders become conflicts only under `must_persist`; unknown and within-shot changes remain distinct.

## Outputs and verification

The two strict schemas are `schemas/local_order_extraction.v0.2.schema.json` and `schemas/local_order_review.v0.2.schema.json`. `comparison.json` contains the new local-order results. `combined_comparison.json` and `scene_memory.json` preserve baseline assertions and new evidence separately. The baseline lamp/tissue presence results are inherited, not rechecked by this stage. `viewer.html` embeds original pixels with diagnostic-part and inferred-center overlays; no external scripts or network are required.

```bash
python EECBench/scripts/audit_local_order_refinement.py RUN
python EECBench/scripts/render_local_order_evidence.py RUN
```

The local comparator can be replayed through `compare_local` or the audit without model calls. Source hashes, crop reconstruction, exact pair/axis/frame coverage, distinct tool-free contexts and baseline preservation are audited.

## Current validation and limits

Original Study3 Shot1/3: 13 + 7 queries, 120 frame records, 2 aligned cross-shot queries. Shot3's formerly missing transverse order is now extracted and accepted by verification. Shot1 extraction gives determinate orders, but verification rejects its unsupported narrow hidden-base estimate. Both cross-shot center-order comparisons remain unresolved. Independent extracted transverse orders are equal after physical-direction normalization; no successful detection of the user-identified reversal is claimed.

20 new comparator/contract tests, 29 prior comparator tests and 3 supplemental 2D-diagnostic tests pass. One additional visual call on five controlled planar diagrams correctly answers ten axis judgments: unchanged order after screen projection reversal, one-axis swap, partial outline occlusion and fully hidden unknown. This is a bounded controlled-image check, not natural-image generalization accuracy or a full independent two-stage visual benchmark.

An optional planar diagnostic accepts explicitly supplied approximate tabletop corners and checks sensitivity of grounded-center ranges under 2D homographies. It is not used to set model answers or final comparison labels; the current manually marked corners are not blind ground truth. No explicit 3D model, calibrated localization probability or complete global spatial solver is implemented.
