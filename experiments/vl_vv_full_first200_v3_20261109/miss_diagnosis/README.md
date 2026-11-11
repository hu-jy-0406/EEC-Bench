# Missed-issue diagnosis for unspecified entities (2026-11-09/10)

Times are Dubai time. Owner question (2026-11-09 evening): many V-V problems that involve unspecified entities seem
to be missed; should we tune the checklist, change the entity definition, or use a stronger model? Agreed first step:
find where misses happen before spending API money.

## 1. Teaser example #004 Wan2.1 (window and plants)

`004_wan21_shot4_6.png`, `004_wan21_plants_ledger.png` (`contact_sheet.py`, `draw_ledger_boxes.py`). Shot5's prompt
names "hanging pots and green leaves beyond the glass" (contract pb0011, pb0012); the windowsill pots are ledger ge0001
and ge0002 (Shot5 only). This rerun confirmed the window/plant inconsistency (V4+V10, setting_background) with only
specified subjects (window, curtain, grille, prompt plants); the first run and the stopped v2 run had missed it. The owner
agreed it is a specified issue.

## 2. Blind audit of 20 videos (Claude subagents; assistant judgment, not human annotation)

- Sample: 4 random videos per model from the 1,000 (seed 20261109), 100 shots (`prepare_audit.py` ->
  `audit20/<task>/` with keyframe sheets, prompt, contract entities, pipeline results).
- Per video, a subagent first listed visible consistency problems of things the prompt does not describe (blind:
  `blind_findings.json`, written before opening the pipeline results), separating "primary" (unprompted objects, props,
  furniture, plants, vehicles, animals, people: entities under the current rules) from "secondary" (walls/floors,
  worn items, body parts). Then it traced each primary finding through the ledger and the V-V candidates and verdicts
  (`trace.json`). Batches: four auditors started 23:57, stopped at 00:04 (owner asked for speed; 4 videos done, 3
  blind-only) and the rest re-split over nine auditors; files of finished videos kept. Done about 00:28.
- Aggregate (`aggregate_audit.py` -> `audit20_summary.json`):
  - Primary findings: 19 in 10 of 20 videos (2 clear, 17 likely; 14 cross-shot, 5 within-shot).
  - Pipeline outcome: 13 no V-V candidate, 1 rejected, 5 confirmed but with specified subjects only (some arguably
    specified anyway: an extra instance of the contract drone, a woman who may be the contract character). None is
    counted as involving an unspecified entity.
  - Ledger: 11 of 19 objects are not in the ledger at all, 4 in some of the relevant shots, 1 split into one entity
    per shot (mower -> "Garden cart" / "Green balloon"), 3 the same entity in all relevant shots (one of them, #078
    Wan2.2 TV cabinet, white with drawers in Shot2 vs dark stand in Shot5, clear, got no candidate).
  - Pipeline in these 20 videos: 72 confirmed V-V issues, 1 with an unspecified subject (real, but its unspecified
    subjects are lamps carried over from the candidate, not what changes).
  - Secondary findings: 58 (40 no candidate, 17 confirmed with specified subjects, 1 rejected).
