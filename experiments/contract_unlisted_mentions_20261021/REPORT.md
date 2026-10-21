# What the Full400 prompts mention without an own contract entry (2026-10-21)

Question (owner): in our benchmark, what are the main types of entities that
are mentioned in the prompt but not explicitly listed in the contract?

Data: the 400 delivered contracts
(`../episode_contracts_20260921/deliverables/episodes/*/contract.json`, 2,000
shots, 7,425 entity records, mean 18.6 per contract). Two methods:

- `count_unlisted.py` → `unlisted_counts.json`: English keyword hits in the
  global and shot prompts, once per (episode, keyword), classified as listed
  (word in an entity name), nested (in an entity description or claim),
  unscored (only in the coverage `unscored` quotes) or missing. Approximate:
  "light" also matches colour adjectives ("light blue"), "camera" is mostly
  the viewpoint, a name match does not prove it is the same thing.
- `manual_sample.json`: 24 random shots read by the assistant against their
  contract's entity names.

## Result

| Type (unlisted) | Keyword count: mentions / own entry / nested / unscored / missing | Manual sample (shots of 24) |
| --- | --- | --- |
| Clothing of characters (shirt, top, trousers, jacket, sleeves, suit, collars, swimsuit, footwear) | 1,086 / 40 / 1,045 / 1 / 0 | 19 |
| Worn accessories (tie, glasses, necklace, cap, scarf, hood, belt, wristbands) | 513 / 135 / 375 / 0 / 3 | 6 |
| Lighting and atmosphere (light, glow, shadows, reflections; inflated by colour adjectives) | 499 / 126 / 296 / 74 / 3 | 8 |
| Parts of listed entities (a robot's sensor plate and lens, a wheelchair's wheel and frame, a box's base and panel, notebook pages, tree bark) | not countable by keyword | 4 |
| Body features and marks (hair, beard, teeth, blood streaks, an animal's beak and feathers) | not counted | most shots |
| Printed graphics / emblems on clothing; visual effects (a hair-like dark outline) | not counted | 3 |
| Furniture and fixtures | 1,033 / 947 / 72 / 8 / 6 (window, doorway, wall, floor as parts of places) | 0 |
| Held or carried props | 284 / 199 / 73 / 11 / 1 (mostly "camera" = viewpoint) | 0 |
| Nature and scenery | 310 / 238 / 65 / 6 / 1 | 0 |
| Background people and crowds | 165 / 94 / 54 / 10 / 7 (unscored/missing hits are mostly "both figures"-style references to listed characters) | 0 |
| Vehicles, animals | 89 / 74 / 15 / 0 / 0 | 0 |

## Reading

- The things our prompts mention without their own entry are overwhelmingly
  **appearance details of listed entities**: clothing, worn accessories, body
  features, and parts of listed objects, plus lighting. They are recorded
  inside the owner's description or in appearance claims (the compiler's
  coverage rule requires every substantive phrase to be a claim or an
  explained unscored entry); genuinely uncaptured mentions are rare.
- Unlike EntityBench (`../entitybench_mentions_20261021/REPORT.md`), set
  elements, props, furniture, vehicles, animals and background people are
  almost always their own entries, as the compiler rules require ("visible
  furniture, architecture/vegetation/background entities explicitly
  described" are objects; "clothing/hair/body parts that merely describe a
  character can remain character attributes").
- Promotion of accessories and visual phenomena is inconsistent across
  episodes: "Hoop earring", "Sunglasses", "Dark watch", "Woman's pendant",
  "Robot shadow", "Tree reflections" are entries in some contracts, while
  glasses, scarves, necklaces and shadows stay attributes in others.
- For provenance this narrows the problem: what the V-V register might split
  out as a separate entity while the contract keeps it as an attribute is
  mainly worn accessories, garments and parts of listed objects.
