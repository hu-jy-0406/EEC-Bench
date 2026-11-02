# Episode contract v2 layout (draft)

Status: requested by the owner on 2026-10-27; all 400 contracts are rewritten in
this layout and the first 200 cleaned (see "Full rewrite" below). Contract v2 is
the evaluator's default contract since 2026-11-01 (`scripts/episode_contract.py`,
`experiments/vl_vv_contract_v2_adapt_20261101/`). The v1 contracts
(`docs/episode-schedule-claims-v1.md`) are read only by the older chains and for
reproducing historical results.

## Owner requirements (2026-10-27)

1. `entity_descriptions`: keys are integer IDs counted from 0 (JSON string keys
   `"0"`, `"1"`, …). `label` is one of `character`, `location`, `object`,
   without a number. The old `Character N` key duplicated the label.
2. The per-shot organization replaces `entity_schedule` and its unclear
   `"1:1"`, `"1:2"` keys. For each shot:
   1. the location entity ID(s). **Location rule (owner, 2026-10-27):** list
      only the main setting where the shot takes place. List two locations
      only when the camera moves from one location to another within the
      shot (in the order visited). A place merely visible from the main
      setting (a hallway through a doorway, the sea from a beach) is not a
      shot location; it stays in `presence`;
   2. a shot description: camera view, camera movement and style, each null
      when the prompt states none. Every shot boundary is a cut (owner,
      2026-11-01), so the contract states no transition; a requirement on how
      the camera changes between shots belongs in `cross_shot`;
   3. `presence`: the IDs of every entity that should appear, locations
      included;
   4. `appearance`: only noteworthy requirements. By default an entity's
      appearance is its entity description; list here only what changes in this
      shot or needs emphasis;
   5. `spatial`: as currently defined.
3. Two versions of every contract: one with evidence and one without. The
   benchmark run gives the version without evidence to the evaluating model.

## Entity granularity (owner, 2026-10-27)

Rules first given on 2026-10-27, boundaries fixed by the owner's rulings on
the 26 examples in `experiments/contract_format_v2_20261027/granularity_examples.md`
(2026-10-29). Only things the prompt names are contract entities.

- **Worn and held items** are separate entities when the prompt describes an
  action with or on the item itself: it is the centre of an event (a pistol
  held to a temple, a cap pulled off and put down, a phone raised to the ear)
  or it is handled at all (raised, lowered, moved, gripped, held up, used).
  Items that are only worn or carried, with no action on them (a badge on a
  lanyard, a coat over the forearm, a watch on a lifted hand, glasses), stay
  in the owner character's description, including such items that v1 listed
  separately.
- **Collections** are one entity (loose papers, city buildings, a group of
  desks, a crowd of guests, people as a group). Members the prompt describes
  separately (a front mug and a rear mug, two different pairs of sunglasses)
  are separate entities. (The owner did not object to this reading.)
- **Walls, floors and ceilings** are not entities; they are part of the
  location description (floors and ceilings confirmed by the owner on
  2026-10-29).
- **Every other structural part the prompt names is a separate entity**:
  doors, doorways, windows, window frames, grilles, curtains, pipes, valves,
  wall or ceiling fixtures (sconces, towel rings), whether or not anything
  happens to them.
- **Furniture and props the prompt names are separate entities**, including
  background furnishings (bottle shelves, fairy lights) and small items on a
  surface (a shaker, a cup, a lamp, desktop papers).
## Layout

```
{
  "schema_version": "episode_contract_v2_draft",
  "episode_id": "...",
  "entity_descriptions": {
    "0": {"label": "character", "name": "...", "description": "..."},
    ...
  },
  "shots": [
    {
      "shot_id": "Shot1",
      "locations": [4, 5],
      "shot_description": {
        "camera_view": "..." | null,
        "camera_movement": "..." | null,
        "style": "..." | null
      },
      "presence": [0, 1, 2, 4, 5, 6, 7, 8],
      "appearance": [{"id": "S2-app-1", "entities": [5], "expected": "...", "quantifier": "when_visible"}],
      "spatial":    [{"id": "S1-spa-1", "entities": [6, 4], "expected": "...", "predicate": "...",
                      "coordinate_frame": "...", "quantifier": "..."}],
      "motion":     [{"id": "S1-mot-1", ...same fields as spatial...}]
    }
  ],
  "unresolved": ["..."]
}
```

