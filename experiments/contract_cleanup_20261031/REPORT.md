# Contract cleanup, first 200 episodes (2026-10-31)

## Owner decisions applied

1. A contract is ground truth, so it holds only requirements the prompt fixes
   clearly. Wording with more than one reasonable reading yields no requirement,
   and the free-text `unresolved` field is dropped. (The owner never requested
   that field; the v1 spec of 2026-09-21 introduced it.)
2. Exception: whether mentions in different shots are the same entity is decided
   by the most likely reading in context.
3. Left/right with no stated frame and a person as subject is the person's own
   left/right (coordinate_frame `entity`). Applied interpretation, announced to
   the owner: positions in a frame composition, facing/profile orientation and
   entering or leaving the view stay screen; body sides stay anatomical; a
   stated frame stays as stated; animals and objects are left as they were.
4. The owner-deferred boundaries were not touched: focus/blur as camera
   information, "hold the shot", lighting stated in one shot, street/snow as floor.

## Deliverables

- `deliverables/contracts_1_200.jsonl`: model-facing contracts, generation
  priority 1–200, no `unresolved` field.
- `deliverables/contracts_1_200_with_evidence.jsonl`, `deliverables/index_1_200.json`.
- Per episode `episodes/<id>/`: `final_ops.json` (all operations on top of the
  frozen v2 contract), `contract.json`, `contract_with_evidence.json`,
  `cleanup_log.json` (dropped notes, note dispositions, identity decisions, id
  map), `review.json`, `resolution.json` where a disagreement was ruled on,
  `status.json`. `cleanup.py export` re-assembled every contract from its
  `final_ops.json` and found it identical to the stored one.
- The v2 inputs in `episode_contracts_v2_20261029/deliverables/` are unchanged
  (hashes pinned in `manifest.json`).

## Results

**Cleanup** (200/200 episodes). 481 notes disposed: identity 237, already
omitted 97, not an ambiguity 81, owner-deferred 38 (unchanged), non-identity
choice 28. 628 identity decisions (262 same, 366 separate).

**Independent review** (197 episodes with review items; 3 had none). 22
disagreements: 19 adopted the review, 1 kept the cleanup, 2 settled by the
owner's direction rule. Typical adopted reviews: a definite back-reference
("the red-and-gold partition") to a structure named earlier, an unnamed figure
who is the only other person in the story, and left/right that context fixes
(back to camera, profile, a shot laid out in screen terms).

**Direction rule.** 2,124 left/right items in 199 episodes: 811 decided by
program (382 no direction left in the requirement, 182 body sides, 247 frame
stated in the prompt words), 1,313 by Sonnet agents. A second pass re-checked
155 items flagged by verb and possessive patterns and changed 12. In the end 112
requirements were rewritten into the person's own frame; 946 were frame
positions, 104 stated frames, 81 body sides, 42 non-persons and 28
facing/profile.

**Contract totals (first 200), v2 → cleaned:** entities 2,978 → 2,945
(character 644 → 635, location 284 → 283, object 2,050 → 2,027; per episode
median 14, range 4–39 → 4–38); presence 6,268 → 6,263; spatial 7,449 → 7,424;
motion 3,550 → 3,545; per-shot appearance 1,418 → 1,417; cross-shot 50 and
absence 8 unchanged; unresolved notes 481 → 0.

## Usage

Claude Code subagents on Sonnet: cleanup 7,410,842 tokens (41 agents incl. the
pilot), review 4,228,650 (23 agents), direction pass 1,505,295 (13 agents incl.
pilot and re-check); 13,144,787 in total. This is Claude plan usage; the
subagent reports give only totals and no verified pricing was applied, so an API
cost equivalent is unavailable.

## Limitations

- All decisions are model judgments checked by mechanical gates, not human
  annotation; one independent review per episode. The direction pass ran after
  the review: its rewrites were not reviewed independently, apart from the
  re-check of the 155 flagged items.
- "Most likely" identity and "two reasonable readings" are judgment calls; the
  first agents and the reviewers disagreed on 22 items, so boundary cases remain.
- A few rewritten requirements mix frames in one sentence (a screen position and
  a person's own side) under coordinate_frame `entity`.
- The evaluator still reads v1 contracts; nothing here changes any evaluator
  stage or score.

## Next 200 (priority 201–400)

Same process (README.md): `cleanup.py prepare --start 200 --count 200`, cleanup
agents with `rules_cleanup.txt` (which now contains the direction rule),
independent review with `rules_review.txt`, rulings via `resolve_helper.py`,
then `direction_pass.py prepare` and the agent pass with `rules_direction.txt`
(the v2 contracts record many person directions in screen frame, so the pass is
still needed), a re-check of flagged items, and `cleanup.py export`.
