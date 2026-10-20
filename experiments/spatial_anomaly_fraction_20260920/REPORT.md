# Spatial score: confirmed anomaly fraction

Explicit user revision, 2026-09-20: omit spatial coverage; score only the proportion of confirmed anomalous entity pairs among all entity pairs.

- Temporal v2 within-shot and cross-shot spatial summaries now report `total_pairs`, `confirmed_conflict_pairs`, `anomaly_ratio` and `score=100*(1-anomaly_ratio)`.
- Denominator is all currently enumerated pairs. Within-shot: pairs of frozen entities; boundary: pairs of reviewed matched identities. Population generation is unchanged. Exempt and unresolved pairs remain in the denominator; only confirmed conflict contributes to the numerator. Each pair counts at most once per scope.
- Nonnegative cosine without another unresolved comparison is `no_conflict` (no anomaly proposal), rather than unknown merely because no positive certification was requested. Missing geometry, uncertain expected-motion intervals and uncertain negative-candidate reviews retain diagnostic uncertainty, without a coverage metric or a penalty.
- Spatial summaries no longer expose C/K/U/E/N aliases, coverage or identification intervals. Diagnostic `no_conflict_pairs`, `unresolved_pairs`, `exempt_pairs` remain. Their sum plus confirmed conflicts equals total pairs.
- Empty pair population yields null score/ratio, not a fabricated 100.
- Presence scoring, original spatial prompts, evidence gates, registration, frame population and historical flow1_fused_v1 scoring are unchanged. No model calls or historical experiment rewrite.

Validation: 31 CPU tests passed (23 temporal,8 restored boundary spatial) on existing owned196093/node197, one CPU, nice19, GPUs hidden. Covers all-positive observations, anomaly/total denominator including exemptions and unknowns, empty populations, missing geometry, once-per-pair penalties, unchanged presence formula, and original boundary review integration. No fresh evaluation has been run.
