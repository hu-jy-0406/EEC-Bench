# Episode global entity registry and collection prompt — 2026-09-20

Implemented the user's confirmed-occurrence episode table and nearby same-kind collection rule. Current temporal_v2 exports the table after all final identity reviews; both registration methods and all stop-after modes include this zero-model-call stage. Historical flow1_fused_v1 execution is unchanged.

The registry merges only final audited one-to-one matched edges, restores original shot aliases, preserves all local observations (including null frame observations), and stores uncertainty links separately. Ambiguous Shot3 candidates are never added to the corresponding Shot1 entity's confirmed occurrences. Their own confirmed local detection records remain separately addressable. A record count is not a proven distinct physical-object count. Same-scene confirmed chains may merge; there is no new cross-scene matching or unsupported gap bridging.

The clustering prompt now groups nearby same-kind objects forming a local pile/group, including individually detected members: a pile of oranges or a group of pens is one node. It replaces the prior individual-first rejection rule. Containers remain separate, candidates retain exact-once ownership, and original detection coordinates/selection rules remain unchanged. A chosen member box is not a whole-group bounding box. All original member boxes remain addressable for future appearance evidence design.

## Validation

57 CPU tests passed: registry 8, temporal 23, detector/clustering contracts 17, legacy integrated regression 9. Tests cover four identity states, transitive confirmed matches, unresolved gaps, alias restoration, singleton inventory conservation, conflicting same-shot merges, final-review provenance, overwrite refusal, and registration/stop-mode export dependencies. Existing box selection and scoring tests also pass. See adjacent `test_*.log` and `validation.json`.

Frozen Study2 export: 46 local entities (20/6/20), 8 matched links, 38 global records, 2 unresolved links (plant ambiguity and historical pen scope mismatch). Checks explicitly confirm:

- Green mug: Shot1/e2 and Shot3/e2 share ge0002.
- Black lamp: ge0003 records only Shot1/e3.
- Bookshelf plant: ge0011 records only Shot1/e11; Shot3/e13 is its own ge0034 with an ambiguous link.
- Historical single pen and pen collection remain separate until fresh clustering is requested.
- All six Shot2 local entities remain in the episode table.

[Readable Study2 table](study2/global_entities.md), [machine-readable table](study2/global_entities.json).

All consumed historical source hashes remained unchanged. No API/model calls, new resource allocation, or GPU work. CPU checks/export ran at nice19 with one CPU and hidden GPUs in existing guangyi.chen allocation196093/node197, checked at load0.87 with >2TB available memory. An initial sandbox srun socket failure was stopped before retry outside the network sandbox. Initial VACE Python lacked jsonschema for four existing temporal tests; those logs are preserved as initial_vace_*.log. All 57 tests then passed using the pipeline-configured base Python. These were environment failures, not changed scoring behavior.

No fresh frontend/model evaluation was run. The new grouping prompt's actual model behavior and appearance scoring remain unvalidated/unimplemented respectively. No historical scores or frozen entity populations were rewritten.
