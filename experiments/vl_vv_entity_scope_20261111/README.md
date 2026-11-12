# Worn items and place parts are entities in detection (2026-11-11)

Times are Dubai time. Owner: "所有类别都加吧，同步改contract" (after "A全部纳入实体，B中除了14都纳入，如果和之前的规则有冲突就
修改之前的规则"). Basis: `../vl_vv_entity_scope_candidates_20261111/README.md`. Contracts: granularity pass in
`../contract_cleanup_20261031/` (`g_pass.py`, `rules_g.txt`). Pipeline C made live the same day
(`docs/vl-vv-branch-pipeline-v2.md` section 9).

## What changed in place (before-copies in `source_before/`, hashes `SHA256SUMS_before` / `SHA256SUMS_after`)

- Shot clustering (`skills/wedetect-shot-entities/review_prompt.txt`): worn or carried items are separate entities
  named by what and whose they are (a matching pair is one entity; the person stays an entity; body parts and makeup
  stay with the person); walls, floors, ceilings, ground surfaces, floor coverings and trees/plants are separate
  entities (sky, clouds and the place as a whole are not). The "merge into the wearer" and "walls are part of the
  setting" bullets are replaced; the seating/draped-furnishing rules are unchanged.
- Floor-covering exclusion before clustering (`scripts/run_wedetect_shot_entities.py`, 2026-09-20): off by default;
  `EECBENCH_EXCLUDE_FLOOR_COVERINGS=1` restores it for historical reproduction; `candidate_filter.policy` records
  `none_2026_11_11`.
- V-V detection, chain v6 (`prompts/vl_vv_issue_discovery_v6_vv_item.txt`, `..._vv.txt`): worn items are entities
  (subject = the item, the person as context); walls, floors, ceilings, the ground, floor coverings and plants are
  entities (ledger ID or added entity); the place stays the only subject of a change of the place as a whole. The
  2026-11-09 walls-part-of-place passages are replaced; the gate that allows a place-only subject is unchanged.
- V-V review call 1 (`prompts/vl_vv_issue_review_v7_vv_rewrite.txt`): same entity statement.
- Matching v2 (`prompts/vl_vv_unspecified_matching_v2.txt`): a worn item is never merged into its wearer (only into
  a contract entity that is the item itself); a wall, floor, ceiling, ground surface, floor covering or plant is
  never merged into its place.
- Pipeline C background discovery (`prompts/vl_vv_background_discovery_v0.txt`) and plug-in U1
  (`prompts/vl_vv_unspecified_plugin_u1_v1.txt`): also list walls, floors, ceilings, the ground, rugs, plants and
  worn or carried items; still not the sky, the place as a whole, body parts or makeup.
- Chain v5 prompts, V-L prompts, binding, scoring and gates are unchanged.

## Tests

`tests/test_vl_vv_*.py`, recovery, wedetect, binding, image-label and API-message tests: 338 pass on node 304
(allocation 385762, CPU only), including the updated wording tests and `tests/test_vl_vv_pipeline_c.py`. No live
model run yet.
