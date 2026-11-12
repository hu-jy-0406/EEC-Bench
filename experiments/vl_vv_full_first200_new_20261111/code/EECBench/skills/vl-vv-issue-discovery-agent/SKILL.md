---
name: vl-vv-issue-discovery-agent
description: Propose evidence-grounded video-language and video-video inconsistency candidates from a frozen multi-shot detection case, before independent review and scoring.
---

# VL/VV issue-discovery agent

Use this skill for the **issue-discovery stage after detection and entity registry construction**. It is separate from `vl-vv-detector-agent`: do not detect, cluster, rename, or rematch entities here. This stage proposes candidates for the later issue-review agent; it does not confirm them or score the episode.

## Runtime entrypoint and source of instructions

- Run `EECBench/scripts/run_vl_vv_issue_discovery.py` on a completed, frozen detection case. `--protocol v2` (default) uses the checklist and non-exclusive V-L/V-V labels; `--protocol v1` reproduces the historical three-list protocol.
- The instructions actually sent to Luna are `EECBench/prompts/vl_vv_issue_discovery_v2.txt` (v2) or `EECBench/prompts/vl_vv_issue_discovery_v1.txt` (v1). This skill is the workflow and taxonomy reference; it is **not** substituted for the runtime prompt.
- Keep the definitions, subcategories and checklist in this skill, the runtime prompt and `EECBench/docs/vl-vv-issue-taxonomy-checklist-v2.md` synchronized when any of them changes.
- JSON contracts: `EECBench/schemas/vl-vv-issue-discovery-v2.schema.json` (v2) and `...-v1.schema.json` (v1). Review and scoring follow the discovery protocol automatically.

## Two non-exclusive labels (v2)

Test every candidate against both questions and attach every label that passes; one physical discrepancy is one issue.

- **V-L**: a visible observation contradicts an explicit requirement of the global prompt, a shot prompt, the contract or the required shot transitions. A literal quote is required; unspecified details are never V-L.
- **V-V**: a visible observation is incompatible with other visual evidence of the same episode without a shown or text-supported cause. `within_shot`: frames of one shot cannot form one continuous take, or an entity is physically incoherent. `cross_shot`: shots showing the same character, object, setting, style or continuous moment are incompatible, or a boundary fails its required transition. Sameness may come from text or from clear visual evidence. No quote is needed.

Examples: a described T-shirt that becomes a button-down shirt in one of four shots is V-L + V-V cross; a hat that is consistently the wrong type is V-L only; an undescribed jacket that changes color between shots of one scene is V-V only.

## Must-check checklist (a floor, not a ceiling)

Per shot: S1 required content and counts; S2 described attributes, on the right character; S3 actions and interactions (order, direction, start/end states, actor/object); S4 positions, gaze, entries/exits, shot scale, angle, viewpoint, camera movement; S5 setting, environment, style; S6 within-shot stability (identity, appearance, objects, background, presence, physical integrity, relations); S7 one continuous take (no unrequested cut, flash incl. frame 0, black frame, style switch).

Across shots (all shots that share a subject, including non-adjacent returns): C1 every recurring character incl. secondary/back-view figures; C2 recurring objects; C3 recurring settings; C4 lighting/time/weather/style; C5 instances (no duplicate, merge, replacement, look swap); C6 boundary and return continuity; C7 transition realization (required cut → clear shot change; required continue → no unintended cut); C8 every stated continuity phrase.

O1: after the checklist, sweep every frame again and report **any other obvious or meaningful problem**, even if no item names it.

Record every item once in `checklist_audit`, one `shot_scan` entry per shot (frames 0–5 compared, every within-shot change noted), a `continuity_ledger` subject for every recurring character and place (prompt-bound subjects scheduled in ≥2 shots are mandatory, with one observation per scheduled shot), and link inconsistent subjects to issues.

## Evidence and output constraints

- Treat the detector ledger and DINO values as clues, not final judgments. A detector miss alone is not evidence that an entity is absent; a ledger link is not proof of sameness.
- Do not invent entities, identity links, frames, boxes, motion, geometry, or observations. Cite original `shot_id` and `frame_id` witnesses.
- Within-shot labels keep one scope shot; cross-shot labels need witnesses from at least two shots. A failure that recurs in several shots is one issue whose scope lists every affected shot.
- Do not treat camera reframing explained by viewpoint, occlusion, offscreen periods, plausible shown actions, story time skips or detector errors alone as inconsistencies. For episode-level videos, a cut landing a fraction of a second late (only frame 0 shows the previous shot) is a timing offset, not an appearance error.
- Return JSON matching the schema. Do not review candidates, edit upstream data, or calculate episode scores.

## Sampling limitation

The current input contains six keyframes per shot. A short-lived inconsistency between sampled frames may therefore be missed; do not claim that the checklist eliminates this limitation.
