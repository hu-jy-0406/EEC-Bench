# VL/VV issue review v4: verdicts on the core problem

User decision 2026-10-06: remove the partly-true verdict (review v3, now
retired) and return to three review outcomes, confirmed, rejected and
uncertain. Change the rules so that a real issue is not rejected because some
non-essential part of its description is inaccurate.

Motivating case: #068 HoloCine run a, I5 (V-V within, presence_instability).
In Shot6 the people really vanish from the elevator. The candidate also said
"the woman returns", which is false, and review v2 rejected the whole issue.

## Rule

Each non-null V-L / V-V label of a candidate is judged on its **core
problem**: the inconsistency that the label and subcategory name.

| Label | Core problem |
| --- | --- |
| V-L | The video violates the source requirement the candidate cites, for the entity, event or shot it names. |
| V-V within_shot | The named kind of change inside the shot, for example an entity appearing or vanishing without cause, an identity or appearance change, or a background jump. |
| V-V cross_shot | The named kind of mismatch between shots that should match (same character, object, place, style or continuous moment), or a required transition that is not realized. |

Secondary details are everything around the core problem:

- exact frames or timing;
- what happens before or after the core problem;
- exact colors, sizes or counts;
- the discovery agent's interpretation of the cause;
- one of several listed shots, attributes or comparisons, when the core
  problem holds without it.

| Verdict | When |
| --- | --- |
| confirmed | The core problem is real and supported by visual or textual evidence (at least one `supports` frame). Confirm even when secondary wording or details are wrong. |
| rejected | Only when the core problem itself is false or contradicted by the evidence. |
| uncertain | The frames and text cannot reliably verify the core problem. |

## Evidence and assessment

- **Evidence roles** are relative to the core problem:
  - `supports`: the frame shows the core problem;
  - `refutes`: the frame contradicts the core problem;
  - `context`: everything else, including a frame that only shows a
    secondary detail is wrong.
- **Assessment:** the reviewer names the core problem it judged and, for a
  confirmed label, any inaccurate secondary detail. The scorer reads this
  assessment.
- **Confirmed without support:** review v2 turned a confirmed label whose
  evidence all refutes into rejected. That conversion is removed in v4: such
  a response goes back to the model through the existing repair loop, because
  the refuting frame may concern only a secondary detail.
- **All other checks are unchanged from review v2:** the label/review
  matching, frame references, and the rule that a within-shot review cites
  only its own shot.

## Files and selection

- **Prompt:** `prompts/vl_vv_issue_review_v4.txt`. This is the v2 prompt with
  only the verdict rules, evidence roles and assessment instructions changed.
- **Schema:** `schemas/vl-vv-issue-review-v4.schema.json` (same shape as v2).
- **Validation:** `review_errors_v4` in `scripts/run_vl_vv_issue_review.py`.
- **Scoring:** unchanged scoring v3. It accepts review v2 or v4, and its
  result records `source_review_protocol`.
- **Default chain:** discovery v2 → review v4 → scoring v3.
- **Older chains:**
  - `--review-protocol v2` keeps the previous review, on the pipeline, the
    review runner and the batch controller;
  - discovery v1 keeps review v1 → scoring v2.
- **Review v3 (partly true) is removed:**
  - its prompt and schema, and scoring v4, are in `prompts/retired/` and
    `schemas/retired/`;
  - no runner accepts it, and a batch directory that recorded it is refused;
  - its validation results remain in `experiments/vl_vv_partial_review_20261006/`.

Validation: `experiments/vl_vv_core_review_20261006/REPORT.md`.
