# VL/VV issue discovery v3: one label per issue

User decision 2026-10-06. When a discrepancy is both a visual inconsistency and
a prompt violation, split it at discovery into two issues:

1. a V-V issue: Shot A and Shot B are visually inconsistent;
2. a V-L issue: Shot B is inconsistent with the prompt.

Each issue then makes one claim. The reviewer can no longer reject the V-L
half because some other shot of the comparison satisfies the prompt.

## Changes from discovery v2

Everything else in discovery v2 is kept: the checklist, the open-ended sweep,
`shot_scan`, the continuity ledger, transitions, the subcategories and the
evidence rules.

- **One label per issue.** Every issue carries exactly one label, `v_l` or
  `v_v`; the other is null.
- **Linked pairs.** A discrepancy that is both becomes two issues that list
  each other in `related_issue_ids`:
  - the V-V issue covers every compared shot;
  - the V-L issue covers only the shot(s) whose content contradicts the quoted
    requirement, quotes the requirement that applies to those shots, and never
    includes a shot that satisfies it.
- **Continuity phrases.** For "same", "remains" or "returns", the violating
  shot is the one whose prompt states the continuity and whose content breaks
  it. For a continuity stated globally, it is the shot(s) that depart from
  what the other shots establish.
- **Transitions and within-shot changes.** A transition failure becomes a V-V
  `transition_realization` issue linked to a V-L `shot_structure` issue. A
  within-shot change that contradicts the text becomes a V-V within-shot issue
  linked to a V-L issue in the same shot.

## Deterministic gates

These are checked in `link_errors` and in `result_errors_v2(..., atomic=True)`;
the repair loop applies them.

- Exactly one label per issue.
- `related_issue_ids` entries exist, are not the issue itself, have no
  repeats, link a V-L issue with a V-V issue, and are mutual.
- A linked V-L issue's shots lie inside its V-V counterpart's shots.
- A `transition_realization` issue has a linked V-L `shot_structure` issue.

## Files and selection

- **Prompt:** `prompts/vl_vv_issue_discovery_v3.txt`.
- **Schema:** `schemas/vl-vv-issue-discovery-v3.schema.json`. It is the v2
  schema plus `related_issue_ids`.
- **Default chain:** discovery v3 → review v4 → scoring v3.
- **Downstream:** review (v4 or v2) and scoring v3 accept v3 discovery results
  unchanged. Each half deducts in its own bucket, just as the two labels of a
  v2 issue did.
- **Older chains:** `--discovery-protocol v2` (pipeline, discovery runner,
  batch controller) keeps the multi-label issues, and `v1` the historical
  chain.

Validation: `experiments/vl_vv_core_review_20261006/REPORT.md`.
