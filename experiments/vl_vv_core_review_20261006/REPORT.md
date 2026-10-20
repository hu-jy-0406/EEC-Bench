# Core-problem review (v4) and one-label-per-issue discovery (v3) — 2026-10-06

## Requests

1. **Remove partly true; judge the core problem.** Remove the partly-true
   verdict and return to confirmed / rejected / uncertain:
   - confirm when the core problem is real, even if secondary wording is
     wrong;
   - reject only when the core problem is false;
   - use uncertain when it cannot be reliably verified.
2. **Test the two failure modes.** On E1 (#014 Wan2.1 run c I1), E2, E3, E5
   (#069 Wan2.1) and #068 HoloCine I5, test whether:
   - (1) the new V-V / V-L definitions stop V-V problems being filed as V-L;
   - (2) the revised rules stop real issues being rejected because of
     imperfect wording.
3. **Split dual-labeled issues (follow-up).** A V-L half must not be rejected
   because another shot matches the prompt. Split such issues at discovery:
   one V-V issue (Shot A vs Shot B) and one V-L issue (Shot B vs the prompt).

## Implementation

- **Review v4.**
  - Spec: `docs/vl-vv-issue-review-v4.md`.
  - Verdicts are judged on each label's core problem.
  - Evidence roles are relative to the core problem.
  - A confirmed label without a supporting frame goes back to the model
    instead of being turned into rejected.
  - Scoring v3 is unchanged.
- **Partly true removed.** The prompt and schema of review v3 / scoring v4 are
  archived under `prompts/retired/` and `schemas/retired/`, and no runner
  accepts them.
- **Discovery v3.** Spec: `docs/vl-vv-issue-discovery-v3.md`. Each issue
  carries one label, and a linked V-V / V-L pair replaces a dual-labeled
  issue.
- **Default chain:** discovery v3 → review v4 → scoring v3. Review v2 and
  discovery v2/v1 remain selectable.
- **Tests:** 74 VL/VV tests pass. Pre-change copies are in `source_before/`
  (review change) and `source_before_split/` (split).

## Runs

- **Allocation:** all runs used existing allocation 236651 / node270 (CPU
  load ~0, API-bound), with no GPU.
- **Scripts and output:** `run_jobs.py` (phases 1–2), `launch.sh`, output in
  `runs/`, summary in `analyze.py` → `analysis.json`.
- **Hand-made files:** `labeling_matches.json` (problem ↔ issue matching) and
  `vl_rejection_reasons.json` (cause of each rejected V-L half). Both are my
  judgment, not human labels.

| Set | What |
| --- | --- |
| `fixed/` | Review only, on the frozen discovery outputs of the target runs. Review v2 ×3 (two from before) and review v4 ×3 on #014 run c and #069 runs a–c; review v4 ×1 on all 24 clip runs; review v2 ×3 and v4 ×3 on #068 HoloCine run a. |
| `labeling/fresh_1..3` | Fresh discovery v2 + review v2 on #014 and #069 Wan2.1. `fresh_v4/` re-reviews these with v4. |
| `labeling/v1_rerun_1..2` | Two old-pipeline (v1) runs of #069, so both videos have three old runs. |
| `split/fresh_1..3` | Discovery v3 + review v4 on #002, #014, #069 Wan2.1 and #028 Wan2.2. |

#068 HoloCine was re-reviewed on the keyframes I5 was proposed on (with
`--allow-legacy-nominal-keyframes`). This is a fixed-input test of the review
rule, not a new evaluation of the video.

**Cost:** 163 model calls; 2,889,836 uncached input, 2,235,545 cached input
and 233,606 output tokens. That is USD 0.428 at the GPT-6 Luna standard API
estimate (USD 0.10 / 0.01 / 0.50 per M), not a billed amount.

## 1. Wording-caused false rejections: fixed for the motivating case

Review of the identical candidate issues. "Old" is the previous review (v2),
"new" is review v4.

| Label | Old review ×3 | Partly-true review | New review ×3 |
| --- | --- | --- | --- |
| #068 I5 V-V within presence (people vanish; "woman returns" wrong) | rejected, rejected, confirmed | – | confirmed ×3 |
| E1 V-L (scarf hides required neckline) | rejected, confirmed, confirmed | partly | confirmed ×3 |
| E2 V-L (short figure) | rejected, rejected, confirmed | partly | rejected, rejected, confirmed |
| E3 V-L (long-coat adult) | confirmed, rejected, confirmed | partly | confirmed, rejected, confirmed |
| E5 V-L (gun) | rejected, confirmed, confirmed | partly | rejected, confirmed, confirmed |
| V-V labels of E1–E5 | confirmed in all 15 old reviews | confirmed or partly | confirmed ×15 |

- **I5.** In all three new reviews the assessment names the core problem (an
  unexplained disappearance inside Shot6). One of them explicitly calls "the
  woman returns" inaccurate.
- **E2, E3 and E5.** The remaining V-L rejections are not about wording. They
  come from the V-L half itself; see section 3.

### Regression check (24 clip runs, one new-review run, same candidates)

| | Old review | Old review, repeat | New review |
| --- | --- | --- | --- |
| Labels confirmed / 128 | 91 | 98 | 93 |
| Verified-artifact labels counting against the score / 92 | 76 | 78 | 69 |
| Control labels counting against the score / 6 | 0 | 2 | 1 |
| Uncertain verdicts | 3 | 1 | 4 |

The new review differs from both old reviews (which agree) on 9 labels:

- **Lost 5 (verified artifacts).** Three are V-L halves of dual issues
  rejected by shot-by-shot reading. The #002 face change and the #047 shirt
  shade became "uncertain".
- **Gained 4.**

On identical V-L halves of dual issues, the new review confirmed 31 of 54 and
the old review 35. On V-L-only and V-V labels it confirmed slightly more. The
broad picture is within the old review's own run-to-run variance (17 of 128
labels flip between two old-review runs). The "uncertain" option is used for
hard face or colour-shade comparisons, which can drop real problems.

