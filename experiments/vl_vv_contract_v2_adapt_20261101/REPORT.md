# Evaluator adaptation to contract v2 (2026-11-01)

Owner rule: the paper and the pipeline must match the expected pipeline, and
contract v2 is the expected contract (`docs/open-questions.md` Q4). The VL/VV
evaluator now reads v2 by default, the contract is the only V-L checking basis,
every shot boundary is a cut, and every shot has a `style` field.

The work had two rounds on the same day. The second came from a later owner
decision: add `style`, drop the shot-text row, make the contract the only checking
basis, and move between-shot camera requirements. This report describes the final
state; section 5 lists text changes round by round.

No model was called. This is checked by tests, an offline run of the chain and a
read of all 400 contracts; **no live API run has exercised the changed prompts**
(owner go-ahead pending, together with Q2). Nothing was committed.

## 1. What changed

**Contract reading.** New `scripts/episode_contract.py`. A case holds `contract.json`
(model-facing, no evidence) and `prompt.json`. In memory the prompt sits under
`"prompt"`, where v1 keeps it, and `model_contract()` removes it before the contract
goes to a model.

| Reader | v2 source |
| --- | --- |
| Prompt registry, shot binding, targeted recovery | `shots[].presence`, entities keyed by contract ID |
| Matching v2 `shot_settings` | `shots[].locations` |
| V-L template, `label_kinds`, `schedule_labels_by_shot` | `contract_template_v2`, entity `label`, `presence`, `absent` |
| V-V continuity subjects, required shot characters | `presence` plus `label` |
| V-L quote check | `entity_descriptions`, `shots`, `cross_shot` and generated presence wording; **not the prompt** |
| V-V quote check (`cause_quote`, provenance) | unchanged: prompt and contract |
| `contract_json` given to models | the model-facing contract, without evidence or prompt |

**New runs and old runs.** `prepare` takes the contract with evidence, or the
model-facing one plus `--prompt`. The batch `prepare_case.py` resolves the current
contract of an episode (cleaned once exported, otherwise the v2 rewrite). The default
chain refuses a v1 contract unless `--allow-v1-contract` is given, and discovery
v1-v4 refuse a v2 contract. The batch controller records `contract_format` per
experiment directory; a directory that recorded none predates v2 and stays on v1.
With the flag, a v1 contract keeps its v1 rows, including a shot-text row the current
prompts no longer describe, so that is neither a current evaluation nor an exact
reproduction of a historical run.

**Contract as the only V-L basis.** V-L detection and review judge only template rows.
`original_prompt` stays in the input as context. `requirement_quotes` must be contract
text, or the item text of a transition row: the schema allows only `contract` and
`shot_transitions`, and a quote found only in the prompt is rejected with a hint. V-V
prompts are unchanged, and V-V quote checks still accept the prompt.

**Transitions.** In the default chain every boundary is a cut. Gone from it: `continue`,
the `shot_transitions` input, `shot_transitions.json`, the shot-map lookup and the
`required` field of `boundary_checks`. Older chains keep their lookup. The normal
cause `required_transition` stays.

**Contracts.** `transition_from_previous` is removed and `style` added in all
deliverables and working copies. `rewrite.py`, `cleanup.py`, `rules_v2.txt`,
`rules_cleanup.txt` and `docs/episode-contract-v2-format.md` keep the new layout, and
`episode_contract.validate_v2` requires it. Both toolchains rebuilt their contracts
from decisions and ops, and each asserts equality with the stored files: 400/400 and
200/200. `manifest.json` pins the changed v2 inputs. `cleanup_log.json` keeps its
historical `source_sha256`. Pilot histories and the 2026-10-27 draft example keep
their old fields; they are records.

## 2. v2 to template mapping

Rows are grouped by shot. Every contract requirement is in exactly one row.

| v2 element | Row | Item |
| --- | --- | --- |
| Entity in `presence` | `EN:<id>@<shot>` | `description`, then presence item `S<n>-pre-<id>` (`exists`) |
| Entity in `absent` | `EN:<id>@<shot>` | absence item `S<n>-abs-<id>` (`throughout`); no description |
| `appearance`, `spatial`, `motion` on one entity | that entity's row | `item_id` = requirement ID |
| The same on several entities | `RL:<shot>` | `item_id` = requirement ID |
| `camera_view`, `camera_movement` | `CM:<shot>`, only when set | items of those names |
| `style` | `ST:<shot>`, only when set | item `style` |
| Each boundary | `TR:<from>-><to>` | fixed rule, quoted `ShotA->ShotB: cut` |
| `cross_shot` requirement | `XS:<id>`, its own row | the requirement; row carries `shot_ids` |

