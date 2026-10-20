---
name: gs-consistency-flow1
description: Match all entities across same-scene shots and evaluate static-entity presence and spatial consistency using full initial identity matching, structural-anchor registration, aligned identity review and one presence judgment. Use for same-scene shot comparisons after isolated shot graph construction; single-shot discovery uses wedetect-shot-entities.
---

# Cross-shot consistency — Flow1

Use `EECBench/configs/gs-consistency-two-scores.v1.json` and the corresponding [specification](../../docs/gs-consistency-two-scores-v1.md). Flow1 is the selected protocol. Flow2 remains an experimental alternative in `EECBench/experiments/study2_flow2_separate_ab_20260919`; do not substitute it automatically.

## Inputs and invariants

- Preserve original JPEG bytes and resolution. Finish each shot's discovery, clustering, camera-compensated motion classification and fixed scene graph independently before cross-shot work.
- All frozen entities (static, moving and motion-unknown) are identity subjects, including entities without 3D geometry. Presence/spatial scoring uses the static-only projection of the reviewed map; exclude entire mixed-motion groups without converting a known moving counterpart into an apparent absence. No entity addition, within-shot merge/split, box repair or motion relabeling in cross-shot stages.
- Keep per-frame camera poses in each shot's fixed scene coordinates. Register Shot3's scene into Shot1's fixed scene, with positive scale, gravity-axis yaw and translation.
- Match only within a scene. Explicit manifest `scene_id` values define membership; single-shot scenes skip cross-shot matching. The current geometry adapter supports Shot1/Shot3; legacy manifests treat optional Shot2 as a singleton scene. Reject unsupported multi-shot combinations rather than silently omit entities.
- Appearance drift alone must not force an identity split when other evidence supports the same physical instance. Appearance scoring is a separate downstream stage.
- Normal story Prompt facts include relevant intervening shots and apply to generated, unmentioned objects too. Do not supply expected defects, prior final verdicts or desired scores.

## Stage order

1. **A and A′:** independently judge full cross-shot identity for every entity. Select high-confidence structural pairs static in both shots with available geometry as registration anchors. A motion-label difference does not prevent an identity match. Similar category and proximity do not establish identity; ambiguous/scope-mismatched identities remain unresolved.
2. **Registration:** select the fixed method requested by the user through `--alignment-method roma_fps32|codex_direct`. FPS32 uses RoMa, static anchors and the exact 3D distance-sum objective below; direct Codex uses original images, normal Prompt and own-shot geometry to estimate the same transform model without RoMa, anchor input or numerical optimization. Preserve the common initial identity call in both methods. Record method-specific diagnostics honestly; direct registration has no RoMa fitting errors. Freeze the resulting transform for all entities.
3. **Aligned A/A′ review:** fresh context reviews every initial group using all originals, paired displacement/extent diagnostics, projections, geometry uncertainty and normal Prompt. Keep/split/reassign/mark unknown with witnesses. Large displacement alone cannot split a physically identical moved object. Reassess objects on disputed supports independently. Assess each resulting single-sided group provisionally; different instances alone do not establish viewpoint exemption. Remove invalid anchors from the reviewed identity map, record their original point contribution, and preserve the frozen transform.
4. **B:** one fresh call receives the static-only projection of reviewed matching and evidence and judges every group in that projection. The complete identity map remains available for appearance evaluation. Common entities: assess whether an object should have left the scene but remains. Noncommon entities: strictly viewpoint, motion or inconsistency; detector gaps and insufficient evidence remain unknown. Confirm conflicts only with original-frame location/visibility evidence, exclusion of occlusion/detector gaps, and specific Prompt motion-cause review. The judgment must pass existing evidence gates; otherwise unknown.
5. **Spatial:** use reviewed, reasonably common static groups. Compute all unordered pair cosines in the shared scene frame. Review only negative proposals through independent per-shot local support evidence and final original-frame/Prompt review. Do not penalize a Prompt-explained move. Do not add a nonnegative review stage.
6. Report the two scores separately, confirmed reasons, C/K/U/E, coverage, all unknowns and stage time/token use. Preserve the existing score formulas; completed spatial evaluation with no confirmed conflict scores 100. A failed or unfinished run is not a completed 100.

