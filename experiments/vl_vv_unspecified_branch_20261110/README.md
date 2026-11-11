# Unspecified branch for V-V (2026-11-10)

Times are Dubai time. Experiment folder only: frozen code copy, no live pipeline, AGENTS.md or paper change, no commit.

## Why

None of the 12 V-V variants tried on 2026-11-10 (summary page https://claude.ai/artifact/H3Ujs7tNKAeFjoc2RCkxRv)
recovered more than 2 of the 13 owner-verified problems of unprompted objects; N2 recovered 2 of 14 on new videos.
The common failure: the V-V model is asked to notice small background differences across several images at once. The
proposed branch splits the work into what GPT-6 Luna can do: list objects per shot, compare lists as text, then check
one specific suspect on a few frames. Owner: "好的，尝试一下添加unspecified分支。U1最好是在前面流程找到的unspecified实体基础上做补充，
这样显得逻辑顺畅一些" (approved after the cost estimate of about USD 0.3-0.6 for the test).

## Design (`run_u_branch.py`; prompts in `prompts/`)

- U1, per shot (Luna low, the shot's six keyframes): starts from the ledger's unspecified entities of the shot
  (REGISTERED_UNSPECIFIED, with their boxed frames) and keeps each one, then adds the background objects the ledger
  misses (same exclusions as the entity rules: walls/floors/place, worn items not handled, body parts, parts of
  registered objects). Per object: description, location, frames visible, change within the shot; plus the view.
- U2, per video (Luna medium, text only): the inventories, shot texts and contract places; at most 10 suspects
  (within shot: a described change or a presence gap; across shots: same object described differently, or an object
  at a place both views show listed in one shot only), each with 2-4 frames to check.
- U3, per suspect (Luna high, only those frames): real / not_real / unclear; a real one comes with a V-V issue
  (subcategory from an object-related list, Chinese description and evidence).
- Real suspects become V-V candidates (checklist item O1; subjects are ledger ids, or added entities n1... made from
  U1's new objects, labelled unspecified), then the frozen chain v6 V-V review (two calls, Luna low) runs on these
  candidates only. No scoring; the branch's issues are not merged with the main V-V issues in this test.
- Host: the rerun v3 cases (frontend, ledger, contract) and their V-V detection records (entity records), read only.
- Code: `code/EECBench`, a copy of the live tree at 21:09 (`SHA256SUMS_code_frozen`). Every call uses the repair loop.

## Checks

- `test_offline.py` (fake transport, real #078 case): U1 once per shot with six frames and the shot's ledger
  unspecified entities; the gates reject a missing or unknown registered entity, a within-shot suspect with two shots,
  a check frame outside the suspect's shots, and evidence on an unattached frame; the built detection result passes
  the frozen review's loader; new objects become n1, n2 labelled unspecified. Passed.
- Live trial #078 (21:12): 14 inventory objects (6 new), 1 suspect (TV cabinet ge0003 white in Shot2, dark wood in
  Shot5), U3 real, review confirmed with subject ge0003 (unspecified); USD 0.011.

## Runs

All 28 videos (8 development videos holding the 13 owner targets, 20 validation videos with 14 audit targets),
started 21:13, allocation 356508, 4 videos at a time, cap USD 1.0. Results: `runs/`, `sheet.md`, `usage.json`.

## Results (runs 21:13-21:17 Dubai; `sheet.md`, `usage.json`, `target_matches.json`)

- 28/28 videos succeeded. Cost (GPT-6 Luna standard-price estimate, not a bill): USD 0.145335 in total, USD 0.0053 per
  video (dev 0.052704 for 8, val 0.092631 for 20), about USD 5 per 1,000 videos; 30-60 s per video.
- U1 listed 163 objects (96 new, the rest ledger unspecified entities kept); U2 raised 25 suspects; U3 judged 7 real;
  review confirmed 6 (all with an unspecified subject), rejected 1.
- Targets (assistant matching): dev 1 of 13 found (#078 TV cabinet) plus 1 partial (#055 countertop items, part of the
  bundled furnishings target); val 0 of 14 (the #036 Wan2.2 shrubs were raised within the shot and rejected by review,
  the camera tilts). For comparison: N2 dev 2/13, val 2/14; night C dev 2/13.
- Where targets are lost: U2 did not raise 6-7 targets whose object U1 had listed in one shot and not in another shot
  of the same place (#025 switch, #036 sill plants, #047 notice and shelves, #143 seats and banner, #149 chair); U1 did
  not list about 13 (nothing at all in #126 and #191; teapot, canopy, bag, bedspread, background building, wedge,
  curtains); 3 validation targets are copies of prompt characters, outside U1's scope by design.
- Other confirmed issues (unverified): #036 HoloCine small white object appearing in Shot1 frame 5 (may be an entering
  object), #120 stick disappearing (same object as the target, different claim), #124 potted plant missing in Shot5
  (Shot1 is very dark), #141 pink shape appearing beside the mouse (may be its tail).
- Reading: the branch is cheap (within the owner's USD 10 per 1,000 videos) and the mechanism works when a listed
  difference is raised (#078); recall is still low because U2 drops most listed differences and U1 misses many
  objects. Next step suggested to the owner: make U2 raise every object listed in one shot and not in another shot of
  the same contract place (U3 then checks each), which uses inventories the run already has. Nothing live changed.

## Round 2: U2 by rule (owner: "改 U2 再跑一轮"; runs 21:24-21:33 Dubai; `run_u_branch_v1.py`, `runs_v1/`, `sheet_runs_v1.md`)

- Change: the round-1 U1 inventories are reused unchanged (only `inventory.json` copied, no new U1 call). U2 is code:
  every inventory object of a shot is checked against the other shots that share a contract place (at most 4; for
  each, what its inventory lists that may be the same object, by detector id or a shared content word in the name,
  or nothing), plus within-shot suspects for a noted change or a gap in the visible frames; at most 15 per video
  (161 suspects in all, no cap reached). U3 v1 (`prompts/u3_verify_v1.txt`, Luna high) checks one object per call
  on its middle visible frame and one frame of each other shot, and names the shots where an inconsistency is seen.
  Detection build and frozen V-V review as in round 1.
- Cost (standard-price estimate, not a bill): USD 0.223529 for U3 and review on 28 videos (0.008 per video); with
  the round-1 U1 (about 0.003 per video) a full branch costs about USD 0.011 per video, about USD 11 per 1,000.
- U3: 34 real, 40 unclear, 87 not real (161). Review on the 34 real (31 units after merging): 5 confirmed, 3 uncertain,
  23 rejected.
- Targets (assistant matching): dev 2 of 13 confirmed (#036 sill plants, #078 TV cabinet); U3 also found #047 notice
  and #055 countertop items (partial), both rejected by the review. Validation 1 of 14 confirmed (#086 duplicate man,
  ledger ge0001); U3 also found the #036 Wan2.2 curtains, rejected by the review.
- The review rejects cross-view "missing" findings when it cannot confirm that the other shot shows the same place
  (basis normal_change / not_expected_to_match, normal causes framing or viewpoint): #047 notice, #036 curtains,
  #055 countertop items, #120 stick. Other confirmed: #055 wall lamp vs pendant lamp (ge0005), #148 wall vent (n1),
  not checked against human judgment.
- Reading: the rule-based U2 fixes the round-1 drop (U3 now sees the listed differences); remaining losses are U1
  coverage (about half of the targets never listed) and the review's conservative rejections. Comparison on the same
  targets: current pipeline dev 0/13, val 1/14; N2 2/13, 2/14 (+USD 0.023 per video); this branch 2/13, 1/14
  (+USD 0.011 per video), 3/13 + 1 partial and 2/14 before review. Development evidence only; nothing live changed.

## Round 3: anchors and a wider U1 (owner: "再迭代一轮看看吧"; runs 21:52-21:58 Dubai; `run_u_branch_v2.py`, `runs_v2/`, `sheet_runs_v2.md`)

- Changes: U1 rerun with `prompts/u1_inventory_v1.txt` (also things lying on or attached to registered or prompt-named
  objects, canopies and building fixtures, edge and far-background objects; reasoning medium). U2 rule as round 2,
  with two frames of the object's shot and two frames of each other shot (at most 3 other shots). U3 v2
  (`prompts/u3_verify_v2.txt`): must name an anchor visible in both shots; a real verdict needs one, and the
  description cites it.
- Cost (standard-price estimate, not a bill): USD 0.346655 for 28 videos, USD 0.0124 per video for the whole branch,
  about USD 12 per 1,000 videos.
- U3: 21 real, 85 unclear, 68 not real (174 suspects). Review (20 units): 10 confirmed, 2 uncertain, 8 rejected.
- Targets (assistant matching): dev 3 of 13 (#036 sill plants, #047 notice sheet, #078 TV cabinet); validation 1 of 14
  (#036 Wan2.2 curtains/blind) plus 1 partial (#107 bed cover: confirmed between Shot7 and Shot5, the target is Shot5
  vs Shot6). Not targets, unchecked: #036 HoloCine narrow window, #055 quilt and lamps, #046 wall plate, #149 seat.
- Comparison (same targets): current pipeline dev 0, val 1; N2 2, 2 (+USD 0.023 per video); night C 2, not run on val;
  branch r1 1 (+1 partial), 0; r2 2, 1; r3 3, 1 (+1 partial) (+USD 0.012 per video). Development evidence only.
- Chosen as the plug-in version for the full first-200 run (owner: C as default, the branch as plug-in).
