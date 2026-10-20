# Scoring efficiency v1

User direction (2026-09-21): autonomously reduce time/tokens, parallelize independent steps, and remove model judgments/outputs unnecessary for scoring. This is a scoped revision of the previous fixed pipeline, not permission to drop scoring evidence or change score definitions.

## Dependency flow

1. WeDetect and isolated per-shot clustering; calibration; sequential GPU geometry/box lifting. As each shot finishes, start its independent binary motion classification and negative-only within-shot relation review.
2. Initial all-entity identity and raw RoMa matching overlap. Correspondence lifting/fitting waits for both; aligned identity review waits for registration.
3. After final identity, run boundary consistency alongside global-entity export. Boundary presence runs alongside the two isolated local spatial observers; spatial verification waits for those observers, and final conflict gating waits for presence.
4. After global export, binding and appearance preparation run independently. DINO and appearance contact-sheet preparation may overlap; Codex appearance does not wait for DINO, but their report joins both.
5. Prompt alignment waits for binding and the per-shot geometry. Independent shot/scope batches run concurrently with separate contexts. Dependencies between claims are resolved inside their original scope, never across a parallel batch boundary.
6. Position scoring is local arithmetic on saved centers and confirmed identities/presence. Preserve every raw r_e. It adds zero model calls/tokens/API cost. Reporting joins all requested scores; there is no new fused episode score.

## Model work removed

- Aligned identity review no longer predicts why each final single-sided entity is missing from the other shot. Its former `noncommon_checks` was only schema-validated and saved; downstream presence does its own independent assessment. Do not synthesize these removed judgments as false or unknown outputs.
- Each initial identity audit now has one evidence explanation instead of separate visual, geometry and same-instance-motion explanations. The identity prompt still requires evaluating displacement/geometry and same-instance movement alternatives, especially before a split. Every original group remains audited, with unchanged inventory, witness, split and anchor validation.
- Boundary presence no longer returns the six spatial-only booleans. All five gates used by presence scoring, endpoint witnesses, prompt causality, status, reasons and uncertainty remain. Presence-only schema cannot validate a spatial event.
- Identity matching can copy unchanged full initial group records through checked IDs rather than reprint them. Changed groups and every initial-group audit are still explicit. Witness-bank encoding preserves all rectangles/observations.

## Evidence and scoring retained

Use the existing lossless tables/reference transport for boundary presence and prompt alignment. It removes repeated serialization, not frames/entities/geometry. Canonical input and raw model responses remain local. No model/reasoning downgrade: Astra/medium for identity, presence and prompt alignment; the previously selected boundary spatial Astra/low is unchanged.

Local spatial placements are retained: the validator uses them to enumerate common-support relations. Identity anchors, all original images, geometry diagnostics, motion classification, prompt binding candidates, appearance attribute scores and evidence required by scoring are also retained. No score-selected pruning, new verifier, changed registration objective or altered median/RMS formula.

## Runtime and rollback

Selected default runtime: `--runtime-profile scoring_efficiency_v1`; previous runtime: `--runtime-profile temporal_spatial_v1`.
Scheduling: `--schedule-profile parallel_v2` uses 6 stage workers, at most 8 reserved API slots, 3 appearance workers when alignment is enabled (otherwise the original 5), and 2 independent alignment workers. Boundary (3), appearance (3) and alignment (2) fit simultaneously. GPU peak remains one. `parallel_v1` restores the previous scheduler; `legacy` remains available.

Standalone alignment defaults remain serial/canonical for compatibility. Pass `--workers 2 --input-transport compact` explicitly. The integrated optimized runtime supplies these settings through its runtime and schedule profiles.

Validation and selection status: see `EECBench/experiments/pipeline_scoring_efficiency_20260921/REPORT.md`. Component replay timings must not be presented as a fresh end-to-end measurement. Record validation calls/cost separately from future production execution.