**How `cross_shot` is mapped.** One row per requirement, attached to the last shot it
names, so it sits with its shot group. Its frames may come from every named shot, and
a judged row must cite at least one frame of each. An issue may report it with one
occurrence per violating shot. This replaces the first-round mapping, where a
requirement sat in each named shot's row and could cite only that shot.

Presence and absence items reuse the V-L gate that a violated presence item must be
the only violated item of its row. `depends_on` and evidence quotes are not in v2
items: v2 dropped the first and the model-facing contract has no evidence.

All 400 current contracts: 17,838 rows (12,430 entity, 1,971 relation, 1,538 camera,
176 style, 1,600 transition, 123 cross-shot), 44.6 per episode, at most 92.

## 3. Style

`shot_description.style` is a string or null; the evidence version records the quote.
Candidates came from a keyword scan of every global and shot prompt
(`tools/scan_style.py`, `style_candidates.jsonl`: 297 sentences in 125 episodes), then
my own reading of every hit (`tools/build_style_decisions.py`, `style_decisions.json`).

**Result:** 176 shots in 54 episodes (85 shots in 28 of the cleaned 200). The owner's
keyword check counted 29 in the first 200; `not_filled` below explains the likely gap.
Every value uses the prompt's words and every quote is verified.

Rules I applied beyond the owner's: a shot's own statement replaces the global one for
that shot, and a global style fills only shots without one. A style counts when it
describes the video or the rendered scene (a shot, view, room, world, image). It does
not count for one entity or prop, a picture inside the scene, an expression, clothing
or a plain colour grade. Location descriptions were not touched.

**Borderline, filled:** `8iDEmCxXz-A_s00025` Shot1 "miniature puppet",
`oiikIyodOAk_s00034` Shot1 "cool, grainy monochrome" (the television image fills the
shot), `6kwhPKkHFpA_s00007` Shot3 "painterly" (from "painterly wall texture").

**Borderline, not filled** (`not_filled` in `style_decisions.json`): `pp5vs_dzZaI_s00007`
"letterboxed ... muted colors", `pp5vs_dzZaI_s00003` "slightly grainy", "detailed
stylized skin", "cartoon man", "animated man" (one entity), a pixel-art game and a
monochrome television picture (inside the scene), "miniature setting", and colour or
lighting phrases such as "muted teal-green cinematic palette".

## 4. Camera requirements between shots

**Moved: 42.** Nine in the first round (`camera_moves.json`) and 33 after the owner
ruled that cases like "Same frontal composition as Shot1 (frontal, chest-up)." are
clear (`camera_moves_second.json`). Each is `dimension: spatial`, `coordinate_frame:
camera`, `quantifier: cross_shot`, so the format gains no new kind. The comparison
moves; words stating the shot's own view stay in the field. For example that value is
now camera view "Frontal, chest-up." plus "Shot3 has the same frontal composition as
Shot1." Wording comes from the multi-shot v1 claim when one fed the value.

I identified the compared shot by reading the prompts. Where the text said only
"earlier", I chose the unique earlier shot of the same subject and setting, so those
33 are my reading, not a program result. Please spot-check `camera_moves_second.json`.

**Left in place: 50** (`camera_remaining.jsonl`, 33 in cleaned contracts). 40 are
reverse or opposite views, which state this shot's own camera position. The other 10
are listed under `left_in_place`: 6 describe the view inside one shot, 2 say only
"another view" with no compared shot, 1 is a reverse view the prompt only calls "back
across the same table", and 1 could compare with two shots (`4cSZVMEi710_s00004` Shot7,
Shot3 or Shot5).

Counts now: cross-shot 69 (cleaned 200) and 123 (current 400), was 50 and 81 before
this work. `camera_view` 741 and `camera_movement` 230 (cleaned 200). No other
requirement count changed.

