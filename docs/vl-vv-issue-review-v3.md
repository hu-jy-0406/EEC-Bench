# VL/VV issue review v3 (true / partly true / false) and episode scoring v4

> **Retired 2026-10-06 (user decision).** The partly-true verdict was removed.
> The current review is v4, which gives verdicts on the core problem of each
> label (`docs/vl-vv-issue-review-v4.md`). The prompts and schemas named below
> now live in `prompts/retired/` and `schemas/retired/`. No runner accepts
> review v3 or scoring v4. This page is kept as the record of the experiment.

User decision 2026-10-06: the reviewer classifies each issue as true, partly
true or false. For a partly true issue it confirms the true part instead of
rejecting the whole claim, and that part counts in the score. Motivating case:
#068 HoloCine, candidate I5 (V-V within, presence_instability). The man really
vanishes from the elevator in Shot6, but the candidate also claimed "the woman
returns", which is false. Review v2 had to choose one verdict for the whole
claim and rejected it, so the real disappearance was never scored.

## Chains (all kept runnable)

| Chain | Discovery | Review | Scoring | Select with |
| --- | --- | --- | --- | --- |
| historical | v1 | v1 (one verdict per issue) | v2 | `--discovery-protocol v1` |
| checklist, all-or-nothing review | v2 | v2 (confirmed / rejected / uncertain per label) | v3 | `--discovery-protocol v2 --review-protocol v2` |
| **checklist, partial review (default)** | v2 | **v3** | **v4** | default (`--discovery-protocol v2 --review-protocol v3`) |

- The flags apply to `run_vl_vv_pipeline.py`, to `run_vl_vv_issue_review.py`
  (`--review-protocol`; the default follows the discovery protocol) and to the
  first-200 batch controller.
- The scoring runner picks v2, v3 or v4 from the review protocol recorded in
  its input.
- A batch directory records its review protocol and keeps it. A discovery-v2
  directory created before review v3 existed resumes with review v2.
- Discovery is unchanged.

## Review v3

Files: `prompts/vl_vv_issue_review_v3.txt`,
`schemas/vl-vv-issue-review-v3.schema.json`, `review_errors_v3` in
`scripts/run_vl_vv_issue_review.py`.

Model and transport are unchanged (GPT-6 Luna/low, all original keyframes,
the same payload as review v2). Every non-null label still gets its own
verdict:

| Verdict | Meaning | Deducts |
| --- | --- | --- |
| `confirmed` (true) | The claim holds in all essential points. Minor imprecision, such as an approximate frame or a loose color word, does not make it partly true. | yes |
| `partly_confirmed` (partly true) | Part of the claim holds and part is false or cannot be established. | yes, for the true part only |
| `rejected` (false) | No part of the claim holds. | no |
| `uncertain` | The frames and text cannot settle whether any part holds. Kept as a fourth option so the reviewer is not forced to guess. | no |

A `partly_confirmed` label carries three extra fields:

- `confirmed_part`: what holds;
- `unsupported_part`: what is false or unestablished, and why;
- `confirmed_shot_ids`: the shots in which the true part is visible.

For every other verdict these three fields are null.

### Rules for the true part

The true part must be a narrower form of the candidate's own claim: fewer
shots, fewer entities or attributes, part of the described events, or a
smaller change of the same kind.

- It cannot add a problem the candidate did not describe, or move it to
  another label or scope.
- It must be an inconsistency the reviewer would confirm if it were the whole
  candidate.
- A normal difference explained by camera, lighting, action, occlusion or
  story does not qualify. If nothing else remains, the verdict is `rejected`.

### Deterministic checks

Every problem goes back to the model through the existing validation repair
loop; no gate was weakened.

- **Partial fields filled:** `confirmed_part` and `unsupported_part` are
  nonempty, and `confirmed_shot_ids` is present without repeats.
- **True part stays in scope:** `confirmed_shot_ids` lie inside the
  candidate's `scope_shot_ids`.
- **Cross-shot partial labels:** a partly confirmed `cross_shot` V-V label
  needs at least two confirmed shots, and the review must cite frames from at
  least two of them.
- **Support for the true part:** at least one `supports` evidence frame comes
  from a confirmed shot.
- **Partial fields only on partial verdicts:** the partial fields are null for
  every other verdict.
- **Within-shot citations:** a within-shot V-V review cites only frames of
  its own shot. This rule is unchanged from review v2.
- **Confirmed without support:** a `confirmed` label with no `supports`
  evidence is sent back to the model, which may choose `partly_confirmed` or
  `rejected`. Review v2 instead converted an all-refutes "confirmed" verdict
  to rejected; v3 does not, because that contradiction can mean that only
  part of the claim holds.

## Scoring v4

Files: `prompts/vl_vv_episode_scoring_v4.txt`,
`schemas/vl-vv-episode-scoring-v4.schema.json`.

Code: the v3 functions in `scripts/run_vl_vv_episode_scoring.py` take the set
of scored verdicts as a parameter; the v3 output is unchanged.

- **What deducts:** `confirmed` and `partly_confirmed` labels receive a
  severity and deduct in their bucket.
- **Severity of a partial label:** the scorer judges it from `confirmed_part`
  and `confirmed_shot_ids` only, as if that part were the whole issue. The
  false part must not raise the severity.
- **Unchanged from v3:** severities, reviewer-confidence factors, duplicate
  handling (a partial label may be a duplicate or a duplicate target in its
  bucket), the product rule and the bucket structure.
- **Output additions:** per-bucket counts gain `partly_confirmed`;
  `issue_scores` rows record `confirmed_part` and `confirmed_shot_ids`;
  `label_counts` gains `partly_confirmed_labels` (its confirmed-only, V-V-only
  and both counts include partial labels); `scoring_rule.partial_rule` states
  the rule.

v4 scores are not comparable with v3 scores, because v4 deducts for labels
that v3 rejected.

Validation: `experiments/vl_vv_partial_review_20261006/REPORT.md`.