## Integrated execution from original keyframes

Use `EECBench/scripts/run_gs_integrated.py` to connect fresh WeDetect, compact isolated clustering, per-frame geometry, isolated motion/static fusion, and Flow1 through one B judgment and the original spatial stage. Follow [the integrated interface](../../docs/gs-integrated-flow1.md) for manifests, existing allocation/GPU guards, fresh output directories and time/token reports. The default run produces both final scores. Use `--stop-after identity` when only cross-shot identities are requested; use `--stop-after presence` when only classification is requested. Single-shot discovery alone still stops at clustering.

## Execution and efficient transport

Run a prepared case through `EECBench/scripts/run_gs_flow1_stage.py CASE STAGE`, where STAGE is `match`, `review_identity`, `presence` or `spatial`. Matching precedes registration; `review_identity` requires the saved registration. Run CPU orchestration within an existing owned allocation. GPU prerequisites remain governed by project cluster instructions.

The stage entrypoint reads the selected transport profile from the configuration. The selected runtime profile is `temporal_spatial_v1` in `EECBench/configs/gs-runtime-profiles.v1.json`; see the temporal cost section below. `safe_spatial_medium` preserves the pre-optimization baseline. Legacy Flow1 model transport remains the same; temporal boundary spatial calls use the explicitly validated stage overrides. `--runtime-profile baseline` restores the previous sequential execution and transport. Only validated stages use compact transport. Compact transport preserves decision prompts, model-response schemas, stage isolation, evidence gates and numerical calculations. Presence aggregation records one review under `single_presence_witness_v1`; it does not report cross-review agreement.

- Keep full canonical `input.json`, original images and geometry locally; save the actual model `wire_input.json`, prompt, response and usage.
- Share exact repeated subtrees and tabulate repeated field names without dropping rows or changing original values.
- A box's corners may use a derived representation only when its original center, size and rotation reconstruct every corner within 1e-9 scene units. Preserve the original full corners for numerical stages; retain literal corners when this check fails.
- Do not lower image quality, drop frames or entities, round defining geometry or skip witnesses to save tokens. Keep the selected model and reasoning setting. A lower-effort/model profile requires per-entity and final-gate validation; equal aggregate scores alone do not establish equivalent quality.
- Explain each required decision concisely while retaining its actual visual and Prompt evidence. Deterministic encoding/decoding belongs in code, not additional model calls.

Use fresh output directories for changed prompts, schemas or transport profiles. Reuse only explicitly frozen upstream artifacts with hashes recorded. Validate complete identity populations and per-group classifications, not only aggregate scores, before adopting an optimization. Preserve canonical transport as the fallback and distinguish validation cost from per-run cost.

## Runtime and cost scope

- Raw RoMa image matching may overlap isolated motion classification and initial identity calls after per-shot geometry completes. Anchor filtering, point lifting and fitting still wait for both image matching and initial identity. Run only one GPU stage at a time and retain the existing prelaunch GPU guard.
- Optional Shot2 in the original-JPEG manifest receives independent WeDetect detection and clustering only. Calibrate, reconstruct, classify motion and compare only Shot1/Shot3; include Shot2's clustering in the total token/cost report.
- Efficient wire outputs may abbreviate keys, reference original attachment indices and share identical witnesses. Restore complete canonical responses and validate original inventory, witness and Prompt gates before scoring. Keep unused wire records in the saved raw response; they are not decision witnesses. Invalid references fail.
- Faster identity/presence profiles remain experimental: Study2 tests changed some unknown/viewpoint classifications even when scores matched. Preserve the selected identity/presence implementation. See the [efficiency comparison](../../experiments/gs_latency_cost_20260919/REPORT.md).
- Distinguish actual model-stage latency from full-pipeline estimates that reuse GPU timings. Report validation-call cost separately from one production evaluation, and API price equivalents separately from actual CLI billing.

