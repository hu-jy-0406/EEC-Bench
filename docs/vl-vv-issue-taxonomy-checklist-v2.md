# V-L / V-V issue taxonomy and must-check checklist (protocol v2)

Status: implemented 2026-10-04 as discovery `vl_vv_issue_discovery_v2`, review
`vl_vv_issue_review_v2`, scoring `vl_vv_episode_scoring_v3`; default in
`run_vl_vv_pipeline.py`. Protocol v1 (three disjoint lists) remains available
with `--discovery-protocol v1`. Evidence and validation:
`EECBench/experiments/vl_vv_checklist_v2_20261004/REPORT.md`.
Since 2026-10-06 the default review after this discovery is
`vl_vv_issue_review_v4` (verdicts on the core problem of each label) with
scoring `vl_vv_episode_scoring_v3`; review v2 remains available with
`--review-protocol v2` (`docs/vl-vv-issue-review-v4.md`). The interim
partly-true review v3 was removed. Discovery v3 (`docs/vl-vv-issue-discovery-v3.md`)
keeps this taxonomy and checklist but gives every issue exactly one label: a
discrepancy that is both V-V and V-L becomes two linked issues.

## 1. Why v2

Two problems in the v1 issue-discovery stage, both visible in the first-200 ×
5-model results (1,000 scored tasks, 2,410 reviewed candidates):

1. **Important artifacts are missed.** A visual audit of 23 episodes × 5 models
   (115 videos) found 288 clearly visible problems the evaluator did not
   report, including the owner's examples: Wan2.1-T2V #014 Shot1 vs Shot3
   courtyard background; Wan2.2 #028 the turquoise woman's top, hair and face
   across Shots 2/4/6/8. Per-model V-V within-shot means were 97.3–100 with
   only 45 within-shot candidates in 1,000 tasks, and no required-cut failure
   was ever reported as such although CineTrans produced single uncut takes
   in most audited episodes.
