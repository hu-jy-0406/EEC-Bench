# VL/VV episode scoring v3 (per-label)

> Since 2026-10-06 scoring v3 also scores review v4 (verdicts on the core
> problem; `docs/vl-vv-issue-review-v4.md`), the default review. The interim
> partly-true review v3 / scoring v4 was removed.

Scoring v3 is selected automatically when the reviewed input comes from
discovery `vl_vv_issue_discovery_v2` / review `vl_vv_issue_review_v2`. It
keeps penalty rubric v2 unchanged: base deductions minor/moderate/major/critical
= 10/25/50/80, reviewer-confidence factors high/medium/low = 1/0.75/0.5,
same-bucket duplicate groups use their maximum adjusted deduction, and each
bucket is `round_half_up(100 * product(1 - p_i/100), 2)`. V-V overall is the
mean of within-shot and cross-shot. There is still no combined V-L/V-V score.

What changes is the unit of assessment. A v2 issue carries a V-L label, a V-V
label (within-shot or cross-shot), or both. The scorer (Luna/low, prompt
`prompts/vl_vv_episode_scoring_v3.txt`, schema
`schemas/vl-vv-episode-scoring-v3.schema.json`) returns one severity per
non-null label, using that label's own review verdict and confidence:

- a confirmed V-L label deducts in the `v_l` bucket;
- a confirmed V-V label deducts in `within_shot` or `cross_shot` by its scope;
- a dual-labeled issue whose two labels are confirmed therefore deducts in two
  buckets, possibly with different severities; a label that is rejected or
  uncertain deducts nothing while the other label may still deduct;
- `duplicate_of` may only point to an earlier issue with a confirmed label in
  the same bucket, never to the issue itself.

The scorer input is the reviewed issue list only (labels, reviews, evidence
text), saved as `scorer_input.json`; no images, contract, ledger, checklist
audit or continuity ledger. `result.json` keeps the v2 output shape (`scores`,
per-bucket `counts`, `issue_scores`, `event_scores`) and adds `label_counts`
(issues, dual-labeled, confirmed V-L only / V-V only / both). Each
`issue_scores` row records its `label` and `subcategory`.

v3 scores are not comparable with v2 scores of v1 discovery runs: v2 discovery
covers more failure types and deliberately counts dual-labeled issues in both
dimensions.
