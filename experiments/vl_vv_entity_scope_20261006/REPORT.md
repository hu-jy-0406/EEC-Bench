# Episode-wide entity descriptions (discovery v4, review v5) — 2026-10-06

## Request

The user asked for one rule to be added and tested on the previous failure
cases: "a contract or global description of an entity applies in every shot
where that entity appears, unless that shot's own text describes it
differently."

## Implementation

- **Rule text.** Discovery v4 and review v5 are discovery v3 and review v4
  with the rule inserted as one paragraph. Spec:
  `docs/vl-vv-entity-description-scope.md`.
- **Assistant clarification.** "Differently" means a different value for the
  same attribute or a stated change; a shorter or less specific mention does
  not override the description.
- **Review v5 rejection clause.** It also says: never reject a V-L label
  because the violating shot's own text only names the entity, or because
  another shot satisfies the description.
- **Default chain:** discovery v4 → review v5 → scoring v3. Older versions
  stay selectable.
- **Tests:** 78 VL/VV tests pass. One test checks that each new prompt differs
  from its predecessor only by the inserted paragraph.
- **Snapshot:** `source_before/`.

## Runs

`run_jobs.py` produced 62 jobs, all of which succeeded, on existing
allocation 236651 / node270 with no GPU.

- **Review v5 on identical candidate issues** (`runs/review/`). These issues
  were reviewed with review v4 in `vl_vv_core_review_20261006`:
  - the 24 clip runs;
  - two more repeats on the four target runs;
  - the six fresh discovery-v2 runs;
  - the twelve discovery-v3 (split) runs.