2. **V-L and V-V were forced to be mutually exclusive.** v1 required "each
   physical discrepancy belongs in one list only". 229 V-L rows span several
   shots; many are cross-shot inconsistencies (e.g. #002 Wan2.1: the man's
   shirt and the sofa change between shots despite "Maintain the same man
   and room") that never reached the V-V cross-shot score. The audit found 43
   such already-detected rows that should also carry a V-V label.

The entity ledger was not the bottleneck for the owner's examples: it linked
the #028 turquoise woman across Shots 2/4/6/8 and the #014 courtyard across
all shots. The miss happened in discovery.

## 2. Definitions

Every candidate is tested against **both** questions independently. One
physical discrepancy is **one issue** that may carry a V-L label, a V-V label,
or both. Labels are never dropped because the other label applies.

**V-L (video vs language).** A visible observation contradicts an explicit
requirement in the global prompt, a shot prompt, the contract (entity
descriptions, entity schedule, claims) or the required shot transitions.
Test: can the violated text be quoted literally? Details the text does not
specify are never V-L.

**V-V (video vs video).** A visible observation is incompatible with other
visual evidence in the same generated episode without a visible or
text-supported cause. Test: can two witnesses in the video be cited that
cannot both be true of the same entity, setting or moment? No quote is
needed.

- **V-V within shot**: frames of one shot cannot all belong to one continuous
  take, or an entity is physically incoherent within the shot.
- **V-V cross shot**: shots that show the same character, object, setting,
  style or continuous moment are mutually incompatible, or a boundary does
  not realize its required transition. Sameness may be established by the
  text (same label/name, entity schedule, "same/remains/returns/again") **or**
  by clear visual evidence that the episode intends the same entity/setting.

### Labeling rules

| Situation | Labels |
| --- | --- |
| Described attribute wrong, consistently wrong in every shot | V-L only |
| Undescribed attribute changes between shots of one scene | V-V cross only |
| Described attribute changes between shots (one shot violates the text) | V-L + V-V cross, one issue |
| Text says "same/remains/returns" and the shots differ | V-L (`stated_continuity`, or the specific subcategory if an attribute is described) + V-V cross |
| A scheduled character is visibly a different person in one shot | V-V cross `character_identity`; add V-L only if a described identity attribute or sameness phrase is contradicted |
| Change within one shot that the prompt also forbids ("hold this single view") | V-V within + V-L |
| Required cut not realized / continue broken | V-V cross `transition_realization` + V-L `shot_structure` (quote "ShotA->ShotB: cut") |
| Same failure in several shots | One issue whose scope lists every affected shot |
| Camera angle shows other parts of the same place; plausible shown action; occlusion; story time skip | Not an issue |
| Episode video cut lands a fraction of a second late so only frame 0 shows the previous shot | Timing offset, not an appearance/identity/presence error; report only if clearly meaningful |

Scoring consequence (v3): a dual-labeled issue deducts once in the V-L bucket
and once in its V-V bucket, each with its own reviewed verdict, confidence and
severity. Buckets remain separate scores; there is still no combined score.

## 3. Subcategories

### V-L (`v_l.subcategory`) — kind of requirement violated

| Code | Definition |
| --- | --- |
| `presence_count` | Required entity/setting missing; wrong count; prominent unrequested extra; entity required offscreen is visible; black/unreadable shot. |
| `attribute` | Described identity descriptors and properties: age, gender, species, hair, clothing, accessories, colors, materials, marks, legible text/numbers, object state; includes an attribute shown on the wrong character. |
| `action_state` | Described action, motion, pose, gesture or expression missing, wrong, incomplete, reversed, out of order, wrong start/end state or direction. |
| `interaction` | Wrong actor/object; described holding, touching, using, giving, receiving or contact absent or wrong. |
| `spatial_orientation` | Described positions, left/right, on/in/under, distances, facing or gaze directions. |
| `setting_environment` | Described location type, background elements, time of day, weather, season, lighting, mood. |
| `camera_composition` | Described shot scale, angle, viewpoint, framing, focus, camera movement. |
| `style_rendering` | Described rendering style, animation vs live action, color mode, aspect/letterbox. |
| `stated_continuity` | An explicit sameness/continuity phrase is contradicted and no more specific subcategory fits. |
| `shot_structure` | Shot plan or required transition not realized: missing cut/continue, a shot's content in another interval, a new shot repeating the previous one. |

### V-V within shot (`v_v.scope = within_shot`)

| Code | Definition |
| --- | --- |
| `identity_drift` | A person/animal morphs into a different-looking individual. |
| `appearance_drift` | Clothing, hair, accessories, colors or marks change with no visible action. |
| `object_instability` | An object's type, shape, size, color, count, text or state changes with no action. |
| `presence_instability` | Pop-in/out without entry, exit or occlusion (including vanishing then reappearing); duplication, splitting, fusion into a hybrid. |
| `background_drift` | Background elements/layout change in a way camera motion does not explain. |
| `physical_integrity` | Malformed/melting/fused bodies, hands or faces; extra or missing limbs; interpenetration; impossible deformation or motion; reflection/shadow without a source. |
| `relation_break` | Held object teleports or switches hands; contact, support or relative position changes with no action. |
| `unintended_cut` | Unrequested cut or composition jump inside a shot; for episode videos, a shot change deep inside the interval. |
| `rendering_instability` | Flicker, color/exposure flash (often frame 0), black/blank frames, style switch inside the shot. |

### V-V cross shot (`v_v.scope = cross_shot`)

| Code | Definition |
| --- | --- |
| `character_identity` | Same character's face, age, gender, skin tone or build differs. |
| `character_appearance` | Same character's hair, facial hair, clothing (type, color, pattern, logo, number), accessories, makeup or injuries differ; attributes migrate between characters. |
| `object_identity` | Same prop/object/vehicle/animal differs in type, shape, color, markings, text or size. |
| `setting_background` | A recurring location's architecture, wall/floor colors and materials, doors/windows, furniture, vegetation, signage, set dressing or layout differ. |
| `environment_lighting` | Same continuous scene changes time of day, weather, season, lighting or color grade without a cause. |
| `rendering_style` | Photoreal vs animation, 2D vs 3D or another style differs across shots that should share one style. |
| `instance_count` | Recurring entity duplicated, merged into a hybrid, replaced by another individual (who takes its place or actions), or distinct characters look identical or swap looks. |
| `state_action_continuity` | Pose, position, held objects, object/clothing state or action progress incompatible across a boundary or a return. |
| `spatial_continuity` | Relative positions, left/right arrangement, screen direction or layout flip/rearrange without a cause. |
| `transition_realization` | Required cut not realized (one take runs through the boundary, near-duplicate consecutive shots, dissolve instead of cut, cut far from the boundary) or required continue broken (unintended cut, jump, reset). |

## 4. Worked examples (real cases)

- **#002 Wan2.1** (v1: two V-L rows only, V-V = 100). Shot3 shows a dark
  button-down shirt while Shots 1/2/4 show the described "faded blue-gray
  T-shirt" → one issue, V-L `attribute` + V-V cross `character_appearance`.
  (The v1 description attributed the shirt to Shot4; the frames show Shot3.)
  Shot4's tall rounded armchair vs the low sofa in Shots 1–3 with "the same
  Beige sofa" → V-L `stated_continuity` + V-V cross `object_identity`. The
  room (dark doorway / wood panels / pale wall / dark wood) and the man's face
  and hair volume also differ across shots → V-V cross `setting_background`,
  `character_identity`, each + V-L via "Maintain the same man and room".
- **#014 Wan2.1** (v1: V-V = 100). Shot1 grand stone building with
  balustraded stairs; Shot3 a low beige single-storey building with a bench;
  text "retain the courtyard continuity", "remains in the same wintry
  courtyard" → V-V cross `setting_background` + V-L `stated_continuity`.
  StoryMem on the same episode keeps the same pine trees and facade in Shots
  1/3 → no setting issue (negative control).
- **#028 Wan2.2** (v1: two V-L rows). The turquoise woman's top (plain with
  strap / dark-marked tee / logo tee / patterned tee), hair (wavy brown /
  long dark / curly with blonde streaks) and face differ across Shots 2/4/6/8
  → V-V cross `character_identity` and `character_appearance` (V-L only for
  described attributes actually contradicted). The robe woman's "pale
  blonde-gray hair pulled back" is loose and long in Shot7 → V-L `attribute` +
  V-V cross `character_appearance`.
