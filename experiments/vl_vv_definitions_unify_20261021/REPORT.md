# V-L vs V-V definitions unified; V-V permissibility wording; image labels enforced (2026-10-21)

## Owner clarification

- **V-L** issue: the generated video conflicts with the prompt (text: oven
  handle on the right; video: on the left → V-L, spatial).
- **V-V** issue: a visual inconsistency within or across shots. The prompt
  decides whether a visual change is permissible: a change that does not
  conflict with the prompt is not a V-V issue.
- "Does not conflict with" was meant for V-V; the 2026-10-20 change applied it
  to the V-L rule ("a shot that satisfies the words does not violate them").
  Wording meant for V-V must not reach V-L.
- Image labels on for all relevant detection and evaluation runs.

## Changes (in place, current default chain)

Pre-change copies: `source_before/`.

1. **V-L reverted** to the pre-2026-10-20 wording ("satisfies") in
   `prompts/vl_vv_branch_definitions_v1.txt` (rule sentence + boundary-table
   row), `prompts/vl_vv_issue_review_v6_vl.txt` (two sentences; now
   byte-identical to `../vl_vv_no_conflict_wording_20261020/source_before/`)
   and the config documentation text. The definitions file is byte-identical
   to the "satisfies" arm of the 2026-10-21 #032 detection check (0/3
   rubber-stamped). The shared definitions already state the owner's
   distinction: V-L = "a visible observation contradicts an explicit
   requirement of the text"; V-V = "incompatible with other visual evidence
   … without a visible or text-supported cause", and the boundary table makes
   an undescribed attribute changing between shots a V-V report.
2. **V-V wording added** to the V-V detection prompt (section 1) and the V-V
   review prompt (section 1) only:

   > The prompt decides whether a visual change is permissible. A change that
   > does not conflict with the prompt, because the prompt calls for it or
   > allows it (…), is normal and not a V-V issue. A change of the same
   > entity, place or moment that neither the prompt nor the frames explain
   > conflicts with the continuity the prompt sets up and is a V-V issue, even
   > when the prompt does not describe the attribute that changed.

   The last sentence is the assistant's clarification so that "does not
   conflict" is not read as "the prompt is silent about it" (that reading
   would drop changes of undescribed attributes, e.g. #028's clothing).
   Rendered prompts: V-L detection and V-L review contain "does not conflict
   with" 0 times; V-V detection and review once each.
3. **Image labels enforced.** `run_wedetect_shot_entities.image_labels()` now
   raises when an API call attaches an image without `shot_id`/`frame_id`
   (no silent unlabeled fallback; all VL/VV and prompt-alignment callers
   supply both). `run_vl_vv_pipeline.py` (and so the batch controller, which
   runs it per case) refuses `EECBENCH_IMAGE_LABELS=off` unless
   `--allow-unlabeled-images` is passed (recorded in the plan). Codex CLI
   backend unchanged (cannot interleave text); every VL/VV stage requires the
   API backend.

Tests: new `test_execute_refuses_unlabeled_images_without_the_historical_flag`;
the label test now expects an error for missing IDs. VL/VV, label,
clustering, prompt-binding and prompt-alignment suites: 180 passed, 1 failed
(`test_gs_prompt_alignment … new_only_branch`, pre-existing on 2026-10-20).

## V-V check: with vs without the new paragraph (`vv_check.py`, `analyze_vv.py`)

V-V detection only, 4 videos × 2 runs × 2 arms, frozen registries, image labels
on; arm "without" = the V-V detection prompt before this change (rendered
prompts differ only by the paragraph). API only on existing allocation 291609
(node auh7-1b-gpu-198, load ≈8/128; its own steps running; CPU-light overlap at
low priority).

| | Without | With |
| --- | --- | --- |
| Issues (8 runs) | 12 | 16 |
| Changes normal / abnormal / uncertain | 56 / 13 / 1 | 51 / 22 / 1 |
| Repair rounds | 2 | 5 |
| #002 Shot3 shirt (V-V) | 2/2 | 2/2 |
| #002 Shot4 sofa | 2/2 | 2/2 |
| #002 room background/door layout | 1/2 | 2/2 |
| #014 Wan2.1 coat/neckwear | 2/2 | 2/2 |
| #028 Shot7 chair | 2/2 | 2/2 |
| #028 Shot8 woman's face | 2/2 | 1/2 |
| #028 Shot8 top pattern | 1/2 (+1 bundled in the face issue) | 1/2 |
| #014 StoryMem (control) issues | 0, 0 | 2, 1 (within-shot) |

- No loss of known V-V problems; the paragraph makes V-V somewhat more willing
  to flag. The control's new findings are debatable (assistant check of the
  frames): Shot4 frame 0 → 1 the man straightens up and the tree trunk shifts
  from mid-frame to the right (fast reframe during the action or a real jump);
  Shot2 frames 2–4 small stance shifts (likely a false positive). Reviews
  would filter some; not measured here.
- #014 Wan2.1 courtyard (reference artifact A1) was found in neither arm, as
  before.
- Cost: 23 calls; 2,289,874 input tokens (1,452,939 cached, 836,935 uncached)
  and 111,143 output tokens, USD 0.154 (GPT-6 Luna standard API estimate; not
  a bill). Without arm USD 0.070, with arm USD 0.084.

## Contract entity coverage (for the owner's question; `contract_mentions.py`)

Keyword count over the first-200 contracts (approximate):

- 95/200 contracts name at least one worn or carried item only inside a
  character description (180 mentions; most often tie 37, glasses 27,
  earring 24, cap 17, necklace 15, hat 13, scarf 12).
- 17 items of the same kinds already have their own entity entry, so the
  compiler is inconsistent about this granularity.
- Garments add 415 mentions in 155/200 contracts.
- Contracts have 16.3 entities on average (max 36).

The comparison and recommendation are in the reply to the owner; nothing was
changed in the contracts.
