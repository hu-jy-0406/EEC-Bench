# Simplified entity ledger without DINO (2026-11-01)

## Owner decisions

- Simplify `episode_entities.json`: `occurrences` is the core content. Drop
  identity reasons, `linked_by`, `identity_status`, `schedule`,
  `supplementary_bindings` and match tags; unspecified entities get the same
  per-shot structure as specified ones (shot, keyframes and boxes).
- The current version does not use the DINO score. Whether a DINO hint helps
  detection is a later ablation (`EECBench/docs/open-questions.md` Q1;
  evidence `EECBench/experiments/dino_issue_relation_20261101/REPORT.md`).

## Format (`ledger_format: vl_vv_entity_ledger_v2`)

Top level: `protocol`, `ledger_format`, `matching_protocol`, `status`,
`shot_order`, `prompt_bound`, `prompt_unbound`. Specified record (`pb…`):
`global_entity_id`, `prompt_entity_id`, `name`, `description` (contract),
`occurrences`. Unspecified record (`ge…`): `global_entity_id`, `name` (local
name of its first occurrence), `description` (matching agent),
`occurrences`. Occurrence: `shot_id`, `local_entity_id`, `boxes`
(`frame_id`, `box_xyxy`, only keyframes with a box; an unlisted keyframe is
unobserved, not absent). A contract entity never detected has an empty
`occurrences`. Schema `schemas/vl-vv-episode-entities-v2.schema.json`
(`additionalProperties: false`).

Where the dropped content is: matching bases, confidences, tags and
supplementary bindings in `case/global_match_v2/` (`result.json`,
`tags.json`; `audit.json` now also records model and reasoning); contract
schedule in `contract.json`; binding status/reasons, candidate IDs, detector
names and scores in the per-shot files under `shot_prompt_recovery/`; DINO in
`dino/` and `global_entities/global_entities.json` (still computed, no longer
attached to the ledger).

## Code

- `scripts/run_vl_vv_detection.py`: `build_episode_entities_v2` writes the v2
  format (`ledger_occurrence`); constants `LEDGER_V2`, `EPISODE_SCHEMA_V2`;
  `attach_dino` leaves a v2 ledger untouched; matching v2 audit records
  model/reasoning. Matching v1 keeps the v1 ledger for reproducing history.
- `scripts/vl_vv_branch_common.py`: `ledger_rows` derives `partition` from
  the list, `occurrence_frame_ids` reads `boxes` or v1 `observed_frame_ids`,
  `ledger_entity` reads `description` or v1 `short_description`.
- `scripts/run_vl_vv_branch_detection.py`: `detected_frames` uses
  `occurrence_frame_ids`.
- `schemas/vl-vv-episode-entities-v1.schema.json` restored to its committed
  version (the earlier same-day v2 additions are no longer needed).
- Tests: `tests/test_vl_vv_matching_v2.py` (ledger fields, missing boxes,
  both formats readable, attach_dino). 162 VL/VV, clustering, image-label and
  segmentation tests pass; the one failure
  (`test_recorded_cut_shots_extracts_planned_frames_from_a_real_video`) needs
  ffmpeg, which this Python lacks, and fails without this change too.
- Pre-change copies with SHA-256: `source_before/`.

## Effect and limits

- The ledger is `INPUT.detector_ledger` of both detection calls, so their
  model input changes. The prompts' description of the ledger (`prompt_bound`
  bound through `prompt_entity_id`, `prompt_unbound`, per-shot occurrences)
  stays correct, and no prompt was edited. Size on #002 (old ledger, 8
  specified entities, recomputed offline): about 107,000 characters compact
  JSON before, about 13,000 after.
- Old chains (discovery v1-v4) mention "DINO values" in their prompts; on a
  new case they get a ledger without them.
- Not validated live (no A/B yet; `docs/open-questions.md` Q2).