**Third round (owner, same day): 35 more moved.** The owner ruled that a reverse view and any
camera requirement that needs several shots belong in `cross_shot`, which overrides the
"left in place" reasoning above. A Sonnet agent identified the compared shot of each of
the 50 values by reading the prompts (`camera_moves_third.json`); I read the doubtful cases
and accepted the list. 34 use predicate `reverse_view_of` and 1 `same_view_as`; 23 are in
cleaned contracts and 12 in v2 contracts. 15 stay: 8 are inside one shot and 7 have no
uniquely identifiable compared shot, each with its reason in the file. Where a prompt says
"return" or "back", the move records the reverse of the preceding shot and drops the
reference to the earlier one. The compared shots are model readings, not a program result.
Counts now: cross-shot 92 (cleaned 200), 158 (current 400). `camera_view` 741 and
`camera_movement` 230 are unchanged, since the shot's own view stays in the field.
Backup `source_before_third/`; `tools/verify_camera_third.py` confirms that only the listed
moves differ; `tools/check_all_contracts.py` and the 35 contract tests pass.

## 5. Every prompt, config and schema text change

Exact diffs: `prompt_config_schema.diff` (round 1), `prompt_config_schema_second.diff`
(round 2). No scoring text changed. The repair, matching and binding prompts are
untouched. V-V prompt files did not change in round 2.

**The shared definitions are included in the V-V calls, so the V-L text changes in
round 2 also reach those calls**, as the owner's decision allows. The V-V definition
text and the V-V column of the boundary table did not change.

### Round 2: contract as the only basis, new rows

| File | Before | After |
| --- | --- | --- |
| discovery V-L, intro | `satisfies the prompt and the contract, shot by shot` | `satisfies the contract, shot by shot` |
| discovery V-L, inputs | `INPUT.original_prompt: the global prompt and every shot prompt.` | `... as context only. It is not a checking basis (section 1).` |
| discovery V-L, inputs | contract fields without style | adds `style` |
| discovery V-L, section 1 | `contradict words of the text (including explicit continuity words).` | `contradict words of the contract (...). Judge and report only requirements in the template rows; a requirement that only the original prompt states is not checked.` |
| discovery V-L, rows | `shot_text rows (SP:<shot>): items "camera_view" and "camera_movement" ... and item "text", the shot prompt, standing for every other explicit requirement ...` | `camera rows (CM:<shot>)`, `style rows (ST:<shot>)`, `cross-shot rows (XS:<requirement id>)` |
| discovery V-L, observed | `for shot_text, shot scale, camera angle and movement, framing, background, style;` | `for a camera row, shot scale, camera angle and movement, framing; for a style row, the rendering style and color mode of the frames; ... for a cross-shot row, the compared feature in each named shot.` |
| discovery V-L, status | `not_applicable (the shot's own text describes this entity differently ...; quote that text in observed)` | `not_applicable (the shot's own requirements in the contract describe this entity differently ...; quote them in observed)` |
| discovery V-L, frame_refs | `entity, relations or shot_text row` | `entity, relations, camera or style row`; adds `for a cross-shot row, at least one frame of every shot it names` |
| discovery V-L, issue_ids | `A transition row belongs to exactly one issue` | `A transition, style or cross-shot row belongs to exactly one issue` |
| discovery V-L, judging | none | adds `cross-shot rows: judge "expected" by comparing the named shots.` |
| discovery V-L, quotes | `literal quotes of the violated words ... (global_prompt, shot_prompt with shot_id, contract, or, for a transition row, shot_transitions ...)` | `literal quotes of the violated contract words ... (contract, or, for a transition row, shot_transitions ...)` |
| discovery V-L, expected | `what the text requires` | `what the contract requires` |
| discovery V-L, occurrences | `the violated row_ids of that shot` | adds `(a cross-shot row counts for every shot it names)` |
| discovery V-L, added entities | `(for example an unrequested prominent extra person, or a required object that appears only partly)` | `(for example a required object that appears only partly)` |
| discovery V-L, discipline | `Report only explicit text requirements.` | `Report only requirements in the template rows.` |
| discovery V-L, discipline | `difference that the text does not constrain` | `difference that the contract does not constrain` |
| review V-L, intro | `against the prompt and the contract` | `against the contract` |
| review V-L, inputs | `INPUT.original_prompt and INPUT.contract_json: the source text. Check every requirement against them directly.` | `INPUT.contract_json: the source of every requirement. Check each one against it directly.` and `INPUT.original_prompt: context only, not a checking basis.` |
| review V-L, section 1 | `explicit words of the text?` | `explicit words of the contract?` |
| review V-L, criterion 1 | `a literal quote of the source text` | `a literal quote of the contract` |
| review V-L, criterion 2 | `the shot's own text, the global prompt, or an episode-wide entity description ... in the shot's own text` | `a requirement of the shot, a cross-shot requirement that names the shot, the required cut at its boundary, or an episode-wide entity description ... in the shot's own requirements` |
| review V-L, requirement_absent | `the text does not state what the unit claims (say what the text does say)` | `the contract does not state what the unit claims, including a requirement that only the original prompt states (say what the contract does say)` |
| review V-L, not_applicable | `a different description in the shot's own text` | `a different description in the shot's own requirements` |
| review V-L, never reject | `the violating shot's own text only names the entity` | `the violating shot's own requirements only name the entity` |
| definitions, V-L | `contradicts an explicit requirement of the text: the global prompt, a shot prompt, the contract (...) or the required cut ...` | `contradicts a requirement of the contract (entity descriptions, shot presence, shot requirements, camera, style, cross-shot requirements) or the required cut ... The original prompt is context, not a checking basis; for the V-L branch, "text" in this section and in the table below means the contract.` |
| definitions, V-L test | `quote the violated words ... A detail the text does not state` | `quote the violated contract words ... A detail the contract does not state` |
| definitions, V-L | `in the contract (entity_descriptions) or in the global prompt applies ... A shot's own text overrides it` | `in the contract (entity_descriptions) applies ... A shot's own requirements override it` |
| definitions, V-L | `Exception: explicit continuity words (...)` | `Exception: explicit continuity words in the contract (...)` |
| definitions, table | `An unrequested entity appears: report presence_count only if it is prominent` | `nothing, unless the contract lists it as absent` |
| config, `presence_count` | `...; an unrequested prominent extra entity; ...` | removed |
| config, `row_kinds` (not sent to models) | shot_text row | camera, style and cross_shot rows |
| config, `single_issue_row_kinds` | `transition` | `transition`, `style`, `cross_shot` |
| config, `statuses.not_applicable` (not sent) | `the shot's own text` | `the shot's own requirements in the contract` |
| config, `decision_basis_definitions` (not sent) | three V-L entries in terms of the text | same entries in terms of the contract |
| schemas, V-L detection and review, records | quote `source`: global_prompt, shot_prompt, contract, shot_transitions | contract, shot_transitions |

