# Entity granularity consistency: EntityBench vs our Full400 contracts (2026-10-21)

Question (owner): is EntityBench's entity granularity consistent, or are the
same kinds of items sometimes independent entities and sometimes attributes?

Method: `wearables.py` → `wearables.json` (worn items: garments and
accessories; English keyword matching, approximate). A worn-item word is
"promoted" when it occurs in an Object name and "nested" when it occurs only
in a Character description. Spot checks on EntityBench episode
`00000865…__run1__i50_j84__T420`.

## Worn items

| | EntityBench (140 episodes) | Ours (400 contracts) |
| --- | --- | --- |
| Episodes with both promoted and nested-only worn items | 124 / 139 | 88 / 338 |
| Characters with ≥2 worn items, some promoted and some not | 233 / 431 (54%) | 9 / 341 (3%) |
| Promoted worn items also named in a character description (stored twice) | 483 / 617 (78%) | 25 / 156 (16%) |
| Same word promoted in some episodes, nested-only in others (episodes promoted / nested-only) | shirt 78/44, jacket 49/45, suit 50/27, t-shirt 32/31, glasses 26/27, tie 11/37, uniform 27/11, dress 16/19, sweater 19/12, necklace 16/13 | shirt 1/198, glasses 20/52, earring 5/36, coat 5/35, necklace 12/21, hat 8/24, cap 2/30, wristwatch 17/4, ring 13/2 |

EntityBench additionally schedules a promoted worn item mainly where the
action text names it: relative to the character it co-occurs with most, a
promoted item is scheduled in a median 20% of that character's shots, in all
of them for 2.3% of 487 items, and in fewer than half for 78%. Part of this is
genuine costume change (Sung-min wears a bloodstained T-shirt, later a denim
jacket), but the spot check shows mention-driven scheduling: Seo-joon's grey
sleeveless hoodie, also part of his character description, is scheduled in 2
of his 8 shots. The same check found an identity inconsistency: the
"WHENEVER" sweatshirt is in Yuna's description, while the action text puts it
on So-hee in several shots.

## Other granularity choices in EntityBench

Promoted to objects in some episodes: visual effects and lighting ("the intense
red glow", "the bokeh lights", "the roiling smoke and flames", "the
electrical energy arcs"), injuries and stains ("the deep gash", "the blood
spatter", "the bloody hand bandage"), collections ("the primitive huts", "the
framed movie posters"), parts of places (doors, windows, a wall sconce). In
other shots comparable things stay in a location description or are named in
the action text without being scheduled (for example a brick wall, a desk, a
service counter; `../entitybench_mentions_20261021/`).

## Reading

- EntityBench's granularity is not consistent: for most garment and accessory
  types the choice between entity and attribute is close to even across
  episodes, mixes within an episode and within one character, often stores the
  same item twice, and schedules promoted items only where the text names
  them. This follows from its construction (registries proposed by an LLM from
  source media per time chunk, merged, then schedules repaired against the
  action text), which has no explicit granularity rule.
- Our contracts follow a stated rule ("clothing/hair/body parts that merely
  describe a character can remain character attributes"): garments are almost
  always attributes and within-character mixing is rare. Our inconsistency is
  concentrated in accessories across episodes (glasses, necklaces, hats,
  earrings mostly attributes; watches and rings mostly entities).
- In EntityBench's evaluator a promoted garment is judged both under its
  wearer's "clothing and accessories" criterion (every scheduled shot of the
  wearer) and as an object (only where scheduled), so the inconsistency
  changes which items get object-level and cross-shot scoring.
