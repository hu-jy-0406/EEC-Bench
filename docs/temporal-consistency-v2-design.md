# Temporal consistency v2 — accepted protocol and implementation

Status: all five decisions explicitly accepted by the user on 2026-09-20. Implemented with CPU regression and fresh Codex component validation recorded under `experiments/temporal_v2_validation_20260920`. See that directory for authoritative validation status; implementation is not a claim of fresh end-to-end GPU evaluation.

## Confirmed requirements

- Separate within-shot consistency from cross-shot boundary consistency.
- Within-shot motion classification represents what should reasonably move or remain stationary, supported by the normal prompt or a natural, causally plausible dynamic. Actual displacement alone must not exempt an anomaly.
- Keep expected motion and observed temporal changes separate. Preserve uncertainty and frame-specific evidence; do not reuse old actual-motion labels as the new classification.
- Keep every sampled frame in its existing fixed shot coordinate system. Compare per-frame entity-pair relative position vectors and submit direction-change candidates to Codex for adjudication.
- Review missing observations of expected-static entities for disappearance/appearance, viewpoint, occlusion, detector failure or uncertainty; a null detector box is not an absence verdict.
- Use raw per-frame evidence for temporal checks, not fused geometry or the subset surviving static fusion outlier rejection.
- Cross-shot identity includes all entities. Replace the both-shots-static scoring population with boundary-state evaluation; moving/mixed-motion labels alone must no longer exclude an entire identity group.
- Cross-shot spatial geometry comes from the preceding shot's final frame and following shot's first frame, after scene registration. Never substitute a fused box or another frame's representative box for a missing endpoint box.
- Keep same-scene comparison scope and normal prompt explanations, including intervening-shot facts. Singleton scenes still need within-shot evaluation.
- Appearance scoring is outside this revision.
- Existing numerical registration objective remains the unweighted sum of unsquared Euclidean distances over ALL fixed selected 3D correspondences, with positive scale, gravity yaw and translation. No residual trimming, robust loss, squared-distance substitution or reweighting.
- Preserve both explicit alignment choices, roma_fps32 and codex_direct; no automatic switching. The default remains roma_fps32.

## Accepted decisions

1. ACCEPTED: full 3D vector cosine < 0 over all temporal keyframe combinations.
2. ACCEPTED: temporal intervals, preserving static-period checks for objects later legitimately moved.
3. ACCEPTED: retain current full-frame anchor matching, all 36 RoMA frame combinations and FPS32 fitting; use exact endpoint geometry for scoring.
4. ACCEPTED: aggregate presence once per entity per shot and spatial once per entity pair per shot, retain all temporal event details and existing score formulas; report boundary comparisons separately.
5. ACCEPTED: endpoint-state decisions with other frames as contextual witnesses; prohibit replacement of endpoint states or geometry.

## Original implementation paths adapted

- `scripts/run_gs_integrated.py`: previously ran geometry/motion only for shot1/shot3, exits after discovery for singleton-only cases, and reports one pair. New within-shot work must include every supplied shot, including the current auxiliary shot2; scene transitions must remain explicit.
- `scripts/prepare_gs_integrated.py`: calibration and inputs previously filtered to shot1/shot3. Generalize for within-shot processing without treating different scenes as registrable.
- `scripts/run_gs_motion_fusion.py` and `prompts/gs_flow1/shot_motion_isolated_v0.2.txt`: the previous label meant observed motion anywhere in shot. Introduce an explicit expectation contract and prompt input instead of silently changing the meaning of historical artifacts.
- `scripts/build_three_method_static_scenes.py`: quality-weighted fusion rejects center outliers; this must not remove temporal evidence. Whether fusion remains auxiliary to identity/registration depends on decision 3; endpoint scoring does not use it.
- `scripts/gs_flow1_evaluator.py`: presence and spatial scoring call `static_matching`; spatial vectors use node-level fused/representative boxes. Replace those scoring inputs for the new protocol, preserve complete identity and missing-geometry records.
- Existing presence conflict gates demand at least two witness frames per shot. Explicitly resolve decision 5 before adapting these gates.
- Existing spatial review includes independent local-support and normal-prompt gates. Preserve them where applicable, explicitly document any endpoint-specific adaptation; do not quietly bypass them.
- Model calls must retain fresh isolated per-shot contexts, original images, frozen inventories, canonical payloads, responses and actual time/token accounting. Cross-shot information belongs only in downstream boundary judgments.

## Validation requirements

- Unexpected swap stays eligible despite observed motion; legitimate pickup is treated according to the accepted temporal policy.
- Disappear/reappear candidates survive detector gaps and fusion-outlier flags, while judgments retain occlusion/unknown alternatives.
- Camera motion alone is not treated as world movement; missing/degenerate 3D vectors cannot become fabricated numerical evidence.
- Boundary checks select exact endpoints, preserve all identity groups and never backfill from another frame.
- Singleton scenes and auxiliary shots receive within-shot checks; different scenes are not directly registered.
- Existing registration solver/objective regression checks remain unchanged; selected-population and source provenance are recorded.
- Unfinished or failed stages must not be reported as completed scores. New-version outputs and historical fixed-baseline outputs stay distinguishable.


## Execution and artifacts

The integrated CLI now defaults to `--consistency-protocol temporal_v2`. Continue to select `--alignment-method roma_fps32` or `codex_direct` explicitly as requested. Use `--consistency-protocol flow1_fused_v1` only to reproduce the historical fused-static baseline. `--plan-only` is read-only. Fresh directories remain mandatory.