## All-entity identity validation boundary

`matching.json` and `identity_review.json` contain the complete identity population; `matching_static.json` is the downstream static scoring projection. Preserve motion labels, original observations and per-frame trajectory evidence. Null 3D geometry remains null and does not remove an entity. Historical static-population replay quality and timings do not validate the expanded population; use a fresh case for new model calls.

## Registration objective correction (2026-09-19, explicit user instruction)

For `roma_fps32`, use `scripts/register_gs_3d.py`: minimize the unweighted sum of **unsquared 3D Euclidean distances** over every selected point pair, `sum_i ||s Rz(theta) Q_i + t - P_i||_2`. Keep the selected population fixed; no residual trimming, clipping, robust loss or group/tile reweighting. Include all correspondence rows, including the historical train/holdout partitions; those partitions are descriptive only and MUST NOT be presented as independent holdout validation. Reprojection is diagnostic only. Keep the existing positive scale [0.1,10], gravity yaw and translation model. Multistart numerical optimization does not certify a global optimum. Historical robust reprojection fits are legacy results, not the current default.


## FPS32 default (2026-09-19, explicit user selection)

The default registration now selects up to32 pairs with the validated deterministic joint-endpoint6D FPS (confidence floor0.2 unchanged), from the full valid lifted anchor pool across both legacy partitions. If3–31eligible pairs are available, use all; fewer than3fails. Every selected pair contributes equally to the exact unsquared3D Euclidean-distance sum, with no residual-based deletion or reweighting. `register_gs_3d.py --sampling all` retains full-pool fitting for explicit comparisons. Save selected row indices, separate selection/optimization timings, selected fitting error and full-pool diagnostics. Legacy partitions are NOT independent holdouts. RoMA still uses36pairs for the current6×6inputs, precise setting and5000sampled matches perpair; reducing upstream RoMA work is not yet adopted.


## User-fixed alternatives (2026-09-19)

Both integrated pipelines are fixed after the completed Study2/Study3 four-run validation. Follow [registration-options.md](../../docs/registration-options.md). Select the user's requested optimization (`roma_fps32`) or direct Codex (`codex_direct`) method. If unspecified, retain and announce the existing FPS32 default. Never automatically fall back, blend, run both or choose by score. Preserve the shared stages, model/runtime settings and scoring gates; algorithmic changes require a user request or confirmation. This does not require repeated permission for ordinary execution of either authorized pipeline. Appearance remains outside the fixed scoring scope.


## Temporal consistency v2 — explicit user revision (2026-09-20)

- The user approved all five design decisions in `EECBench/docs/temporal-consistency-v2-design.md` (relative to workspace root). `run_gs_integrated.py` now defaults to `--consistency-protocol temporal_v2`; `flow1_fused_v1` preserves historical scoring.
- Classify reasonable EXPECTED motion by time interval, separately from actual observed changes. Unexpected jumps must not self-exempt. Use raw per-frame geometry for all keyframe-pair cosines; negative cosine proposals and expected-static missing observations receive Codex review. Every shot, including singleton/auxiliary scenes, receives within-shot evaluation.
- Across shots compare all reviewed identities at the exact preceding tail/following head frames within the same scene; no both-shots-static filter, no fused-box substitution, no replacement of missing endpoint boxes. Other frames are contextual witnesses only. Compare consecutive scene occurrences in manifest order with explicit pair-local aliases.
- Registration still uses all original keyframes, unchanged RoMA 6x6 matching / FPS32 / exact unsquared distance sum, or the explicitly selected direct Codex method. Auxiliary fusion and observed-motion fields serve only identity/anchor registration and never select the scoring population.
- Preserve separate within-shot entity/pair scores, boundary scores, full event ledgers, original witness/causal/local-support gates adapted explicitly to endpoint witnesses, uncertainty and coverage. No new overall score, appearance score, model downgrade or objective change.
- Read the validation report/status before claiming an actual end-to-end evaluation; cached-geometry component validation is not a fresh frontend/GPU run.