- **Fresh discovery v4 + review v5** (`runs/pipeline/`): the four videos
  (#002, #014, #069 Wan2.1 and #028 Wan2.2) × 3 runs.

**Cost:** 143 calls; 2,555,733 uncached input, 1,684,244 cached input and
198,013 output tokens. That is USD 0.371 at the GPT-6 Luna standard API
estimate, not a billed amount.

## 1. Previous failure cases: the same candidate issues, review v4 → review v5

There were 33 V-L labels (paired with a V-V report of the same discrepancy)
that review v4 had rejected. The causes are my earlier classification in
`vl_vv_core_review_20261006/vl_rejection_reasons.json`.

| Cause of the earlier rejection | Labels | Confirmed by review v5 |
| --- | --- | --- |
| Requirement read shot by shot ("this shot's text does not restate it", "another shot satisfies it") | 12 | 9 |
| The V-L claim is not a text requirement (gender, exact pattern) | 12 | 6 |
| Visual judgment (viewpoint, colour shade, "still angular") | 9 | 4 |

- **Shot-by-shot rejections (main target).** Nine of 12 are now confirmed by
  applying the contract description to the later shot. Examples:
  - #069: the short figure's dark trousers in Shot4 versus "brownish
    trousers";
  - #069: the long-coat adult's olive coat in Shot4 versus "gray-brown coat";
  - #069: Shot3's slim rifle versus the "large ... bulky textured" firearm;
  - #002: Shot3's collared shirt versus the man's "faded blue-gray T-shirt".
  The three still rejected are rejected on the merits. "Red-and-dark full
  suit" allows blue-purple, and no text says the top is plain.
- **"Not a text requirement" claims now confirmed (6):**
  - **Legitimate (2):** the issue also cites the short figure's trousers, a
    real contract violation.
  - **Partly right (3):** the gun part is a real violation, but the reviewer
    also counts the jacket's stripes against Shot1's diamond pattern.
  - **Over-confirmed (1):** jacket pattern only.
  In these the reviewer treats the earlier shot's depiction as the
  requirement. The contract only says "patterned jacket", which stripes
  satisfy.

Across all paired V-L labels on identical issues:

| Set | Review v4 confirmed | Review v5 confirmed |
| --- | --- | --- |
| Dual-labeled issues (18 runs, 54 labels) | 31 | 38 |
| Split pairs (12 runs, 25 labels) | 15 | 19 |

A few labels also moved the other way (dual: 3 confirmed → rejected, 2 →
uncertain; split: 3 confirmed → rejected), which is consistent with
run-to-run variance.

### Target labels, three reviews each

| V-L label | Old review (v2) | Review v4 | Review v5 |
| --- | --- | --- | --- |
| E1 (#014 scarf hides required neckline) | 2/3 | 3/3 | 2/3 |
| E2 (#069 short figure) | 1/3 | 1/3 | 2/3 |
| E3 (#069 long-coat adult) | 2/3 | 2/3 | 3/3 |
| E5 (#069 gun) | 2/3 | 2/3 | 3/3 |

E1's one rejection judged the neckline "hidden, so not shown to be violated",
an unrelated visual call.

### Regression check (24 clip runs, identical candidates)

| | Old review | Old review, repeat | Review v4 | Review v5 |
| --- | --- | --- | --- | --- |
| Labels confirmed / 128 | 91 | 98 | 93 | 94 |
| V-L labels confirmed | 42 | 47 | 42 | 45 |
| Verified-artifact labels counting against the score / 92 | 76 | 78 | 69 | 78 |
| Control labels counting against the score / 6 | 0 | 2 | 1 | 0 |
| Uncertain | 3 | 1 | 4 | 2 |

## 2. Fresh discovery v4 + review v5

### Verified artifacts

Matched by hand against each video's artifact list; artifact-runs over 3 runs
per video.

| Video | Discovery v2 + review v4 (dual) | Discovery v3 + review v4 (split) | Discovery v4 + review v5 |
| --- | --- | --- | --- |
| #002 Wan2.1 | 10 / 12 | 7 / 12 | 7 / 12 |
| #014 Wan2.1 | 8 / 15 | 9 / 15 | 9 / 15 |
| #028 Wan2.2 | 9 / 15 | 4 / 15 | 8 / 15 |
| #069 Wan2.1 | 8 / 18 | 12 / 18 | 12 / 18 |
| **Found** | **35 / 60** | **32 / 60** | **36 / 60** |
| **Confirmed** | **34 / 60** | **30 / 60** | **35 / 60** |

### The target problems' V-L halves

- **P2, short figure:** a linked pair in 3 of 3 runs, V-L half confirmed 3/3,
  citing the contract's brownish trousers. In the split v3 runs it was
  rejected 2/2.
- **P3, long-coat adult:** V-L half confirmed 2/2.
- **P4, gun:** V-L half confirmed 1/1, but it was only created in 1 of 3 runs;
  the other two report V-V only.
- **P1, woman's outfit:** a linked pair in 1 run, separate V-V and V-L issues
  in 1 run, and not reported in 1 run.

### Side effects in discovery

The one-label-per-issue rule is not always followed. Two cross-shot visual
differences were filed as V-L only:

- the #014 fresh_1 courtyard (confirmed);
- the #069 fresh_1 jacket pattern, which was rejected, so that verified
  artifact was lost because no V-V issue existed.

A deterministic gate cannot tell these apart from legitimate V-L-only issues
spanning several shots (for example a wrong hat in two shots).

## Conclusion

- **What the rule fixes.** It removes the shot-by-shot V-L rejections that
  remained after the split: 9 of 12 recovered, and the rest rejected on the
  merits.
- **Overall effect.** It raises verified-artifact confirmations on identical
  candidates (69 → 78 of 92) without confirming controls (0 of 6). With
  fresh discovery it gives the best artifact count of the three chains,
  within noise.
- **New risk.** The reviewer sometimes treats an earlier shot's depiction as
  the requirement (a jacket's diamond pattern where the text only says
  "patterned"). Possible fix, not applied: state that the requirement is the
  wording of the description, not how another shot happened to depict it.
- **Open issue.** Discovery still occasionally files a cross-shot visual
  difference as V-L only.

## Limitations

- One to three runs per condition.
- Matching, rejection-cause classes and artifact annotations are assistant
  judgment, not human labels.

## Addendum: in-place fix of review v5 (the wording is the requirement)

At the user's direction (a bug fix, no new version), review v5 now also says:
"The requirement is the wording of the description, not how another shot
happened to depict it: a visual attribute that merely appeared in another
generated shot is not a requirement unless the text states it."

- **Prompt hashes:** `42568de9…` before the fix, `f439fd4f…` after. The
  pre-fix copy is in `source_before_fix/`. All runs above used the pre-fix
  prompt.
- **Targeted check** (`fix_check.py` → `runs/fix_check/`): nine frozen
  discovery outputs, review only, two repeats, all with the fixed prompt.

| Label | Pre-fix review v5 | Fixed review v5 (×2) |
| --- | --- | --- |
| #069 run b I2: jacket pattern (+ gun) | confirmed via pattern + gun | confirmed ×2, reasoning now says only "patterned" is required and confirms via the gun (fixed) |
| #069 run a I1: jacket + gun | confirmed via pattern + gun | confirmed ×2; one review still cites the stripes vs Shot1's diamond pattern |
| #069 split run 3 I4: jacket + gun | confirmed via pattern + gun | confirmed (pattern + gun), rejected ("still patterned, gun still angular") |
| #069 split run 2 I7: jacket pattern only | confirmed (over-reach) | confirmed ×2, still "not the diamond jacket seen in Shot1" (not fixed) |
| 10 labels recovered by the entity rule (trousers, coat, gun, shirt) | confirmed | 19 of 20 reviews confirmed (one coat label rejected once) |

- **Outcome:** the sentence alone fixes the reasoning in some reviews but not
  reliably. The pure pattern case is still confirmed from the earlier shot's
  look.
- **Variance across all labels of the nine runs:** V-L 4 confirmed →
  rejected and 6 rejected → confirmed, which is normal run-to-run variance.
- **Cost:** 18 calls; 277,580 uncached input, 277,526 cached input and 38,318
  output tokens. That is USD 0.0497 at the GPT-6 Luna standard API estimate,
  not a billed amount.

## Addendum 2: second in-place sentence ("compare the shot directly with the quoted words")

At the user's direction, review v5 also gained: "Compare the shot directly
with the quoted words. If the shot satisfies the words (for example, any blue
car satisfies "a blue car"), reject the V-L label even if the shot looks
different from another shot; that difference is a V-V question."

- **Prompt hashes:** `f439fd4f…` before, `6bec2d8e…` after (current). The
  copy before this change is in `source_before_fix2/`.
- **Re-run:** the same targeted check, `fix_check.py … fix_check2` →
  `runs/fix_check2/`.

| | Pre-fix review v5 | First fix (×2) | Second fix (×2) |
| --- | --- | --- | --- |
| Jacket-pattern over-reach labels (4 labels, 8 reviews) | 4/4 confirmed | 7/8 confirmed | 2/8 confirmed |
| Labels recovered by the entity rule (10 labels, 20 reviews) | 10/10 | 19/20 | 16/20 |
| All V-L labels in the nine runs (86 reviews) | – | 73 confirmed | 49 confirmed |

- **Pattern over-reach (fixed).** The reviewer now says stripes satisfy
  "patterned jacket" in 6 of 8 reviews.
- **Over-correction 1: stated continuity.** "The same Beige sofa", "back in
  the corridor" and "the same room" are now rejected because a difference from
  another shot "is a V-V question". These requirements are inherently
  comparisons with other shots, so the sentence contradicts them. Examples:
  #002 sofa labels (verified artifact A2), and #069 Shot3 corridor.
- **Over-correction 2: only the shot's own words.** The reviewer checks just
  the shot's short wording and ignores the rest of the episode-wide
  description. Examples: #069 gun ("still angular", ignoring "large … bulky
  textured casing"); colour shades accepted as "fits the broad description"
  (olive vs gray-brown coat, dark vs brownish trousers).
- **Conclusion:** the second sentence trades the pattern over-reach for a
  larger loss of real V-L violations. Recommended: revert it, or reword it so
  that (a) explicit continuity wording ("same", "remains", "returns") still
  requires matching the other shots, and (b) the comparison is against the
  entity's full description, not only the shot's own words. Not applied
  without the user's decision.
- **Cost:** 18 calls; 278,102 uncached input, 278,048 cached input and 40,139
  output tokens. That is USD 0.0507 at the GPT-6 Luna standard API estimate,
  not a billed amount.