- Reading: the auditors see about one unprompted-object problem per video, mostly subtle ("likely"), while the
  pipeline reports almost none. The largest loss is that small background objects never enter the ledger (light
  switch, notice sheet, canopy, side table, towel, baton), and the V-V agent rarely reports things outside the ledger;
  even ledger objects changing clearly across shots can be missed (#078). Needs human verification before any claim.
- Usage: Claude subagents only, no OpenAI API calls; the nine finishing auditors reported 1,577,759 tokens (the four
  stopped ones not reported); cost unavailable (no billing data).

## 3. Frontend loss point: unseen by WeDetect or dropped in clustering? (2026-11-10 00:35)

Owner question: are the 11 audit objects missing from the ledger unseen by WeDetect-Anything, or detected but not
registered by shot clustering? `frontend_check.py` draws every raw WeDetect detection on the cited frames, colored by
the clustering outcome (`frontend_check/*.png`, `frontend_check/status.json`); each image was inspected.

- Clustering keeps almost everything: of 160 raw detections on these frames, 158 went into entities, 2 were rejected.
- 9 of 11 objects have no WeDetect box at all: light switch (#025), sill plants and garage canopy (#036), notice sheet
  and rear-wall banners/shelves (#047; one "picture" box there was put into a person entity), baton (#120), side table
  and towel on the chair (#126), small cloth in the paw (#127). Small, thin or flat background things.
- 1 was detected but rejected by clustering: the second drone (#036 Shot1 f5, "车辆 0.45").
- 1 is part of a larger detected entity: the changing screen images (#096 HoloCine) sit inside the TV-wall box.
- The vocabulary is not the limit: it holds 电灯开关, 毛巾, 桌子/茶几, 海报, 横幅/旗帜, 植物, 布, 架子 (no baton or canopy).
  The detector output requires class match score >= 0.4 (objectness 0.1, top_k 100; `run.json` postprocessing), so
  these objects either scored below that or were not proposed. Not yet tested.

## 4. Lower WeDetect thresholds on the same frames (2026-11-10 00:43, owner: "Yes, test it")

`wedetect_lowthr.py` (same model and weights, CPU on allocation 356507, 4 threads, about 2 min): one forward pass per
frame (27 frames), production proposals (objectness > 0.1, top 100) plus extended ones (objectness > 0.05, top 300),
best class and match score for every proposal (`wedetect_lowthr/*.png`, `frames.json`; each image inspected).

- Recovered by a match threshold of 0.3 (objectness unchanged): the light switch (#025, 0.33/0.39, labeled 出口) and
  the side table (#126, 桌子 0.30 in one of two frames; 凳子 0.18 in the other).
- Recovered only with objectness 0.05 and match 0.2: the baton (#120, 手 0.31 / 毛笔 0.23, objectness 0.08-0.09).
- Proposed but far below any usable match: the towel on the chair (#126, best class 0.03).
- No separate proposal at all: sill plants and canopy (#036), notice sheet and banners/shelves (#047), cloth in the
  paw (#127).
- Cost in boxes (27 frames, 125 production boxes): match >= 0.3 adds 18% (objectness 0.1) or 46% (objectness 0.05);
  match >= 0.2 adds 30% / 74%. Most added boxes are scene or part boxes (wall, room type, hand, face).
- Reading: thresholds recover 2-3 of the 9 unseen objects; most small background things are never proposed as
  separate objects, so the detector settings alone cannot close this gap.

## 5. Human review page for the 19 findings (2026-11-10, owner: "给我做一个带图的网页")

- Page: https://claude.ai/artifact/Ws5aPmQegonTE3KLfrCuh7 (private until the owner shares it). Per finding: the cited
  keyframes (unchanged copies in `human_review/img/`), approximate boxes (`human_review/markers.json`: placed by Claude
  after looking at each frame, solid = the object, dashed = the corresponding spot; not detector output), Chinese
  translation and English original, the involved shots' prompt text, all six keyframes of each involved shot, and the
  pipeline outcome (rerun v3 and the 2026-11-10 night arms) in a collapsed section.
- Two questions per finding: is the problem real (yes / no / can't tell), and does the prompt name the object
  (unspecified / specified / unsure), plus a note. Answers are saved in the artifact database, collection `reviews`, one
  shared document per finding (`reviews/<num>-<id>`: finding, real, prompt, note, updated); read them with ArtifactData
  `list`. If storage needs the viewer's permission the page shows a "授权保存" button; answers given before that stay in
  the browser and are uploaded once granted. The page's "复制结果" button gives the same as text.
- Version 1 (published about 10:52 Dubai) drew no cards: `trace.json` stores `ledger_entity` as a string for some findings
  and the page called `.map` on it, so the script stopped and the status stayed at "正在连接共享存储". Version 2 normalizes
  the field, drops the `user` capability (per-viewer documents), adds step-by-step status with timeouts and a global
  error message.
- Build: `human_review/build_review_page.py` (template `page_template.html`). Checked: Node.js syntax check (conda
  package cache `nodejs-22.22.3`) and a jsdom smoke test with a stubbed store (scratchpad, not kept): 19 cards, 63
  cited frames, 81 boxes, lightbox, filter, saving, and the granted / needs-permission / denied / outside-viewer /
  no-store cases, no script errors; database write, list and delete with a probe document (removed). Not checked: the
  real claude.ai viewer and its permission dialog.

## 6. Owner's verdicts on the 19 findings (2026-11-10, review page)

Read with ArtifactData `list` (`human_review/verdicts_raw/`), joined in `human_review/summarize_verdicts.py` ->
`human_review/verdicts_summary.json` (owner notes kept verbatim there). Answers given 11:10-11:38 Dubai.

- Real problem: 16 yes, 1 no (036-A4 mower), 2 can't tell without the full video (096-A1 screens, 127-A1 cloth). The
  owner also wants the full video for 036-A1 (second drone; leaning real). The three videos were added to the page
  (version 3); verdicts may change after watching.
- Prompt names the object: of the 16 real, 14 unspecified, 2 specified (013-A1 woman, 013-A3 handbag). The owner asks
  to merge 126-A3 (towel) into 126-A2 (side table): 13 distinct real problems with unprompted objects.
- Pipeline (rerun v3) on these 14: 9 objects never entered the ledger, 3 are in some of the relevant shots, 2 in all;
  V-V gave no candidate for 11, rejected 1 (126-A1), confirmed 2 under specified subjects only (036-A1, 055-A1). None
  is counted as unspecified. Night arms: C confirms 036-A2 and 055-A1 with unspecified subjects, E2 raises 078-A1 as
  uncertain.
- Labeling notes from the owner: 013-A1 = V-L (hat missing) + V-V (appearance change), both specified; 013-A2 = V-L
  (lamp not rendered as required) + V-V of the unspecified green object; 126-A1 and 126-A2 are within-shot V-V (the
  audit filed 126-A2 as cross-shot); 025-A1/A2 count if Shot4 requires the Shot2 view with no movement in between,
  which the prompt supports (Shot4: "The alternate hallway view returns ... Keep the exchange restrained and the
  surrounding hallway still"; Shot3: "Their bodies remain close together and largely still").
- Not resolved, noted only: 126-A1's lounger is linked in the ledger to contract entity pb0012 "Low pale chair" (named
  in Shot2's text) while the owner judged it unspecified; 025-A2 mixes contract entities (framed picture [7], arched
  display [5]) with unnamed ones (teapot, blue ornament).
- Reading: 16 of 19 audit findings are real, so in these 20 videos the pipeline misses real problems of unprompted
  objects; their low share in the pipeline output is not evidence that they are rare. The audit is not exhaustive:
  this measures how often audit findings are real, not the pipeline's recall over all problems.

Second read (answers changed 11:48-11:52 Dubai, after the owner watched the three videos; `human_review/verdicts_raw_2nd`
-> `verdicts_summary.json`; the first read stays in `verdicts_summary_first_read.json`):

- 036-A1 (second drone): the full video shows the drone entering the view, so it is fine in the video; from keyframes
  alone flagging it is understandable. Owner: keep it as a special case, do not change the pipeline for it. The button
  was left at "real"; counted here as not real (`INTERPRET` in the script).
- 096-A1 (TV screens): not real, specified. Same situation: the screen content change is reasonable in the video and
  only looks like a jump in the keyframes. Owner: special case, no pipeline change; ideally the model would know that
  screen content switching abruptly is common sense and not report it.
- 127-A1 (cloth in the paw): real, an appearance inconsistency of the hand. Question 2 unanswered; counted as specified
  (the paw belongs to contract character [0] White shaggy creature).
- Count: 16 real, 3 not real. Real and unspecified: 13 (12 distinct after the 126-A2/A3 merge); real and specified: 3.
  On the 13, the pipeline counted none as unspecified: no V-V candidate 11, rejected 1, confirmed under specified
  subjects 1; 8 objects never entered the ledger. Both video-only false alarms (036-A1, 096-A1) were problems the
  pipeline had itself confirmed under specified subjects.