## Temporal cost optimization — user-authorized, validated 2026-09-20

- Previous default `temporal_cost_v1` (explicit interval rollback): keep GPT-6 Astra throughout. Clustering, expected motion, within-shot review, initial identity, aligned identity review and boundary presence stay medium with their original prompts and transport. Never globally lower effort or change an exemption/unknown to save money.
- Only `boundary_local_shot1`, `boundary_local_shot3`, and `boundary_spatial_verify` use efficient input/output transport and low reasoning. Lossless references/tables and reconstructible OBB corners retain all defining geometry numbers; no frame/entity/box removal or rounding. Original decision prompts remain verbatim prefixes. Short output keys and shared original-frame witnesses decode into the full original schemas before unchanged evidence gates run.
- The two local calls may run concurrently in fresh isolated contexts, each receiving only its own shot. Write the shared prompt before launch; final review waits for both validated local results. No shared cross-shot judging context, GPU overlap, or numerical registration change.
- Strict frozen-input quality screen on Study2/3/4: spatial compact/medium, compact/low and efficient/low preserved every spatial event status; select efficient/low by aggregate API cost. Composing it with untouched stages preserves all final event statuses, units, denominators and scores. Full motion/presence/within compression was rejected because individual labels changed even when headline anomalies or scores matched. Do not promote the broad experimental profiles.
- Evidence: [validation and cost report](../../experiments/temporal_cost_quality_20260920/REPORT.md). This is fresh model COMPONENT validation on frozen original upstream data, plus exact composition checks, not a new full GPU/end-to-end run. Full-pipeline cost/time are explicitly composition estimates; report actual validation expense separately. Always accompany token counts with corresponding API cost and distinguish standard list-price equivalents from billing.
- Explicit rollback: `--runtime-profile safe_spatial_medium`. Original study runs and source snapshots remain immutable.


## Whole-shot binary motion — explicit user revision (2026-09-20)

- Default runtime is now `temporal_binary_v1`. This supersedes the interval expected/observed motion requirement and the earlier default `temporal_cost_v1`; that profile remains explicit interval rollback. Keep GPT-6 Astra/medium for this classification.
- Exactly one moving/static label per entity per whole shot. Moving requires an applicable in-shot Prompt action or original-frame-grounded natural dynamics; category movability, camera motion, geometry noise or unexplained drift do not qualify. No supported legitimate cause means static, including ambiguous/unexplained changes. No separate observed classifier or interval rows. Retain one short reason and necessary fact/frame references.
- Keep all own-shot original frames and frozen entities, unchanged 2D observations and defining 3D/camera data. Compact tables remove repetition; omit redundant corners only after <=1e-9 reconstruction verification, otherwise preserve literals. Full canonical classification input remains saved. Do not round geometry.
- Within-shot eligibility now uses the whole-shot binary label. Legitimate movement anywhere in a shot exempts that entity's whole-shot static checks; earlier static subintervals are no longer separately classified. Unexplained drift stays static and eligible. All entity pairs remain in the existing spatial-score denominator. Cross-shot tail/head comparison still includes ALL reviewed identities regardless of motion, with all other frames available as contextual evidence.
- Local spatial normalization must preserve the raw row subject/object/order/prose/witnesses together; put swapped-endpoint/negated-order arithmetic only in a separately labeled canonical_relation. Never flip an order while leaving it attached to opposite endpoint IDs. Numeric signs and evidence gates are unchanged by this representation fix.
- Binary static is NOT observed anchor certification. The existing matching call evaluates actual physical stability and usable geometry under its original rules, considering original images, occlusion, reliable frames and auxiliary fusion. Do not impose a new every-frame raw-box stability requirement. `match_binary_v1.txt` preserves the original matching prompt prefix and only adapts the field interpretation. Original spatial/presence prompts, gates, registration method/objective and scores stay unchanged.
- Validation/report: [validation report](../../experiments/shot_binary_motion_20260920/REPORT.md); protocol: [binary motion contract](../../docs/shot-motion-binary-v1.md). Nine classifier calls preserve all132 whole-shot labels; corrected CPU/API downstream replays preserve all confirmed identity links and all confirmed anomaly sets on Study2/3/4. Study3 side-table plants change from unmatched to ambiguous (not a confirmed match), and some non-anomaly unknown/exempt diagnostics differ; do not claim all detailed outputs are identical. Frozen detector/geometry/rawRoMa inputs were reused; no fresh GPU frontend or end-to-end wall-clock claim. Include failed/corrective validation expenses separately from production cost.


