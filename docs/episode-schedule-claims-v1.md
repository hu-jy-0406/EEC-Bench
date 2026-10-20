# Episode schedule + claims v1

User-selected on 2026-09-21: one `contract.json` per episode, with an
EntityBench-style episode inventory and shot schedule, plus four-dimensional
prompt-alignment claims. Full400 compilation was explicitly requested.

## Primary fields

- `entity_descriptions`: dictionary keyed by `Character N`, `Location N`,
  `Object N`. Each entry has the EntityBench `label`, unique `name`, and
  `description`, plus exact prompt `evidence` for auditability.
- `entity_schedule`: dictionary keyed by chronological `scene:shot` keys.
  Each value has `characters`, `places`, `objects` name lists. Names reference
  the episode-wide inventory: repeated references assert the same intended
  entity, not a measured visual-identity match.
- `claims`: existing four-dimensional claim semantics, with stable `claim_id`,
  `dimension`, registry labels in `entity_ids`, original `shot_ids`, `predicate`,
  `expected`, `coordinate_frame`, `quantifier`, `depends_on`, exact `evidence`.

Do not add another persistent `scene_id` field. Reuse registered Location
names in `places` for established same-scene recurrence; distinct physical
locations need distinct names. A numeric schedule-key prefix identifies a
chronological scene occurrence, not necessarily a persistent physical place.
A shot can show more than one location (e.g. a room and a doorway into a hall);
shared incidental visibility alone does not authorize same-scene registration.
Uncertain location identity must be recorded, not silently merged.

## Source and traceability

`episode_id` and `schema_version` identify the artifact. `prompt` stores the
current authoritative global prompt and ordered per-shot text verbatim once; each shot records its
original `shot_id` and corresponding `schedule_key`. `coverage` maps exact
source sentence units to claims and explains unscored text. `provenance`
records source/input hashes and review method. `unresolved` preserves genuine
ambiguities; these must not be presented as uniquely resolved facts. An unknown
identity association is not a requirement for physically distinct entities.

Only original `global_prompt` and `shots[].generation_prompt_en` are semantic
inputs for this Full400 construction. Existing source-video entity inventories,
observed facts, images, generated outputs, and model-specific additions cannot
supply unstated requirements. Source scene metadata is used only for schedule
key numbering, not as semantic identity evidence. The user authorized contextual
correction of contradictory original prompts on2026-09-21. Such corrections
are synchronized across current source/queue copies before the affected contract
is compiled and independently reviewed again; no interpretation justification
is added to the final prompt or contract. Queue order is preserved; model-specific
generation adaptations remain separate.

## Evaluation semantics

Schedule lists expected visible entities sometime in a shot, not every frame.
Unlisted is not forbidden or absent. Explicit negatives belong in presence
claims. Each required scheduled entity has one single-shot presence claim;
there is no additional duplicate schedule score. Ordinary appearance uses
`when_visible`. Preserve partial visibility, changing states, action completion,
coordinate systems, and same-scope presence dependencies.

Four dimensions only: presence, appearance, spatial, motion. Preserve all
applicable requirements without invented constraints or synonym double-counts.
Pure style, camera operation, audio, duration/order and offscreen persistence
remain explicit unscored source records under the existing four-dimensional
protocol; source text itself is never deleted. Concrete depicted composition,
visible pose/action and entity relations remain evaluated where supported.

## Compatibility and status

Batch implementation and isolated source/review records:
`EECBench/experiments/episode_contracts_20260921`.
The existing evaluator accepts `prompt_alignment_b_v1`, not this new authoring
schema directly. Delivery therefore includes a deterministic
`alignment_contract.json` beside each primary contract. This derivative expands
schedule names into the existing registry format and preserves all claim IDs,
text, evidence, dependencies and scoring dimensions. Pass that derivative to
`run_gs_integrated.py --prompt-alignment-contract` or the standalone alignment
runner. No evaluator decision prompt, scoring formula, geometry support or
historical result changes are implied. Semantic audit is model-based and does
not establish formal equivalence or independent human ground truth.