The evidence version (`contract_with_evidence.json`) has the same content plus:
`evidence` (prompt quotes with shot IDs) on every entity, requirement and shot
description field; `source_claim_ids` (v1 claim IDs) for
traceability; `source_label` (v1 key) on entities; and a copy of the `prompt`.
The model-facing `contract.json` drops all of these.

## Style (owner, 2026-11-01)

`shot_description.style` holds the visual or render style the prompt explicitly
states ("stylized 3D animation", "hand-drawn cel-animation", "black-and-white"),
in the prompt's own words. A style in the global prompt applies to every shot; a
style in one shot prompt applies to that shot only, and a shot's own statement
replaces the global one there. Expressions ("animated face"), clothing
("black-and-white suit"), a single entity or prop, a picture inside the scene and
plain colour grades are not styles. Location descriptions are not changed
("Painterly animated bedroom" stays). The evidence version records the quote;
`shot_id` is `global` for a global style.

## Additions confirmed by the owner (2026-10-29)

- `cross_shot`: top-level list for requirements that span shots (v1 has 91
  multi-shot claims, e.g. "Shot4 position matches Shot2"), including how the
  camera changes between shots (`dimension` spatial, `coordinate_frame` camera,
  e.g. "The woman is shown more closely in Shot3 than in Shot1.").
- Per-shot `absent`: entities the prompt says are not visible (14 v1 claims).
- Per-shot `motion`, with the v1 definition.

## Full rewrite (2026-10-29)

All 400 contracts are rewritten by Claude Code subagents (Sonnet; owner's
choice instead of the OpenAI API) following
`experiments/episode_contracts_v2_20261029/rules_v2.txt`; each decisions file
must pass `rewrite.py check` before `rewrite.py finalize`. Every episode then
got one independent subagent audit pass (owner's choice, after a sample of 40
needed 26 revisions): 153 pass, 247 revised. Outputs:
`experiments/episode_contracts_v2_20261029/deliverables/`.

## Rules used for the example conversion

- Entity order: characters, then locations, then objects, in v1 order.
- `presence` = the v1 schedule of the shot (identical to its v1 presence
  claims, all `present` / `exists`).
- `locations` follows the location rule, from the decisions file (the v1
  schedule lists every visible place).
- Entity descriptions were rewritten from the prompt wording to contain every
  stable appearance attribute the prompt states anywhere; v1 appearance claims
  covered by a description were folded into it. A v1 appearance claim stays as
  a per-shot `appearance` requirement only if it is shot-specific (in the
  example only "the office is lit by daylight", stated in Shot2 alone).
- Spatial and motion claims are kept unchanged apart from the ID format and
  entity IDs. `depends_on` is dropped: a requirement on an entity in a shot
  implicitly depends on that entity's presence in the shot.
- Camera instructions, which v1 recorded as unscored coverage text, fill
  `camera_view` / `camera_movement`; a v1 spatial claim that only describes
  framing ("both visitors visible from about the waist up") moved into
  `camera_view`.
- Every v1 claim is accounted for in `claim_accounting.json`.

## Open points for the owner

- `motion` was not in the owner's list; the example keeps it as a per-shot list
  with the v1 definition so that no requirement is lost.
- Resolved 2026-10-27: `locations` stays a list but follows the location rule
  above (in the example every shot is in the office, so each lists only the
  office; the hallway seen through the door stays in `presence`). In v1, 102
  of 2,000 shots list two places and 12 list three to five; most are
  adjacent spaces seen through a door or window, or sub-areas of one setting.
  107 v1 shots list no place; the example convention for such shots is an
  empty list (not yet confirmed by the owner).
- What counts as "needs emphasis" for per-shot appearance. The example lists
  no restatements (e.g., Shot3 repeating "Wooden office desk"), only
  shot-specific attributes.
- Moving a shot-introduced attribute into the episode-wide description makes it
  a requirement in every shot where the entity appears (e.g., the art is
  "abstract" only in Shot3's text). This follows the existing rule that a
  description applies to every shot unless the shot describes it differently.
- v1 `coverage` (sentence → claim map, unscored text) and the `alignment_contract`
  derivative are not regenerated in the example.
- Entity/attribute granularity (pending owner decision) may change which items
  are separate entities, e.g., the badge or glasses inside character
  descriptions.
