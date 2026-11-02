# VL/VV episode scoring v1

The fourth agent scores **one generated episode** from the completed issue-review
`result.json`. It uses GPT-6 Luna with low reasoning through the configured
OpenAI API transport. The model receives the full review JSON as its only
episode-specific input and no images or separate prompt, contract, detector,
entity registry, discovery file, or prior conversation. The scorer's skill is
the model instruction file: `skills/vl-vv-episode-scorer/SKILL.md`.

## Benchmark basis and local design choice

[EntityBench](https://arxiv.org/abs/2605.15199) separates prompt following
from cross-shot consistency and uses an entity-fidelity gate for its own
cross-shot metrics. [VBench](https://github.com/Vchitect/VBench/blob/master/README.md)
reports separate dimensions and normalizes them before aggregation. Those
designs motivate separate V-L and V-V axes here. The following severity
deductions and aggregation are **UEC-Bench v1 choices**, not formulas claimed
by either benchmark. They have not been calibrated against human scores.

The output has three 0–100 scores: `v_l`, `v_v.within_shot`, and
`v_v.cross_shot`. Higher is better. `v_v.overall` is their equal arithmetic
mean. There is no combined V-L/V-V episode total; the two top-level dimensions
remain visible separately.

## Rubric and deterministic math

The agent assigns one severity per reviewed candidate. Rejected and uncertain
candidates get `none` and zero deduction. Confirmed candidates receive:

| Severity | Base deduction |
| --- | ---: |
| minor | 5 |
| moderate | 15 |
| major | 30 |
| critical | 55 |

The skill defines the impact threshold for each tier. The runner then scales a
confirmed issue's deduction by review confidence: high ×1, medium ×0.75,
low ×0.5. This treats confidence as uncertainty in the verdict, separately
from severity. For two rows describing the same concrete failure within one
dimension, the model points the later row to the first via `duplicate_of`.
The runner keeps the larger adjusted deduction for that event. Distinct
failures remain separate even when they share an entity or shot.

For each dimension, with unique event deductions `p_i`, the score is
`round_half_up(100 × ∏(1 − p_i/100), 2)`. A dimension with no confirmed reviewed
events scores 100. The product is monotone, distinguishes severity and repeated
events, and avoids the immediate zero saturation of a capped additive sum.
`v_v.overall = round_half_up((within_shot + cross_shot)/2, 2)`.

For example, one high-confidence major event scores 70 in its dimension.
Two distinct high-confidence moderate events score 72.25. Two candidate rows
about the **same** moderate event score 85 after deduplication. These are
arithmetic examples, not judgments on a video.

The output records every candidate's verdict, severity, confidence, base and
adjusted deduction, duplicate link, and reason; each unique event records its
applied deduction. Candidate, verdict, and unique-event counts accompany each
dimension. `uncertain` receives no penalty but remains counted, so 100 means
only that this reviewed JSON contains no confirmed issue in that dimension.
Coverage and human-calibrated validity are not asserted. Episode lengths differ
in the dataset; compare models on the same episode set and average per-episode
scores rather than treating a raw issue count as a length-normalized metric.

## Invocation

```bash
EECBench/scripts/openai_api_env.sh \
  /vast/users/guangyi.chen/anaconda3/bin/python \
  EECBench/scripts/run_vl_vv_episode_scoring.py \
  --review /abs/issue_review/result.json \
  --output /abs/fresh/issue_scoring
```

The review file can also be a recovered review `result.json`. The runner
requires successful discovery and review status, exact one-to-one issue
assessment, valid same-dimension duplicate references, and legal severity
assignment. A failed model response is retained in `call/` and produces no
episode score. The successful output is `issue_scoring/result.json`; the exact
review input is copied to `review_input.json`. `call/input.json` is the same
review JSON, and `call/request.json` has an empty `images` list. Source hashes,
API usage, an estimated USD cost split by uncached input/cached input/output,
and elapsed time are recorded. Cost is a standard API estimate, not an actual
billing record.
