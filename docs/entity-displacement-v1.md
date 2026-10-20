# Entity displacement position consistency v1

User-approved on 2026-09-21. Selected production temporal_v2 spatial/full runs now execute `scripts/gs_entity_displacement.py` as a CPU-only stage; identity/presence early stops and historical flow1_fused_v1 remain unchanged. No model calls, new tokens or API charge. Existing relationship, presence, appearance and prompt-alignment scores remain separate.

## Measurement and population

Within each shot, use frozen whole-shot static labels. Retain every visible original box with finite raw 3D center, including observations not selected by auxiliary fusion. No interpolation, box substitution or residual-based removal. For n>=2, save all unordered frame-pair Euclidean distances, their mean d_e, maximum and witness frame IDs. n<2 is unscored, never zero.

Across each consecutive same-scene boundary, require final confirmed one-to-one identity and static labels in both shots. Use exactly preceding tail / following head observations, with the existing frozen scale/rotation/translation applied through the unchanged boundary geometry adapter. No fitting or anchor changes. Missing endpoints remain unscored, no nearest-frame replacement. Moving, mixed-motion, unmatched, ambiguous and scope-mismatched identities are excluded from this new component, not from existing relation evaluation. Restore pair-local aliases in exported IDs.

Reuse already accepted entity-specific boundary presence reviews whose cause is reasonable_motion and whose prompt gate explicitly accepts explains_change. These may exempt a both-static entity with a known legitimate between-shot move. Do not infer new movement, scan narrative keywords, exempt from viewpoint/occlusion alone, or use a pair-wide reason to excuse each member. Existing judgments may lack an explicit between-shot motion determination: no new classifier is introduced, and static status alone is not certification that a between-shot move was prohibited. This residual limitation is saved in the output.

Both prompt-bound and prompt-unbound entities participate. Static labels mean expected reasonable motion, not measured physical stability. Collection representatives preserve original scope and may carry detection-scope noise.

## Normalization and scoring

For each individual shot or boundary separately:

- b = median of that scope's eligible measured entity distances; each entity contributes once.
- r_e = d_e / b. Within d_e is the all-pair mean; across d_e is the exact endpoint distance.
- S_e = 100 / max(1, r_e).
- S_population = 100 - sqrt(mean((100 - S_e)^2)).

The within maximum is diagnostic only, not a second penalty. The boundary median uses boundary distances, NOT within-shot baselines. No tau, softmax, second weighting layer, or overall median across episodes.

Apply this same RMS formula to each shot, each boundary, all within records pooled, all boundary records pooled, and finally all valid within+boundary records pooled. An entity seen in several shots/boundaries contributes separate records. Do not average already-computed shot scores. Larger inventories therefore contribute more episode weight.

A missing/zero baseline returns null ratios. A baseline <= 32 ULPs of the largest scope distance is numerically degenerate and also returns null; this is a relative floating-point guard, not an anomaly threshold or physical noise calibration. No epsilon division fabricates large ratios. Raw distances survive. Empty scored population returns null. No minimum population cutoff: counts are explicit; a singleton self-normalizes to 1 and small populations give weak references.

The ratios remove uniform coordinate scaling but do not isolate detection noise or registration error. Widespread true drift can raise the median and be hidden; noisy detections can lower scores. The result is a relative geometric position score, not a calibrated visual-error probability.

## Saved outputs and integration

Each new run writes `displacement/results.json`, `displacement/entities.csv` and `displacement/REPORT.md`. JSON/CSV retain round-trip double precision (no manual rounding/clipping of r_e), source hashes, scorer source fingerprint, protocol/formula, scope/entity IDs, raw mean/maximum or endpoint distance, denominator, original/aligned centers, frame witnesses and explicit missing/excluded reasons. JSON also contains every within-frame pair distance. Report rendering may round displayed scores only.

`summary.json.position_consistency` exposes per-shot, per-boundary, episode-within, episode-cross and episode-all scores plus links to the records. Existing stage/call accounting reports zero extra model calls/tokens/API USD for the new stage. Source provenance includes the new scorer. The stage waits for own-shot classifications and all requested boundary reviews; it has zero API slots, no GPU and no model dependencies beyond existing results. Failure to produce its result fails a requested spatial/full run.

Replay frozen inputs independently without changing their old summaries:

```bash
python EECBench/scripts/gs_entity_displacement.py --case EXISTING_CASE --out NEW_OUTPUT_DIRECTORY
```

Run CPU work on an existing low-utilization owned compute allocation according to workspace policy. To change aggregation later, reuse saved r_e records; no detector, geometry or model rerun is needed.

## Validation

60 focused tests passed: new displacement tests (9), temporal core (23), parallel scheduling (4), appearance integration (7), prompt alignment (17). Study2/3/4 frozen CPU replay and independent source/hash/formula checks passed. Study4 Shot1 means/maxima and Study3/4 endpoint distances reproduce historical diagnostics within 1e-12.

Report: `EECBench/experiments/entity_displacement_integration_20260921/REPORT.md`. These are component replays and integration tests, not a new full frontend/GPU evaluation or human calibration. Validation adds 0 model calls, 0 tokens, USD 0 API.
