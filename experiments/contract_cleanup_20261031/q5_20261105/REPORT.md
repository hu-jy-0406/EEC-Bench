# Q5: the owner's four contract rulings applied to the first 200 contracts (2026-11-05)

## Owner decision

Rulings of 2026-11-01 (`EECBench/docs/open-questions.md` Q5): (1) focus, softness or blur is camera
information of that shot (`camera_view`); (2) "hold the shot / view / two-shot" is a static camera
(`camera_movement`); (3) lighting stated in one shot goes to the location description or to that shot, by
context; (4) a street, snow or similar ground is part of the location, not an entity. Go-ahead on 2026-11-05
("apply Q5"), after the assistant recommended applying them to the first 200 (the full-run scope) before the full
evaluation. Priority 201-400 are not cleaned yet; they get the rulings in their cleanup (rules updated).

## Process

Same structure as the cleanup and the direction pass (`../README.md`):

- `q5_pass.py`: each episode's Q5 operations are appended to its cleanup operations (`ops_before_q5.json` keeps
  the earlier ones) and the contract is re-finalized from the frozen v2 input with every cleanup check. Before the
  pass, rebuilding all 200 contracts from their operations reproduced them exactly (0 mismatches).
- `cleanup.py`: one new operation `add_requirement` (an appearance / spatial / motion requirement of one shot,
  with prompt quotes; used for lighting that is a state of one shot) and optional quotes on `edit_description`
  (an added attribute carries its prompt words). Pre-change copies with SHA-256 in `source_before/`.
- Rules for the agents: `../rules_q5.txt` (the four rulings with edge cases), review `../rules_q5_review.txt`.
  The pilot and the first agents raised edge cases; clarifications were added during the pass (copy of the first
  version: `rules_q5_wave1.txt`), and the independent review applied the final text to all 200 episodes:
  softness of part of the image ("softly visible", "recede softly", "a soft silhouette", "a soft foreground",
  motion blur) counts, softness as material, motion manner or light quality does not; an instruction to the
  camera to hold on a subject's view is a hold, holding an action or pose is not; lighting stated in every shot of
  the place, globally or carried over explicitly ("Preserve / Maintain ...", "the same amber-lit booth") is the
  place's lasting look, otherwise it belongs to its shot (the narrower requirement); a light source's own glow
  stays an attribute of that entity; a place the contract keeps as a location (a forecourt, a road vehicles travel
  along), landforms, banks and ledges are not ground.
- Pass: 1 pilot agent (3 episodes, inspected by the main session) and 20 agents of 10 episodes (Claude Code
  subagents on Sonnet). Every episode lists the statements it checked (`checked`, with outcome recorded /
  already_recorded / not_applicable).
- Independent review: 20 fresh agents, one verdict per operation and per checked statement, plus missed
  statements. 152 episodes without disagreement; 48 episodes with 77 open items (`disagreements.txt`).
- Rulings by the main session (`rulings.json`, `resolutions/`): 65 items adopted, 12 kept. Kept: an outcome label
  without contract change; "the same dim dance room" (the lighting word is carried over); a pool bank (a
  landform); wording with two readings ("a soft edge of his curls", "soft ceiling-light reflections", "a soft
  vertical reflection", "soft rectangular lamp highlights"); sunlight in 3 of 4 shots without carry-over;
  "a new, darker view" (a comparison); "nighttime atmosphere" (time of day, not lighting); highlights that
  follow from a recorded global light. Four agents wrote the corrected operations under these rulings (`check`
  only); the main session recorded every resolution (`resolve_all.py`), and each applied file equals the agent's
  final file.
- Export (`q5_pass.py export`): `../deliverables/contracts_1_200.jsonl` and `_with_evidence.jsonl` replaced; the
  previous files with SHA-256 are in `deliverables_before/`. New SHA-256: model-facing 6cfc0fa9..., with evidence
  d0e91773..., index c8f914be....

## Result (200 contracts)

| | before | after |
| --- | --- | --- |
| Q5 operations (final) | | focus/blur 130, hold 21, lighting 190, ground 7 |
| shots with focus/blur/softness in camera_view | 243 | 318 |
| shots with hold/static wording in camera_movement | 139 | 159 |
| camera_view / camera_movement set | 741 / 230 | 764 / 249 |
| entities (character / location / object) | 2,945 (635 / 283 / 2,027) | 2,935 (635 / 280 / 2,020) |
| presence / spatial / motion requirements | 6,263 / 7,424 / 3,545 | 6,245 / 7,422 / 3,545 |
| per-shot appearance requirements | 1,417 | 1,550 |
| cross-shot / absence | 92 / 8 | 92 / 8 |

- Entities drop by 10 (7 objects, 3 locations): ground merged into its location (snow, paths, a street, a
  walkway, grass, a game ground), some of it recorded as location entities before; presence and spatial counts
  follow from the merges.
- All 200 contracts build the evaluator's requirement list and prompt registry without error (requirement kinds:
  presence 6,245, description 6,245, spatial 7,422, motion 3,545, appearance 1,550, camera_view 764,
  camera_movement 249, style 85, cut 800, cross_shot 92, absent 8).
- Table 3 (`paper/uec-bench/stats/benchmark_stats.py`, `stats_200_cleaned.json`; previous values in
  `stats_200_cleaned_pre_q5.json`): entities 2,935 (635 / 280 / 2,020), presence 6,245, spatial 7,422, appearance
  1,550; the other rows are unchanged. The paper table is not edited.
- New cases (`prepare_case.py` resolves the exported cleaned contract) use the Q5 contracts; frozen cases and
  earlier results keep their own copies.

## Not done

- Priority 201-400: not cleaned yet; `../rules_cleanup.txt` now states the four rulings and points to
  `rules_q5.txt`.
- Agent judgment is not human annotation; edge cases were decided by the main session's rulings above.

## Usage

45 Claude Code subagents on Sonnet (1 pilot, 20 pass, 20 review, 4 corrections), 7,354,903 subagent tokens in
total (pass 3,529,451 including the pilot, review 3,285,831, corrections 539,621), as reported by the agent
runtime. These run on the Claude Code session, not the OpenAI API; the input / cached / output split and a cost
are not available. All tool commands were lightweight Python on the login node (`nice -n 19`), except the final
requirement-list check on allocation 354054 (CPU).
