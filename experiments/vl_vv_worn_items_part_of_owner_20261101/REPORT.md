# Worn and carried items are part of their wearer in detection (2026-11-01)

## Owner decision

Apply the contracts' entity/attribute split (2026-10-27/29 granularity rules)
to entity detection, so that something the contract keeps as an attribute is
not detected as a separate (and then unspecified) entity. Main reason: the
consistency of a worn item is already checked as part of the person's
appearance (V-V checklist W2/X3). This supersedes the 2026-10-21 decision that
a watch the text does not name is prompt-unbound.

Rule as implemented:
- An item a person wears or carries without handling it (clothing and shoes,
  headwear, glasses, jewelry, a watch, a badge or lanyard, a tie or scarf, a
  belt, a bag on a shoulder, a coat over an arm) is part of that person,
  whether or not the text names it. Body parts are part of their person.
- An item held in a hand or handled (raised, moved, picked up, put down, taken
  off, put on, used), or no longer on the person, is an entity of its own.
- Walls, floors and ceilings are part of the setting; doors, windows,
  structural fixtures, furniture and props remain entities.

## Changes (in place; current default chain discovery v5 → review v6 → scoring v5)

| File | Change |
| --- | --- |
| `skills/wedetect-shot-entities/review_prompt.txt` (shot clustering) | the "worn clothing merges into the wearer" rule (2026-09-11) widened to all worn or carried items and body parts; handled items and items no longer on the person stay separate; wall/floor/ceiling candidates are rejected with a constituent-policy reason |
| `prompts/vl_vv_issue_discovery_v5_vv.txt` (V-V detection) | worn or carried items are not registered; a change to one is reported as a change of the person; if registered it takes the wearer's provenance (`part_of_entity` for a prompt-bound wearer); "wristwatch" prompt_quote example and the unnamed-worn-item-is-unbound rule removed |
| `prompts/vl_vv_issue_review_v6_vv.txt` (V-V review) | same provenance rule |
| `configs/vl-vv-branch-v1.json` | provenance label and `part_of_entity` texts; schemas regenerated, unchanged (`--check` passes) |
| `tests/test_vl_vv_branch_pipeline.py` | the 2026-10-21 test replaced by `test_worn_or_carried_items_are_part_of_their_wearer` |
| `docs/vl-vv-branch-pipeline-v1.md` | provenance section updated |

V-L prompts and the shared definitions are unchanged. Pre-change copies and
SHA-256 sums: `source_before/`. After-change SHA-256: review_prompt
f89b2b03…, discovery v5 V-V 9f0c61f7…, review v6 V-V 49a620f4…, config
5fa51d02….

## Tests

126 VL/VV and image-label tests and 17 shot-clustering tests pass (run at
nice 19 on the login node; no compute allocation was running).

## Not yet validated live

No A/B run has been made. Needed: re-run shot clustering on frozen WeDetect
detections (`run_wedetect_shot_entities.py --detections …`) and the V-V branch
(`run_vl_vv_pipeline.py --mode from-registry`) on cases with worn items, for
example #032 (glasses, ear stud, tie, wristwatch) and #002, and compare
entities, provenance and the `v_v_unintentional` subset with the stored runs.
Existing results were produced under the old rule; their ledgers may still
contain worn items as `ge…` entities, which the new V-V prompts route to the
wearer.