Gates changed in round 2: judged cross-shot rows must cite every named shot; style and
cross-shot rows belong to one issue; an occurrence may cite a cross-shot row from any
named shot; prompt-only quotes are rejected.

### Round 1: v2 field names, no `continue`

| File | Before | After |
| --- | --- | --- |
| discovery V-L, inputs | `INPUT.contract_json: ... (entity_descriptions, entity_schedule, claims).` | v2 field list |
| discovery V-L, V-V, inputs | `INPUT.shot_transitions: the required transition ("cut" or "continue") at every shot boundary; INPUT.shot_sources: ...` | `INPUT.shot_sources: ...` (V-V adds `Every shot boundary is a cut.`) |
| discovery V-L, entity rows | `its episode-wide description (item_id "description") and each claim of this shot about it (item_id = claim_id, ...)` | `its episode-wide description (item_id "description"), its presence or absence in this shot, and each requirement of this shot about it (item_id = the requirement id, ...)` |
| discovery V-L, relations rows | `claims of this shot that relate` | `requirements of this shot that relate` |
| discovery V-L, transition rows | `the required cut or continue at the boundary into this shot.` | `the required cut at the boundary into this shot. Every shot boundary is a cut.` |
| discovery V-L, judging | `- claims: judge "expected"` | `- requirements: judge "expected"` |
| discovery V-L, judging | `a required cut must show a clear shot change (...); a required continue must continue the same take or moment.` | `the required cut must show a clear shot change (...).` |
| discovery V-V, inputs | `scheduled in two or more shots` | `scheduled (listed in the contract's presence) in two or more shots` |
| discovery V-V, boundary_checks | `exactly one entry per boundary of INPUT.shot_transitions, in order: the required transition, last_frame` | `exactly one entry per shot boundary, in shot order: last_frame` |
| discovery V-V, boundary_checks | `Whether a boundary realizes its required cut or continue is a V-L question` | `Whether a boundary shows a clear cut is a V-L question` |
| discovery V-V, provenance | `the contract entity label such as "Object 2"` | `the contract entity ID such as "2"` |
| review V-L, review V-V, inputs | `INPUT.shot_transitions and INPUT.shot_sources.` | `INPUT.shot_sources.` |
| definitions, V-L | `(scheduled in entity_schedule or visibly present)` | `(listed in the shot's presence or visibly present)` |
| definitions, V-V | `(same name or label, entity_schedule, "same", ...` | `(same name or contract entity ID, "same", ...` |
| definitions, table | `A required cut is missing or a required continue is broken` | `A required cut is missing` |
| config, `shot_structure` | `(a required cut or continue, a shot's content` | `(a required cut, a shot's content` |
| config, `required_transition` | `whether a boundary realizes its required cut or continue is a V-L question` | `whether a boundary shows a clear cut is a V-L question` |
| schema, V-V `boundary_checks` | property `required` (`cut`, `continue`) | removed |

