# "Does not conflict with" wording in the V-L rule — change and check (2026-10-20)

## Request

Owner: keep the current rule (a shot that matches the words is not a V-L
violation even if it looks different from another shot; explicit continuity
words are the exception), and refine the wording by replacing "satisfies"
with "does not conflict with". In-place wording refinement of the current
default chain, no new protocol version.

## Change

Only the sentences that state this rule (pre-change copies in `source_before/`):

| File | Old | New |
| --- | --- | --- |
| `prompts/vl_vv_branch_definitions_v1.txt` (shared by all branch detection and review calls) | A shot that satisfies the words ("a blue car" is satisfied by any blue car) does not violate them … | A shot that does not conflict with the words (any blue car does not conflict with "a blue car") does not violate them … |
| same, boundary table | A shot satisfies the words but looks different from another shot | A shot does not conflict with the words but looks different from another shot |
| `prompts/vl_vv_issue_review_v6_vl.txt` | … while each shot satisfies the words, is not a V-L issue | … while neither shot conflicts with the words, is not a V-L issue |
| same, basis `visual_difference_only` | the shot satisfies the words and only differs | the shot does not conflict with the words and only differs |
| `configs/vl-vv-branch-v1.json` (documentation text only; not rendered into prompts or schemas) | same as the basis line | same |

Unchanged on purpose (different concepts): the V-L template status
`satisfied`, the rejection basis `requirement_satisfied` ("the frames satisfy
the quoted words"), the episode-wide rule "never reject … because another
shot satisfies it", and "JSON that satisfies the schema". Codes, schemas and
gates are unchanged; `build_vl_vv_branch_schemas.py --check` passes; 124
VL/VV tests pass.

SHA-256: definitions `f3de084a…` → `5ab883c1…`; review v6 V-L `cd7b854e…` →
`48ae4392…`; config `f937512d…` → `aa33821b…`.

## Check: same candidates, review only

`review_check.py`, `analyze.py` → `analysis.json`. The 16 V-L detection
results of the 2026-10-09 validation (8 videos × 2 runs) were re-reviewed
twice: arm `new` with the changed prompts, arm `old` with the pre-change
copies (a repeat of the original review; its rendered prompt is
byte-identical to the 2026-10-09 one). Image labels were off in both arms,
matching the original reviews, so only the wording differs. API only, on
existing allocation 286177 (node load checked before launch).

| | Original (10-09) | Old wording, repeat | New wording |
| --- | --- | --- | --- |
| Candidates confirmed / rejected / uncertain (of 50) | 42 / 8 / 0 | 42 / 6 / 2 | 39 / 9 / 2 |
| Rejections with basis `visual_difference_only` | 0 | 0 | 0 |
| Candidates whose state differs from the original | – | 7 | 9 |
| Differences between old repeat and new | – | – | 9 |

- **Within run-to-run noise.** The new wording differs from the original by 9
  candidates and from the old repeat by 9; two runs of the old wording
  already differ by 7.
- **The rule itself was never invoked.** No review in any arm rejected a
  candidate as `visual_difference_only`, and the changed new-arm rejections
  are factual readings of the frames (basis `requirement_satisfied`), not
  appeals to "does not conflict".
- **Three of the new-arm changes are wrong readings, not wording effects.**
  #032 run_a L2–L4 (one problem reported three times): the text requires the
  oven's "pale handle and glowing window on the right"; the frames show the
  oven on the left (checked by the assistant). Both old-wording reviews
  confirmed; the new review said the handle is on the right. #028 run_a L3:
  the Shot7 blue lounger is fairly sharp and mid-right, not "blurred in the
  far right background"; the new review rejected it. #028 run_b L1 (finger
  near chin) is debatable: hand at the ear in frames 0–2, finger at the chin
  in frames 3–5; the original review also rejected it. Images were
  unlabeled in this check, as in the original reviews; the current default
  sends labels.
- **Conclusion:** no measurable effect of the wording on these candidates;
  50 candidates and one repeat per arm cannot exclude a small effect.

## Cost

31 calls (15 reviews per arm, since #014 StoryMem run_a has no V-L candidates
and its review makes no call, plus one repair round in the new arm);
1,295,282 input tokens
(36,407 cached, 1,258,875 uncached) and 41,961 output tokens: USD 0.147 at the
GPT-6 Luna standard API estimate (USD 0.10/M uncached input, 0.01/M cached
input, 0.50/M output; not a bill). Old arm USD 0.073, new arm USD 0.074.

## Follow-up (2026-10-21): V-L detection on #032

This check covered the review stage only. The definitions also reach V-L
detection, and there the new wording appears to trigger rubber-stamping on
#032 Wan2.2: all 55 template rows `satisfied` in 3 of 4 runs with "does not
conflict with" versus 0 of 3 with "satisfies" (same day, image labels on),
although the model's own observation puts the oven handle on the left while
the text requires the right. #002 and #047 were not affected. Details:
`experiments/vl_vv_transition_provenance_20261021/REPORT.md`. The wording was
not reverted without the owner's decision.
