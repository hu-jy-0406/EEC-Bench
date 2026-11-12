# Granularity pass: worn items and place parts become contract entities (contracts 1-200, 2026-11-11)

Times are Dubai time. Owner: "所有类别都加吧，同步改contract" (after "A全部纳入实体，B中除了14都纳入，如果和之前的规则有冲突就修改
之前的规则"); presence only in shots whose own text mentions the item ("只列该镜头文字提到的"). Basis:
`../../vl_vv_entity_scope_candidates_20261111/README.md`. Detection side: `../../vl_vv_entity_scope_20261111/README.md`.

## Process

- Program `../g_pass.py` (show / check / apply / review-show / review-record / resolve-show / resolve / ruling /
  status / export), built on `../cleanup.py`, which gained two operations: `add_entity` (new entity, presence and
  absent shots, each listed shot needs an evidence quote from that shot or the global prompt) and
  `retarget_requirement`. The pass appends its operations to each episode's cleanup operations (after the Q5 pass;
  `ops_before_g.json` keeps the operations before it), so every existing contract check still applies.
- Rules: `../rules_g.txt` (G1 worn or carried items, G2 walls, floors, ceilings, ground, floor coverings, trees and
  plants; presence rule; what moves out of descriptions; retargeting). Review `../rules_g_review.txt`, resolution
  `../rules_g_resolve.txt`.
- Pilot: one agent, 3 episodes, inspected by the main session. Pass: 20 agents (10 episodes each, 7 in the last).
  Independent review: 15 fresh agents, one verdict per operation and per checked mention, plus missed mentions.
  Resolution: 9 fresh agents ruled on every open point (keep_g / adopt_review, corrected operations checked before
  `resolve`). Main-session consistency rulings with `ruling` on 4 episodes (below).
- Claude Code subagents on Sonnet (owner: no OpenAI API for contract work): 46 agents, 10,069,083 subagent tokens
  as reported by the agent runtime (pass 4,622,590 including the pilot; review 3,876,356; resolution and the -clad
  ruling 1,570,137). These run on the Claude Code session; an input / cached / output split and a cost are not
  available.

## Assistant rulings inside the owner's presence rule (added to rules_g.txt during the pass)

Several agents read borderline wording differently; these rulings were added so that the review and resolution
judged all episodes the same way:
- A collective clothing word ("their clothing", "the same outfit") mentions every garment of that person the prompt
  names (tops, outerwear, dresses, trousers, skirts, ties, scarves, belts, footwear, headwear), not eyewear, jewelry,
  watches, badges, lanyards or bags; "appearance" alone mentions none.
- An item word inside a person's description or label in the shot's text mentions that item ("the dark-shirted
  man", "the Mint-blouse woman", "bespectacled", "suited", "uniformed", "in camouflage"); a set word refers to the
  pieces the prompt describes ("Blue-uniformed man" -> his shirt, tie and cap). "<color>-clad" attached to a person
  names that person's clothing; attached to a body part ("black-clad shoulder") it does not.
- A body part is not a garment mention unless the words name the garment ("white-shirted shoulder" yes,
  "patterned shoulder" no).
- A mounting compound ("wall light", "wall clock", "floor lamp", "floor candles") names the object, not the surface;
  a phrase naming a particular wall ("on the rear wall", "rear-wall urinals") mentions it.
- A wall or floor covering named inside a place's description mentions it ("peach-walled", "wood-paneled",
  "carpeted"); a surface adjective of a place kept as a location ("cobbled alley", "grassy clearing") creates no
  ground entity; "tiled"/"tiles" without saying wall or floor is ambiguous and creates no entity.

Main-session rulings (`ruling` command; status keeps the review and resolution record): JRuA4AnW_cw_s00080 ("Armored
man" lists the arm and shin armor in Shots 1-4, as the uniformed-label rulings); y2wupV34DRk_s00021,
_RWbXkm4JQY_s00261 and 8TH72R2BIS4_s00034 (-clad person labels).

## Result (`../g_stats.py` -> `stats.json`)

| | before (2026-11-05 export) | after |
|---|---|---|
| entities | 2,935 | 4,438 (+1,289 G1 worn items, +214 G2 place parts) |
| presence entries | 6,245 | 9,224 |
| shot requirements (appearance, spatial, motion) | 12,517 | 12,517 (some retargeted to the new entities) |
| cross-shot requirements | 92 | 92 |
| compiled V-L template rows | 9,023 | 12,004 |
| compiled requirement-list entries | 27,005 | 32,963 |

Review outcome: about half of the episodes had no open point; resolution adopted most review points (the most
common: an item named in a person's label missing from that shot's presence, mounting compounds counted as walls,
ambiguous tiles made entities). Checks: every episode's operations pass `check`; `export` rebuilt every contract from
its operations and matched the stored files.

## Files

- Exported: `../deliverables/contracts_1_200.jsonl`, `..._with_evidence.jsonl`, `index_1_200.json`; previous
  export (2026-11-05, after Q5) in `deliverables_before/`.
- Compiled requirement packages recompiled (`scripts/compile_episode_requirements.py --update`: 200 updated, 200
  unchanged); previous packages in `compiled_before/`.
- Per episode: `episodes/<id>/g_ops_applied.json`, `g_review.json`, `g_resolution.json`, `g_ops_resolved.json`,
  `ops_before_g.json`.
- Audits: `../g_audit.py` (place adjectives; 5 flagged shots were all false positives such as "paneled door"),
  `../g_open.py` (resolution assignment).
- Priority 201-400 get the same rules when they are cleaned.

Agent judgment is not human annotation; residual differences remain in borderline wording ("the woman in white",
garment parts such as cuffs and sleeves). The new contracts are not yet used in an evaluation run.
