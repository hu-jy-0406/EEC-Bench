# V-V transition_realization removed; worn items no longer inherit provenance (2026-10-21)

## Owner decisions

1. A boundary that does not realize its required transition (a missing
   required cut, a broken required continue) is a V-L issue only
   (`shot_structure`). Remove `transition_realization` from the V-V
   cross-shot categories.
2. Entity provenance is decided by mention: an entity is prompt-bound if the
   prompt or contract names it, prompt-unbound otherwise. A wristwatch the
   text does not name is prompt-unbound even when a prompt-bound character
   wears it.

Both changes are in place in the current default chain (discovery v5 →
review v6 → scoring v5; no new protocol names). Older chains (v1–v4) are
unchanged. Pre-change copies and their SHA-256 sums: `source_before/`.

## Changes

| File | Change |
| --- | --- |
| `configs/vl-vv-branch-v1.json` | V-V cross-shot `transition_realization`, its entity-optional entry, checklist item X10 and change aspect `transition` removed; normal cause `required_transition` now says the shot change at a boundary is normal for V-V and realization of the required cut/continue is a V-L question; provenance texts: prompt-bound = contract entity or named by the text (including an item named inside a character description, e.g. "wristwatch"); worn, held or carried items the text does not name are prompt-unbound; `part_of_entity` only for body parts |
| `prompts/vl_vv_branch_definitions_v1.txt` | cross-shot V-V definition no longer mentions boundaries; boundary table: missing cut / broken continue → V-L `shot_structure`, V-V nothing to report (content across the boundary still compared) |
| `prompts/vl_vv_issue_discovery_v5_vv.txt` | `boundary_checks` without the `realized` verdict ("whether a boundary realizes its required cut or continue is a V-L question"); transition mentions removed; provenance section as in the config |
| `prompts/vl_vv_issue_review_v6_vv.txt` | provenance definitions as in the config; transition_realization removed from the entity-free list |
| `scripts/build_vl_vv_branch_schemas.py` → `schemas/vl-vv-issue-discovery-v5-vv`, `vl-vv-issue-review-v6-vv`, `vl-vv-branch-records-v1` | `realized` field and the removed codes dropped (regenerated; `--check` passes) |
| `scripts/run_vl_vv_branch_detection.py` | X10-not-N/A gate and not_realized → transition issue gate removed; camera-jump gate uses `camera_position` only |
| `tests/test_vl_vv_branch_pipeline.py` | fixture without `realized`; two new tests (transition is V-L only; unnamed worn items do not inherit) replacing the not_realized test; 125 VL/VV tests pass |
| `docs/vl-vv-branch-pipeline-v1.md` | updated |

V-L already checks every boundary through its contract-template transition
rows (`TR:…`, subcategory `shot_structure`); that side is unchanged. No stored
V-V output of this chain contained a `transition_realization` issue or a
`not_realized` boundary, so existing results stay readable.

## Live check (3 frozen cases, one run each, image labels on)

`run_jobs.py check`, `launch.sh 291609 check 3`; API only, on existing
allocation 291609 (node auh7-1b-gpu-198, load ≈7.5/128, its own steps
running; CPU-light overlap step at low priority; job 286177 had expired).

- All 3 runs succeeded (100–158 s). V-V detection validated with 0, 1 and 0
  repair rounds (the one repair was an unrelated continuity-ledger
  assessment). Every boundary was still compared (3, 5 and 7 boundary checks
  without a realization verdict); no transition issue appeared. All boundaries
  of these clip-model cases are required cuts, so a missed transition could not
  occur here; that needs CineTrans/HoloCine cases with fresh detection.
- The worn-item rule was not exercised: no reported issue involved a worn or
  held item.
- Scores (V-L / V-V): #002 21.09 / 83.75, #032 100 / 60.94, #047 Wan2.1
  9.14 / 81.25.
- Cost: 21 calls; 1,751,132 input tokens (723,613 cached, 1,027,519 uncached)
  and 60,532 output tokens, USD 0.140 (GPT-6 Luna standard API estimate; not a
  bill).

## Finding: "does not conflict with" wording and V-L detection on #032

#032's V-L score of 100 came from a V-L detection that marked all 55 template
rows `satisfied`, although its own observation for Shot2 reads "oven handle on
the left of the frame" and the text requires "pale handle and glowing window
on the right" (the frames show the oven on the left). This is the rubber-stamp
pattern seen during the 2026-10-09 development. The 2026-10-20 wording check
covered only the review stage, so V-L detection on #032 was rerun three times
with the current definitions and three times with only the 2026-10-20
"satisfies" sentence restored (`definitions_satisfies_variant.txt`; the
rendered prompts differ only in that sentence and the boundary-table row).
Image labels on in both arms. `detection_check.py`:

| #032 V-L detection | All 55 rows satisfied (0 candidates) | Handle/window side flagged |
| --- | --- | --- |
| "does not conflict with" (3 check runs + the pipeline run) | 3 of 4 | 1 of 4 |
| "satisfies" (3 check runs) | 0 of 3 | 3 of 3 |
| "satisfies", 2026-10-09 (unlabeled, 2 runs) | 0 of 2 | – (4–5 candidates each) |

#002 and #047 were not affected under the new wording (6 and 12 violated
rows). One video and few runs, but the contrast on #032 (3/4 vs 0/5) points to
the wording. Not changed without the owner's decision.

Cost of the detection check: 14 calls; 2,105,706 input tokens (1,921,077
cached, 184,629 uncached) and 48,337 output tokens, USD 0.062 (standard API
estimate).