## 2. V-V problems filed only as V-L: fixed by the new definitions

How each run reported the four target problems:

| Problem | Old pipeline (3 runs) | New definitions, one issue per discrepancy (6 runs) | Split, discovery v3 (3 runs) |
| --- | --- | --- | --- |
| P1 #014 woman's outfit (E1) | not found; **V-L only**; V-V only | V-V only ×2, both labels ×3, **V-L only** ×1 | V-V only; not found; linked pair |
| P2 #069 short figure woman → man (E2) | not found ×3 | both labels ×5, not found ×1 | linked pair ×2, V-V only |
| P3 #069 long-coat adult (E3) | V-V only; not found ×2 | both labels ×6 | linked pair ×3 |
| P4 #069 gun (E5) | V-V only ×2, **V-L only** | both labels ×6 | V-V only ×2, linked pair |

- **Old pipeline.** It filed a cross-shot visual change only as V-L in 2 of
  its 6 reports.
- **New definitions.** The V-V aspect carries a V-V label in 22 of 23 reports
  with one-issue-per-discrepancy discovery (one V-L-only miss), and in 11 of
  11 with the split.
- **V-V verdicts.** The V-V labels of these problems were confirmed in almost
  every review. The one exception is P2 fresh run 3, where discovery used the
  wrong subcategory (`instance_count`).

## 3. The V-L half of a dual issue: helped only partly by the split

Review v4 verdicts on V-L labels whose discrepancy is also reported as V-V.
The "v2" column covers runs a–c of four videos plus fresh runs 1–3 of #014 and
#069; the split column covers 3 runs of each of the four videos.

| | Discovery v2, one issue with both labels (18 runs) | Discovery v3, linked pairs (12 runs) |
| --- | --- | --- |
| Paired V-L confirmed / rejected | 31 / 23 (43% rejected) | 15 / 10 (40% rejected) |
| Rejected because the requirement was read shot by shot ("this shot's text does not restate it", "another shot satisfies it") | 10 (19% of paired V-L) | 2 (8%) |
| Rejected because the V-L claim is not a text requirement (gender, exact pattern) — correct | 7 | 5 |
| Rejected on a visual judgment (viewpoint, colour shade, "still angular") | 6 | 3 |

- **What the split fixes.** It nearly removes the failure you described. P3's
  V-L half (Shot4 coat colour) was confirmed in 3 of 3 split runs, against 4
  of 6 when it shared an issue with the V-V label.
- **Why the overall rate barely moves.** Split discovery also creates V-L
  halves for things the text never states (correctly rejected), and the
  visual-judgment rejections remain.
- **Remaining shot-by-shot cases.** Both concern #002's shirt. The global text
  says "faded blue-gray T-shirt" while Shot3's own text says "blue-gray
  shirt": the source itself is ambiguous.

### Recall check

I matched the split runs' issues to the verified artifact lists by hand.
Artifact-runs found:

| Video | Dual-label runs a–c | Split runs 1–3 |
| --- | --- | --- |
| #002 Wan2.1 | 10 / 12 | 7 / 12 |
| #014 Wan2.1 | 8 / 15 | 9 / 15 |
| #028 Wan2.2 | 9 / 15 | 4 / 15 |
| #069 Wan2.1 | 8 / 18 | 12 / 18 |
| **Total** | **35 / 60** | **32 / 60** |

Confirmed under review v4: 34/60 for the dual-label runs, 30/60 for the split
runs. The difference is within noise for three runs per video. #028 dropped
sharply, and the split runs sometimes omitted a V-L half (the gun's V-L half
appeared in 1 of 3 split runs, against 6 of 6 dual-label runs).

## Main remaining cause and a proposed rule (not applied)

The contract's character and object descriptions are episode-wide. In #069,
"Short dark-clothed figure ... brownish trousers" and "Long-coat adult ...
gray-brown coat over dark trousers" are defined once, and Shot4 only names
these characters. The reviewer repeatedly treats such a description as a
requirement of the shot where it was written, and rejects violations in later
shots.

The proposed rule, for discovery and review: an entity description in the
contract (or the global prompt) applies in every shot where that entity is
scheduled or visible, unless that shot's own text explicitly describes it
differently. This changes input semantics, so it needs the owner's decision.

## Limitations

- One review run per protocol on the 24-run set.
- Three discovery runs per video.
- Problem matching, rejection-cause classification and artifact annotations
  are assistant judgment.
- #068's discovery was not rerun on the new keyframes, which would need GPU
  detection.