The quote source name `shot_transitions` stays: a transition issue must still quote
something, and that quote is the row's item text.

## 6. Decisions for the owner

1. **Unrequested prominent entities.** V-L reported these through the shot-text row.
   With no row for them, V-L can no longer report one, and V-V reports one only if it
   is itself inconsistent, so an invented prominent entity now costs no score. I
   removed that wording because the owner's rule requires it; say if it should return
   in some other form.
2. **Prompt requirements outside the contract** are now unchecked by design. How much
   of the prompts that covers was not measured.
3. **`coordinate_frame`.** Items carry it, and it matters for the left/right rule
   (`entity` = the person's own side), but the V-L prompt does not define it. I did not
   add text, since the owner's authorization covers the checking basis only.
4. **The 50 camera values** in section 4, above all the 40 reverse views.
5. **`unresolved` in 201-400.** Until Q3, 192 of those contracts send their
   `unresolved` notes to the models inside `contract_json`.
6. **Entities in no presence list** (12; 10 of them only in `absent`) stay out of the
   registry, as unscheduled v1 entities did: their absence is checked, but a detected
   occurrence is not bound to the contract entity.

Resolved by the second decision: the frame limit on cross-shot checks, the undefined
`cross_shot` quantifier (cross-shot rows now have their own judging line), and the
shot-text row against "only unambiguous requirements".

## 7. Paper

- **Section 3.3.2** lists entity, relation, camera, style and transition rows but not
  the cross-shot rows, and "citing frames from both halves of the shot" does not hold
  for them (they cite every named shot). The mapping is in section 2.
- **Table 3:** cross-shot / absence is now **69 / 8** (paper says 50 / 8); the
  commented 400-episode row is 123 / 14 (says 81 / 14). `benchmark_stats.py` does not
  read the removed field.
- **Section 3.2** says the top-level list holds "how the camera changes from one shot
  to the next". True of the 42 moved items; 50 such values remain in shot blocks, 40
  of them reverse views.

Everything else in 3.1 to 3.3 that touches the contract or template matches the code.

## 8. Verification

- Tests, node 309 in allocation 343193: **198 passed, 1 failed** in the baseline set
  (was 162 passed). The failure is the known no-ffmpeg
  `test_recorded_cut_shots_extracts_planned_frames_from_a_real_video`.
- `tests/test_vl_vv_contract_v2.py` (35 tests) uses three real cleaned contracts as
  fixtures: projection, style, prepare, registry, binding and recovery inputs, matching
  payload, template rows, the new gates, continuity subjects, an offline run of all
  five model stages, the format guards, and no `continue` or shot-text row in rendered
  prompts.
- Audits of the backed-up files, 5,207 each round: 0 unexpected differences
  (`contract_rewrite_audit.json`, `contract_rewrite_audit_style.json`).
- All 400 current contracts pass the full read path with every requirement placed once,
  and shot IDs match all 1,000 first-200 task rows (`contract_read_check.json`).
- `tools/smoke_cli.sh`: `prepare` and `--dry-run` work from the command line.
- Schemas regenerate clean with `--check`.
- Copies before each round: `source_before/` and `source_before_style/`, each with
  `SHA256SUMS`, `contract_data_before.tar.gz` and per-file hashes.

Not related to this work: 9 tests fail in `test_shot_prompt_recovery.py` and
`test_gs_prompt_binding.py`. The recovery script lacks `materialize_review` and
`review_schema`, which those tests call, and neither script was changed here. A
separate proposal is open for them.
