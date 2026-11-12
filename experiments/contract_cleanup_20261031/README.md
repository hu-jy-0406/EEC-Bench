# Contract cleanup: only unambiguous requirements (2026-10-31)

Owner decision (2026-10-31): a contract is ground truth, so it may contain only
requirements the prompt fixes clearly. Wording with more than one reasonable
reading yields no requirement, and the `unresolved` field is dropped. The one
exception is entity identity: whether mentions in different shots are the same
entity is decided by the most likely reading in context, because identity
cannot be left open and it decides what cross-shot consistency is checked
against. The owner never requested `unresolved`; the v1 spec (2026-09-21)
introduced it and the v2 rewrite carried it over.

Scope: first the 200 episodes already evaluated (generation priority 1–200).
The owner wants the remaining 200 (priority 201–400) cleaned later with the same
process when Claude usage allows.

Input: the frozen v2 contracts in
`EECBench/experiments/episode_contracts_v2_20261029/deliverables/episodes/`
(read only; hashes pinned in `manifest.json`). Nothing there is modified.

## Process

1. Register episodes: `python3 cleanup.py prepare --start 0 --count 200`
   (for the second half: `--start 200 --count 200`).
2. Cleanup: Claude Code subagents on Sonnet (owner: no OpenAI API for contract
   work), a few episodes per agent, follow `rules_cleanup.txt`: `show`, write
   `episodes/<id>/ops.json`, `check` until PASS, `finalize`. The program applies
   the operations (remove/rewrite requirement, camera value, description edit,
   merge, split), renumbers entity ids, validates (exact quotes, references,
   presence, every note disposed exactly once, identity decisions consistent
   with the result) and writes `contract.json` (model-facing),
   `contract_with_evidence.json`, `cleanup_log.json` and `review.md`.
3. Independent review: a fresh Sonnet subagent per batch follows
   `rules_review.txt` for every episode with at least one identity decision or
   change (`review-show`, `review.json`, `review-record`). It sees the original
   contract and the decisions, not the first agent's reasons.
4. Disagreements are resolved by the main session (Opus) with
   `resolve_helper.py resolutions/<id>.json` (rulings keep_cleanup /
   adopt_review / owner_rule), recorded in `episodes/<id>/resolution.json`; a
   changed outcome re-finalizes from corrected ops that pass `check`.
5. Direction rule (owner, 2026-10-31: left/right with a person as subject and no
   stated frame is the person's own left/right): `python3 direction_pass.py
   prepare` lists every left/right item (program-decided where obvious), Sonnet
   agents classify the rest with `rules_direction.txt` and `apply`; then build
   `directions/recheck_list.json` (verb/possessive patterns on items not judged
   person directions, see REPORT.md), re-check them with
   `rules_direction_recheck.txt` (`recheck-show`, `recheck-apply`).
6. `python3 cleanup.py status`, then `python3 cleanup.py export` writes
   `deliverables/contracts_<first>_<last>.jsonl` (model-facing) and
   `..._with_evidence.jsonl` plus an index.

## Status

First 200 complete (STATUS.md, REPORT.md).

## Changes after the first 200 (2026-11-01)

`shot_description.transition_from_previous` is gone from all contracts: every
shot boundary is a cut. Camera requirements that only compare a shot with a
named other shot moved to `cross_shot` (op `camera_to_cross_shot`); details and
copies of the previous files are in
`EECBench/experiments/vl_vv_contract_v2_adapt_20261101/`. `manifest.json` pins
the v2 inputs after that change.

## Owner rulings on four boundaries (2026-11-01; applied to 1-200 on 2026-11-05)

Focus/blur is camera information (`camera_view`); "hold the shot" is a static camera in `camera_movement`;
one-shot lighting goes to the location or that shot by context; street/snow ground is part of the location.
Applied to the first 200 with `q5_pass.py` (operations appended to each episode's cleanup operations,
re-finalized, independently reviewed, rulings by the main session) and exported to `deliverables/`
(previous files in `q5_20261105/deliverables_before/`). Rules `rules_q5.txt`, review `rules_q5_review.txt`,
report `q5_20261105/REPORT.md`. `rules_cleanup.txt` now states the rulings for the remaining 200.

## Worn items and place parts as entities (owner, 2026-11-11; applied to 1-200 the same day)

Owner: "所有类别都加吧，同步改contract"; presence only in the shots whose own text mentions the item. Applied with
`g_pass.py` (rules `rules_g.txt`, review `rules_g_review.txt`, resolution `rules_g_resolve.txt`) and exported to
`deliverables/` (previous files in `g_20261111/deliverables_before/`); report `g_20261111/REPORT.md`. Priority
201-400 get the same rules when they are cleaned.