Every supplied shot, including singleton scenes and formerly auxiliary Shot2, receives its own calibration, Pi3X, Boxer, fresh expected-motion judgment and within-shot review. Own-shot classification may read the normal global/own-shot prompt but never another shot's actual evidence. Motion is represented over consecutive sampled-frame intervals. Full temporal comparisons span every pair of keyframes; a comparison is eligible only when both entities are expected static throughout the intervening intervals. A reasonable-motion interval makes that comparison exempt, while uncertainty remains unknown. This does not erase earlier static comparisons. Unsampled motion timing remains uncertain.

Expected motion is the new scoring classification. `observed_motion_status` remains separate. `motion_status` and `expected_motion_status` both express expected reasonable motion. A separate `anchor_observed_static` flag additionally requires actual stable observations for registration anchors. An expected-static object with an actual unexplained jump cannot become a registration anchor. Fused boxes remain auxiliary to identity/registration; no temporal or boundary score reads them.

Boundaries follow manifest chronological order within each scene (e.g. room Shot1 -> room Shot3 across an intervening garden shot). For more than two occurrences compare consecutive scene occurrences, not every nonadjacent scene pair. Pair folders explicitly map original shot IDs to the unchanged registration adapter's `shot1`/`shot3` aliases; record this mapping and input hashes. No global multi-shot identity merging is claimed. Every pair performs its own full identity, unchanged chosen registration and aligned identity review.

`within/SHOT/proposals.json` saves every temporal pair, vectors, eligibility and cosine. `within/SHOT/results.json` saves one presence unit per entity and one spatial unit per entity pair plus all adjudicated events. `pairs/PAIR/boundary/proposals.json` saves exact boundary observations, all identities and pair vectors; `boundary/results.json` saves boundary scores/events. Missing endpoint geometry remains null. All original per-frame evidence is retained even if auxiliary fusion rejected it.

Presence missing-observation candidates are reviewed at every expected-static sampled frame without a retained detection, including before first observation and after last observation. Conflicts require a target missing-frame witness and an observed contextual reference in the same shot. Boundary presence conflicts require BOTH exact endpoint witnesses; extra context cannot replace either. Spatial boundary conflicts also retain separate isolated local-order observations, verified physical support/reference and the normal-prompt gate. Tested endpoints cannot serve as their own independent anchors. Uncertain identity/visibility/depth/causality remains unknown.

Event review batches contain at most 32 proposals, preserving all proposals, complete original images and own-shot evidence. Batching does not select/drop candidates. At most two CPU/API stages run concurrently and never two GPU stages. Raw RoMA can overlap initial identity after pair preparation; filtering/fitting waits for identity anchors. All GPU launches retain the existing UUID/idle-process guard. Timing, actual usage, failures and hashes are saved; failed/unfinished stages do not yield completed scores.

Scores retain the old formula and coverage convention: N=C+K+U, E excluded; score=100*(1-K/N) when presence has decided evidence, otherwise null. Completed spatial evaluation with K=0 retains score100 even with coverage0. One entity/pair with multiple conflicts contributes K=1. Remaining unresolved temporal comparisons preserve unknown coverage unless a conflict already establishes the unit violation. Parts and boundaries remain separate; no new combined overall score is invented. Negative cosine detects directional disagreement (>90 degrees), not every possible displacement or transient event between sampled frames.

Input manifests must include the actual shot opening and ending frames when claiming video-boundary evaluation. With keyframes alone, the runner can only select the first/last supplied frames; it cannot infer omitted video endpoints. Frames with zero retained detections save empty Boxer observations instead of crashing or fabricating boxes.

For spatial boundary conflicts, both endpoint identity groups must additionally have supported compatible boundary presence. This retains the original joint-presence gate while preserving all identity groups and numerical candidates in the new audit ledger.

Fresh full Study2/Study3/Study4 validation completed 2026-09-20: `experiments/temporal_v2_study234_full_20260920/REPORT.md`. All shots and boundary stages ran from fresh WeDetect outputs; inspect unknown/exempt coverage before interpreting scores. Study4 is the original `experiments/study3-concise-mtd-local/` dataset.

## 2026-09-20 user correction: restore original boundary spatial review

Boundary comparison states remain the preceding tail and following head with raw per-frame boxes. Evidence collection uses all original keyframes. The production adapter `gs_boundary_spatial_review.py` now reuses the original Flow1 local-observation and spatial-verification prompts/schemas verbatim, plus an explicit endpoint scope note. Original per-axis reliability and >=2 distinct-frame evidence rules (including endpoint) are restored; uncertain vertical order does not veto a supported horizontal reversal. This supersedes the initial pair-wide LOCAL reliability / combined temporal spatial CHECK implementation for cross-shot boundaries only. No new evaluation results are implied; see `experiments/boundary_spatial_prompt_restore_20260920/REPORT.md`.

## 2026-09-20 user revision: spatial anomaly fraction, no coverage

For both within-shot and same-scene boundary spatial evaluation, report confirmed anomalous entity pairs divided by all enumerated entity pairs; spatial score is100*(1-ratio). Each pair contributes at most once. Exempt and unresolved pairs remain in the denominator, with only confirmed conflicts penalized. Nonnegative comparisons are normal no-anomaly outcomes; retain missing/uncertain evidence as diagnostics. Spatial coverage and identification intervals are removed. Empty pair population returns null. Existing pair-generation rules, presence scoring, restored spatial prompts and evidence gates, and registration remain unchanged. See `experiments/spatial_anomaly_fraction_20260920/REPORT.md`.
