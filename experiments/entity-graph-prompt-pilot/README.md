# Entity-graph prompt pilot

This directory contains four low-density, eight-shot episode prompts for
testing shot-level scene-graph extraction and cross-shot graph comparison.

## Design contract

- Each generation prompt names one location, one person, and at most one
  manipulated prop. Ambient room objects are deliberately left open so the
  generator can create prompt-unbound entities.
- Each episode uses the pattern `location A -> brief location B -> location A`
  and contains an explicit legal removal plus an explicit legal introduction.
- The first and revisited views include a repeatable wide view. Reverse and
  close views provide partial overlap and deliberate non-observation cases.
- `_pilot_design` is metadata for experiment construction. The current Wan
  generation script ignores it and reads only `scenes[].video_prompts`.

## Recommended use

1. Generate the unedited baseline episode.
2. Keep only shot pairs where the baseline output actually contains two to four
   clear recurring prompt-unbound entities; do not force identity matches among
   repeated same-category instances.
3. Freeze the baseline entity correspondences and legal-change schedule.
4. Make one graph-level edit per counterfactual video: node addition/removal,
   attribute change, relation change, or violation of a scripted transition.
5. Ensure the edit is visible in at least two of the six uniformly sampled
   reference frames used by the current extractor.
6. Pair each inconsistent edit with an unedited control and, when possible, a
   visually similar benign edit so editing artifacts do not reveal the label.

The four prompts are ordered from cleaner object identity to more ambiguous
open-vocabulary structure: study, cafe, ceramics studio, rehearsal room.