## Within-shot missing-box review paused — user revision (2026-09-20)

Selected temporal_binary_v1 sets within_presence_review=false. Exclude within-shot missing-observation events from model review; preserve raw null boxes and all original spatial comparisons. Emit presence=null and explicit not-evaluated status, never a completed100. Only negative eligible cosine events receive within-shot review; empty batches make no model call. Cross-shot presence and its spatial evidence dependency remain unchanged. Model prompts/settings remain unchanged. Other runtime profiles preserve the previous within-presence behavior. This supersedes the earlier within-shot missing-observation review requirement for the selected runtime. Frozen deterministic regression preserves all9 shot spatial outputs; fresh reduced-input model quality/cost has not been measured.


## Negative-only within-shot review — explicit user revision (2026-09-20)

- Selected runtime is temporal_spatial_v1. This supersedes temporal_binary_v1 as default, preserving whole-shot binary motion and all cross-shot settings. Keep Astra/medium for within review; temporal_binary_v1 remains explicit generic-review rollback.
- Within agent reviews ONLY eligible negative-cosine spatial events, one check per event; no missing-box/presence judgment, motion relabeling or identity task. No candidate means no API call. Preserve raw null observations and all-pair cosine/scoring population. Within presence is null/not_evaluated_user_disabled, never a fabricated100.
- Use gs_temporal_within_spatial.py and within_spatial_v1.txt. Retain all original own-shot frames/entities/per-frame defining geometry/cameras and uncertainty diagnostics. Omit duplicated fusion/motion metadata and use compact tables/shared witness indices. Decode to original witness/normal-prompt/conflict gates; no gate or registration/scoring weakening. Preserve full canonical input locally.
- Frozen comparison:16 spatial events retained,14 exact statuses;Study2 two unknown→occlusion-exempt. Known confirmed anomalies/scores unchanged, not all diagnostics identical. Cost661847tokens/$8.12231→145923tokens/$1.61567; summed call time1432.865→143.922s. This includes removing109 presence events, not merely shorter prompt text. No positive within-shot anomaly examples in that test, so no general recall guarantee.
- Fresh complete Study2/3/4 runs succeeded. Known lamp/tissue and green-mug/pen-holder anomalies preserved; all9 within scores100; Study4 no false alarm. Existing collection clustering changed populations/identity denominators; Study4 cup collection versus singleton scope mismatch excludes that cup pair, NOT a reproduced explicit swap exemption. Do not claim every historical score/unit/identity unchanged.
- Full measured total2174827tokens/$25.099798, individual1268.49/1301.85/1014.83s, parallel1306.47s. Full+screen validation2320750tokens/$26.715468. Standard API equivalents not bills. Report: EECBench/experiments/within_negative_review_20260920/REPORT.md; specification: EECBench/docs/within-negative-spatial-v1.md. All work finished; no inference process remains from this run.
