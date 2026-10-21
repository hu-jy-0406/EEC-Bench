# How EntityBench builds entity schedules, and what it does with entities the schedule omits (2026-10-21)

Question (owner): does EntityBench also have prompt-mentioned entities without
their own registry/schedule entry, how does it handle them, and what does that
imply for our entity provenance and prompt-binding design?

Sources: the released repository (`EntityBench/`, 140 episode scripts and the
evaluator `eval/evaluate_benchmark.py`; the construction code is not released)
and the paper (arXiv 2605.15199, §3.1 and Appendix B). Counts:
`count_mentions.py` → `entitybench_mentions.json` (keyword/name matching,
approximate); `sample_shots.json` (25 random shots read by the assistant).

## How the registry and schedule are built (paper §3.1)

- Scripts are derived from real narrative media. Characters are detected,
  tracked and clustered (face/body embeddings, then LLM deduplication); objects
  and locations are proposed by an LLM as local registries per time chunk,
  merged into episode identities and verified against script and video.
- Character descriptions are rewritten to focus on face and demographics
  (actions and transient states removed); clothing and accessories stay in
  them. Action text is then enriched from the resolved schedule.
- Verification is one-directional: "every entity in a shot's entity schedule
  is actually mentioned in the action text"; mismatches are repaired by adding
  the mention or removing the entity from the schedule. Nothing checks that
  everything the text mentions is scheduled.

So the registry and schedule are an inventory of the tracked, mostly recurring
entities that the benchmark evaluates, not an inventory of everything the
prompt names.

## The same gap exists in EntityBench

| | EntityBench (140 episodes, 2,491 shots) | Our first-200 contracts (1,000 shots) |
| --- | --- | --- |
| Episodes with a worn/carried item named only inside a character description | 92/140 (218 mentions: tie 44, glasses 31, cap 20, necklace 16, hat 13, helmet 12) | 95/200 (180 mentions) |
| Same kinds of items given their own entry | 173 | 17 |
| Objects that are garments/accessories ("the grey sleeveless hoodie", "the dark suit", "the 'WHENEVER' sweatshirt") | 673 of 2,080 objects (32%); 432 also share a garment/accessory word with a character description (often the same item described twice) | few |
| Shots whose text names a registered entity not scheduled in that shot (whole-word match) | 96 (3.9%), e.g. "sits in his manual wheelchair", "wearing a dark suit" | 23 (2.3%; several generic names such as "Window", "Sky") |
| Scheduled names without a registry description | 57 of 11,437 ("the stack of papers", "the black backpack") | 0 of 6,776 |
| Unregistered things named in the action text (manual, 25 random shots) | 11/25 shots: desk, food counter, service counter, plate of food, spectators, pedestrians, "another soldier", "a scared figure", a large screen | not measured |

## How EntityBench handles them (evaluator)

- **Only scheduled registry entities are evaluated.** Grounding, presence,
  per-entity fidelity and cross-shot consistency run over the shot's scheduled
  entities and their registry descriptions (`ground_entities_in_frame` builds
  its list from the schedule). Anything else is out of scope.
- **Worn items inside a description are part of the character.** Both the
  intra-shot fidelity judge and the cross-shot judge score characters on face,
  hair, "clothing: clothing style, color, and accessories" and build. Glasses
  or a tie in the description are judged as the character's appearance.
- **Promoted wearables are judged twice.** When a garment is also an object
  entry, it is grounded and scored as an object (shape, color/texture,
  proportions, details) in addition to the character's clothing criterion.
- **Unscheduled mentioned objects** only enter action fidelity: the
  `object_interaction` criterion is asked only when a scheduled object's name
  occurs in the action text (`object_in_action`); otherwise it is skipped.
- **No prompt-bound / prompt-unbound notion.** Unmentioned or invented content
  is never evaluated, so EntityBench never has to decide whether an entity is
  "unintentional". It sidesteps our provenance question rather than solving it.

## What this suggests for our design (for the owner's decision; nothing changed)

1. The gap is inherent to the EntityBench format, not a defect of our contract
   compiler: both datasets show it at similar rates.
2. EntityBench's provenance-free design works because it evaluates only the
   registry. We additionally evaluate unintentional entities, so we need to
   know what the text mentions; EntityBench offers no ready answer.
3. A construction-time variant of the mention list: EntityBench verifies
   scheduled ⇒ mentioned. Adding the reverse check when compiling a contract
   (every physical thing a shot text names is a scheduled entity, an attribute
   inside a scheduled entity's description, or recorded as an unregistered
   mention with its quote) would produce the mention list as part of contract
   construction and verification, instead of as a separate later step.
4. A promotion criterion, if items ever get their own entry: EntityBench's data
   suggest promoting a worn/carried item only when it is treated as a thing in
   its own right (named "the …", acted on, handed over, taken off, or recurring
   independently); otherwise keep it as a character attribute.
5. EntityBench judges an undescribed accessory as part of the character's
   clothing consistency; the owner's rule (2026-10-21) makes an unnamed watch
   prompt-unbound. The difference only affects the unintentional-entity
   statistic, not whether a change is reported as a V-V issue.

## Limits

The construction rules are taken from the paper text and the released data;
the construction code is not public. Counts use English keyword or name
matching and are approximate; the unregistered-mention rate comes from 25
manually read shots.