- **#028 CineTrans**. All eight intervals are one continuous take of one
  blended woman; none of the seven required cuts happens and the robe and
  turquoise women merge → V-V cross `transition_realization` + V-L
  `shot_structure`; V-V cross `instance_count` + V-L `presence_count`.
- **#014 HoloCine**. Frame 0 of Shots 2–4 still shows the previous shot (cut
  ~0.25–1 s late) → timing offset; not an identity/presence error.
- **#068 HoloCine**. One static elevator-wall take for all eight shots;
  characters vanish for several keyframes and reappear; in Shot8 the woman's
  clothes and pose continue on a man → `transition_realization`,
  `presence_instability`, `identity_drift`.

## 5. Must-check checklist

The checklist is a floor, not a ceiling: after completing every item the
evaluator performs an open-ended sweep (O1) and must report any other obvious
or meaningful problem. Each item is recorded once in `checklist_audit`
(`checked` + terse note, or `not_applicable` + reason); each issue lists the
items that found it (`O1` for open-ended findings).

Source column: **D** = type already detected by v1 (census, section 6.1);
**M** = type found missed in the audit (section 6.2).

| Item | Check | Main subcategories | Source |
| --- | --- | --- | --- |
| S1 | Required content per shot: scheduled entities, counts, no prominent extras, offscreen requirements, not black | presence_count, shot_structure | D, M |
| S2 | Described attributes, bound to the right character | attribute | D, M (attribute bleed) |
| S3 | Actions/interactions: complete, order, direction, start/end states, right actor and object | action_state, interaction | D, M |
| S4 | Positions, facing/gaze, entries/exits, shot scale, angle, viewpoint, camera movement; subject not cropped | spatial_orientation, camera_composition | D, M |
| S5 | Setting, environment, lighting, color mode, rendering style | setting_environment, style_rendering | D |
| S6 | Within-shot stability of identity, appearance, objects, background, presence, physical integrity, relations | identity_drift … relation_break | D (few), M (many) |
| S7 | One continuous take: no unrequested cut, jump, flash (incl. frame 0), black frame, style switch | unintended_cut, rendering_instability | M |
| C1 | Every recurring character incl. secondary/back-view: identity and appearance across all its shots | character_identity, character_appearance | D, M (#028, #002) |
| C2 | Recurring props/vehicles/animals/furniture | object_identity | D, M |
| C3 | Recurring settings: architecture, colors, materials, doors/windows, furniture, vegetation, set dressing, layout | setting_background | D, M (#014) |
| C4 | Lighting/time/weather/color grade and rendering style across shots | environment_lighting, rendering_style | D, M |
| C5 | Instances distinct and singular: no duplicate, merge, replacement, look swap, missing | instance_count | D, M |
| C6 | Boundary and return continuity: poses, positions, held objects, states, screen direction, action progress | state_action_continuity, spatial_continuity | D, M |
| C7 | Transition realization per required cut/continue | transition_realization, shot_structure | M (never detected as such) |
| C8 | Every "same/remains/returns/still/again/continue/unchanged/keeps/familiar/established" phrase | stated_continuity + matching V-V | D (as V-L only), M |
| O1 | Open-ended sweep for anything else | any | — |

**Continuity ledger.** Before writing cross-shot issues the evaluator records
one subject per recurring character and place (and any recurring object or
style it compared): per shot, the inspected frame and a terse signature of
decisive features, then `consistent / inconsistent / uncertain`; an
inconsistent subject must link its issue IDs. The runner computes
`required_continuity_subjects` = prompt-bound characters and places scheduled
in ≥2 shots and rejects a ledger that omits one of them or one of their
scheduled shots (validation-repair loop applies). This turns C1/C3 into an
explicit all-shots comparison instead of an implicit one-pair glance.

**Shot scan.** For S6/S7 the evaluator writes exactly one `shot_scan` entry
per shot: frames 0–5 compared in order (faces, hair, clothing, who is
present, objects, background, framing, brightness/style), every change and
whether action or camera motion explains it, and the IDs of issues in that
shot. The runner rejects a missing or duplicated shot and links to issues
whose scope does not include the shot. This was added after the first live
validation rounds showed that within-shot checks were still skipped.

**Shot transitions.** Discovery and review receive `shot_transitions`
(required `cut`/`continue` per boundary) and `shot_sources` (independent clip
vs interval of one episode video, with keyframe timestamps). Source order: an
explicit `case/shot_transitions.json`; else the source shot map's per-shot
`cut` flags (the flag of shot k+1 governs boundary k→k+1), reached through
`benchmark_metadata.json`; else the default "every contract shot boundary is
a cut". All 1,000 first-200 shot-map flags are `true`; `continue` is
supported for future data.

## 6. Evidence

### 6.1 Already detected (coverage of the checklist)

All 2,410 v1 candidates were mapped to v2 subcategories by deterministic
keyword rules (`analysis/map_detected_issues.py`; approximate). Every mapped
class is covered by a checklist item:

| v2 class | candidates (confirmed) | item |
| --- | --- | --- |
| V-L attribute | 751 (684) | S2 |
| V-L presence_count | 339 (313) | S1 |
| V-L interaction | 262 (235) | S3 |
| V-L action_state | 181 (156) | S3 |
| V-L spatial_orientation | 173 (155) | S4 |
| V-L camera_composition | 88 (83) | S4 |
| V-L setting_environment | 53 (47) | S5 |
| V-L shot_structure ("still shows previous content") | 41 (41) | S1, C7 |
| V-L style_rendering | 31 (30) | S5 |
| Within appearance/identity/object/presence/relation/rendering/cut | 45 (39) | S6, S7 |
| Cross character_appearance | 201 (184) | C1 |
| Cross object_identity | 81 (68) | C2 |
| Cross character_identity | 61 (60) | C1 |
| Cross setting_background | 59 (45) | C3 |
| Cross rendering_style | 30 (27) | C4 |
| Cross spatial/instance/lighting/state | 14 (11) | C4–C6 |

### 6.2 Missed (audit)

Six independent visual audits of 20 random episodes stratified by shot count
plus #002/#014/#028, all five models (115 videos), compared contact sheets and
full-resolution keyframes with the v1 findings. 288 missed issues (202 high
confidence; 71 major/critical): V-L codes 266 mentions, within 75, cross 208.
93 missed issues warrant both labels. Most frequent: cross character
appearance 53, transition realization 49 (24 CineTrans + 24 HoloCine; 22 are
timing offsets), cross character identity 47, required entity missing 54,
action 51. Patterns: (1) cuts never checked; (2) within-shot checks almost
never fire; (3) only one character / one shot pair compared; (4) attribute
bleed, swaps and merges between characters; (5) a failure flagged in one shot
but not in the others; (6) first-frame flashes. These are agent audits at
keyframe resolution, not human ground truth; spot checks of #002, #014,
#028, #068, #069 and #180 confirmed the cited high-impact findings.

## 7. Implementation

| Stage | v2 files | Validation |
| --- | --- | --- |
| Discovery | `prompts/vl_vv_issue_discovery_v2.txt`, `schemas/vl-vv-issue-discovery-v2.schema.json` | ≥1 label per issue; subcategory/scope pairing; within = one shot, cross = ≥2 witnessed shots; V-L quote required; entity IDs required except setting/environment/style/camera/transition labels; all 16 checklist items exactly once, cited items not `not_applicable`, C7 required for multi-shot; one `shot_scan` entry per shot with in-scope issue links; a `transition_realization` issue must also carry V-L `shot_structure`; ledger covers every required subject and scheduled shot; inconsistent subjects link issues |
| Review | `prompts/vl_vv_issue_review_v2.txt`, `schemas/vl-vv-issue-review-v2.schema.json` | One review per issue, one verdict+confidence+assessment per non-null label, none for absent labels; within-shot reviews cite only their shot; all-refutes evidence normalizes confirmed → rejected (existing rule, per label) |
| Scoring | `prompts/vl_vv_episode_scoring_v3.txt`, `schemas/vl-vv-episode-scoring-v3.schema.json` | One assessment per (issue, label); penalty rubric v2 weights, confidence factors and product rule unchanged; duplicates only to earlier issues in the same bucket, never self |

Runners select protocol automatically: `run_vl_vv_issue_discovery.py
--protocol v2` (default); review and scoring follow the input file's
protocol. Output shape of scores/counts is unchanged; v3 adds `label_counts`.
The existing validation-repair loop applies to all new gates.

## 8. Limitations

- Six keyframes per shot still miss short events between samples; boundary
  frames are 0.25 s apart for episode videos and file boundaries for clips.
- Live validation covers 14 frozen cases (three rounds; see the report): all
  owner examples caught, 17/41 audit-reported v1 misses recovered in one run,
  within-shot defects (3/13) and face-identity drift remain weakest, and
  repeated Luna/low runs vary. The 288-issue audit is agent-based, not
  human-calibrated.
- More output (audit + ledger) costs more tokens; labels may also increase
  false positives, which the independent review must catch.
- v1 and v2 scores are not comparable: v2 deliberately counts dual-labeled
  issues in both dimensions and covers more failure types.
