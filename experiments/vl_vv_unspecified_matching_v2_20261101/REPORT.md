# Matching v2: identity of unspecified entities by the most likely reading (2026-11-01)

## Owner decisions

- Specified entities are linked across shots by their contract IDs; matching
  is only needed for unbound (candidate unspecified) occurrences.
- Identity follows the most likely reading of the episode, not visual
  similarity alone, so that a changed rendering does not split one entity and
  hide the inconsistency.
- No `unresolved` outcome. Every unbound occurrence has exactly one of three
  destinations: (1) merged with other unbound occurrences into one unspecified
  entity, (2) alone as one unspecified entity, (3) merged into a specified
  entity (a supplementary binding).

## Design

Inputs to the matching agent (`prompts/vl_vv_unspecified_matching_v2.txt`,
GPT-6 Luna low as before): the original global and shot prompts; each shot's
settings (contract places scheduled in it); the specified entities (tag `P<k>`,
name, description, occurrences) as anchors; the unbound occurrences (tag
`U<n>`, name, per-frame boxes, detector categories); and the six keyframes of
every shot with every occurrence drawn on them (blue P boxes, orange U boxes,
tag labels), each image preceded by its shot/frame label. The full contract is
not sent.

Rule: decide by setting and recurring places, position and relations to other
entities, continuity of actions and the story; an appearance difference is an
inconsistency for later stages, not evidence of two entities; keep apart only
on positive evidence (both visible in one shot, the prompt introduces another,
different places with no movement, different roles). At most one occurrence of
an entity per shot; a supplementary binding only into a shot where the
specified entity has no occurrence. Every assignment has a short description,
confidence (high/medium/low) and a one-sentence basis.

Deterministic checks (all returned to the model by the existing repair loop):
exact-once coverage of U tags, known tags only, one occurrence per shot,
specified_tag rules, no clash with existing or other supplementary occurrences.

Ledger (`episode_entities.json`, same file and protocol `vl_vv_detection_v1`,
new field `matching_protocol: vl_vv_unspecified_matching_v2`): one `pb…` record
per contract entity (`identity_status` contract_id or scheduled_only;
occurrences with `linked_by` contract_id or matching; `supplementary_bindings`
with confidence and basis); one `ge…` record per unspecified assignment
(`identity_status` matched or single, `match_confidence`, basis as
`identity_reason`); `unresolved_identity_links` is always empty. The schema was
extended with these statuses; v1 ledgers stay valid.

### Revision: simplified ledger (2026-11-01, owner decision)

The ledger fields described above (`identity_status`, `linked_by`,
`supplementary_bindings`, `match_confidence`, `unresolved_identity_links`,
DINO) are no longer written; matching v2 now writes the simplified ledger
`vl_vv_entity_ledger_v2`. See
`EECBench/experiments/vl_vv_ledger_simplified_20261101/REPORT.md`.

### Revision: appearance weighed with all relations (2026-11-01, user clarification)

The owner stated the principle as: the matching agent considers appearance
together with multiple relations to decide whether occurrences are one entity,
and does not decide from appearance alone or from a single spatial relation,
so that an inconsistently rendered entity is not split into two. The prompt's
identity paragraph was revised in place (no live run had used the first
draft): appearance is now named as one of the cues weighed together with the
setting, position, relations to other entities, action continuity and story;
"neither appearance nor any single relation decides on its own"; an appearance
difference is not a reason to split when the other evidence shows one entity;
one shared relation (e.g. the same desk) does not by itself merge two
occurrences. The positive-evidence list for keeping occurrences apart, the
three destinations, output fields and deterministic checks are unchanged.

- First draft: `prompt_history/vl_vv_unspecified_matching_v2.first_draft.txt`,
  SHA-256 e64da901417fb894d7a3d8cdc9efe97dd5974de50e8a956b1f7707dce0bcde6a.
- Current prompt SHA-256 3edd0e75f0eea0a0b240a399d700b255ac8c7450be5251eee8e4036214a97b71.
- `tests/test_vl_vv_matching_v2.py` checks the principle sentences; 54 matching
  and branch-pipeline tests pass. Still no live run, so there is no A/B of the
  two drafts.

## Code

- `scripts/run_vl_vv_detection.py`: `match()` dispatches to `match_v2` (default)
  or `match_v1` (historical, unchanged); new `--matching-protocol {v1,v2}`;
  output in `case/global_match_v2/` (tags, annotated frames, attempts, audit,
  result); `run.json` records `matching_protocol`.
- `schemas/vl-vv-episode-entities-v1.schema.json`: identity statuses
  contract_id, matched, single; optional `matching_protocol`.
- `tests/test_vl_vv_matching_v2.py`: 9 tests (tags, payload, three
  destinations, all-errors reporting, one occurrence per shot, ledger, annotated
  frames, default). 160 VL/VV, clustering and segmentation tests pass.
- Pre-change copies (from git HEAD) and SHA-256: `source_before/`.

## Not yet validated live

No model run yet. Validation needs fresh matching on existing cases (the
matching stage needs an allocation for API calls) and a comparison of the
ledgers with v1, e.g. #032 (v1 ledger: glasses, wristwatch, earring and
bracelet as separate unbound entities; note the clustering change of the same
day now merges worn items into the wearer, so a fair comparison re-runs
clustering first) and a case with recurring background objects.
