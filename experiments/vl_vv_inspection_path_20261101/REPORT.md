# V-V inspection path and the `other` subcategory (2026-11-01)

## Owner decisions

- The consistency branch answers the checklist along a fixed inspection path:
  each shot, each recurring subject across shots, each shot boundary; every
  noticed change is judged, abnormal changes become issues, and each issue names
  the checklist items that found it. Paper and prompt state this logic.
- The open sweep must not force a problem outside the checklist into a listed
  subcategory. A sweep finding that fits no subcategory uses `other` and is
  described in the agent's own words.

## Changes

- `prompts/vl_vv_issue_discovery_v5_vv.txt`: section 2 now states the path and
  which checklist items each pass answers (pass 1: W1-W7; pass 2: X1, X2, X3, X5,
  X6, X7, X8; pass 3: X4, X9); O1 is required in the answers; section 3 is
  "Records of the path: fill them before checklist_audit and the issues". The
  item mapping is the assistant's reading of each item's check text and of the
  record fields (the ledger has `style` subjects and records the camera position
  of a place); it was not stated before.
- `schemas/...discovery-v5-vv`: field order changed so `checklist_audit` follows
  the records (`shot_scan`, `continuity_ledger`, `boundary_checks`,
  `observed_changes`, `checklist_audit`, `entity_register`, `issues`). Before,
  the audit came first, so structured output had the model answer the checklist
  before writing any record. No field was added or removed.
- `configs/vl-vv-branch-v1.json`: `other` in both V-V scopes and in the
  entity-optional list; O1 check text no longer says "the closest subcategory".
  V-V schemas regenerated (`--check` clean). Enums de-duplicated.
- `scripts/run_vl_vv_branch_detection.py`: new gate, subcategory `other` must list
  O1 in `checklist_items`.
- `tests/test_vl_vv_inspection_path.py`: every item has one place on the path,
  records precede answers, `other` available once, sweep wording. The new gate
  itself has no dedicated test.
- Paper 3.3.2 consistency branch rewritten to the same logic.

Scoring is unchanged: penalties use severity, not subcategory. Section 4's
subcategory heatmap gets an `other` row.

## Verification and limits

203 tests in the VL/VV, clustering, image-label and segmentation set: 202 passed,
1 known failure (no ffmpeg). No live run, so the effect of the new field order and
wording on detection is unknown (`docs/open-questions.md` Q2). Pre-change copies
with SHA-256: `source_before/`.
