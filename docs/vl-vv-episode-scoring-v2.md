# VL/VV episode scoring v2

The fourth agent scores one generated episode from its completed issue-review
`result.json`. It uses GPT-6 Luna with low reasoning. The scorer receives the
review JSON as its only episode-specific input; it has no images or independent
access to the prompt, contract, detector, or discovery output. Its current
instructions are in `skills/vl-vv-episode-scorer/SKILL.md`.

## Scores

The output keeps the existing three dimensions: `v_l`, `v_v.within_shot`, and
`v_v.cross_shot`, each from 0 to 100. `v_v.overall` is the arithmetic mean of
within-shot and cross-shot. There is no combined V-L/V-V score.

## Severity deductions

The scorer assigns one impact tier per reviewed candidate. Rejected and
uncertain candidates receive `none` and no deduction. Confirmed issues use:

| Severity | Meaning | Base deduction |
| --- | --- | ---: |
| `minor` | Small, local mismatch; main identity, action, or relation remains recognizable. | 10 |
| `moderate` | Clear, meaningful mismatch limited to one detail, subject, relation, or short portion of a shot. | 25 |
| `major` | A central required action/entity/relationship fails, or a recurring entity or scene changes substantially across shots. | 50 |
| `critical` | The error defeats a core episode premise or affects several important shots/entities across the episode. | 80 |

Multiply a confirmed issue's base deduction by review confidence: high `1.0`,
medium `0.75`, low `0.5`. Confidence changes the adjustment, not the severity
tier. Distinct confirmed failures compound separately. Rows describing the
same concrete failure in the same dimension share one event; the runner uses
the maximum adjusted deduction in that event.

For unique event deductions `p_i`, compute a dimension as
`round_half_up(100 * product(1 - p_i/100), 2)`. A dimension without confirmed
issues in the reviewed JSON scores 100. This says nothing about issues omitted
by discovery or the review input. V-V overall is the equal mean of its two
subdimensions.

Illustrations: one high-confidence moderate event scores 75; two distinct
high-confidence moderate events score 56.25; one high-confidence major event
scores 50; one high-confidence critical event scores 20. Duplicate reports of
one event do not compound.

The v2 base deductions are a deliberate stronger-penalty design choice. They
are not calibrated against human judgments. The ten-episode, three-model set
provides a frozen comparison set, not a calibration or independent test set.
Increasing deductions cannot lower a bucket with no confirmed reviewed issue;
that requires better discovery/review coverage rather than a scoring weight.

## Historical comparison

Version 1 used base deductions `5/15/30/55` and the same confidence factors,
deduplication and product formula. Its outputs remain intact under
`experiments/vl_vv_episode_scoring_20260925/`. A penalty-only replay can reuse
the existing severity/verdict decisions to isolate the deterministic weight
change. Fresh v2 Luna assessments are separately identified by protocol and
must not be represented as human-calibrated outcomes.

## Invocation

```bash
EECBench/scripts/openai_api_env.sh \
  /vast/users/guangyi.chen/anaconda3/bin/python \
  EECBench/scripts/run_vl_vv_episode_scoring.py \
  --review /abs/issue_review/result.json \
  --output /abs/fresh/issue_scoring_v2
```

The runner validates exact one-to-one assessment coverage, legal severities,
and duplicate links restricted to earlier confirmed issues in the same
dimension. It saves the exact review input, skill/schema/source hashes, API
usage and standard API cost estimate. The estimate is not a bill.
