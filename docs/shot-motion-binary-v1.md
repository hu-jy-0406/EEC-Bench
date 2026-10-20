# Shot motion binary v1 — user revision, 2026-09-20

The user explicitly replaced per-interval expected/observed classifications with
one moving/static decision per frozen entity per whole shot. This is a protocol
revision, not a claim that whole-shot and interval scoring are equivalent.

## Classification

- **moving:** an applicable normal prompt action prescribes this entity's motion
  inside this shot, or original-frame evidence supports a natural causal dynamic.
  The cause must concern this entity; movability, neighboring motion or observed
  displacement alone is insufficient. A between-shot action does not authorize
  unexplained within-shot movement.
- **static:** no supported legitimate motion inside this shot. Unexplained drift,
  teleportation, swaps, camera-induced displacement, noisy geometry and ambiguous
  changes without a grounded cause do not earn a motion exemption. This label
  does not certify observed physical stability or anchor suitability.
- Legitimate movement anywhere in the shot gives one whole-shot moving label.
  There is no third motion class, interval list or separate observed classifier.
  Brief uncertainty can be recorded in the reason. Downstream event judgments
  retain their original unknown outcome and evidence requirements.

Output: entity ID, binary label, causal basis, valid prompt references, up to two
representative original-frame witness IDs and one short reason. All supplied
frames must be inspected, regardless of how many representative witnesses are
cited. Every call is a fresh isolated context with only its own shot's actual
evidence. Original frames are never resized or omitted.

## Transport and downstream contract

The classifier receives unchanged 2D boxes and each original OBB's defining
center, size and rotation, with camera poses/intrinsics. Redundant corners and
fusion diagnostics are omitted from this classification view; full canonical
inputs remain in `expected_motion/inputs/SHOT_full.json`. Existing compact
tables/references reduce repeated keys without rounding numbers or dropping
entities/frames. GPT-6 Astra/medium is retained.

Within-shot static checks apply to the static/static population throughout the
shot. A whole-shot moving entity no longer has separately checked earlier static
intervals; this is the explicit granularity revision. Abnormal motion with no
legitimate cause stays static and still generates negative-cosine/missing-box
proposals. Every keyframe-pair cosine still uses original per-frame geometry;
pair scoring retains the existing all-pairs denominator.

Cross-shot identity and exact tail/head comparisons include ALL entities,
including moving entities. No binary motion label automatically exempts a
boundary event. Other keyframes remain contextual witnesses. Existing spatial
prompts, causal/visibility/support gates and score formulas are unchanged.

The existing initial matching call assesses actual anchor stability from all
original frames and raw geometry. Binary static labels must never synthesize
`anchor_observed_static=true`. `match_binary_v1.txt` preserves the original match
prompt verbatim and appends only the binary-field interpretation. Only reliable
matched static structures may be anchors. Auxiliary fusion remains for identity
and registration; its selected/outlier flags never filter scoring geometry.
RoMa/FPS32 and the exact unweighted unsquared 3D distance objective are unchanged.

## Reproduction and scope

Selected default profile: `temporal_binary_v1`; explicit interval rollback:
`temporal_cost_v1`. The previous original temporal runtime remains
`safe_spatial_medium`. Legacy expectation JSON and interval proposal handling
remain supported for historical reproduction; new binary outputs are not
expanded into redundant interval rows.

Validation lives in `experiments/shot_binary_motion_20260920/`. Nine new isolated
classifier calls use frozen Study2/3/4 detector/geometry inputs. Subsequent CPU/API
replay reruns within-shot review, initial identity/anchor selection, lifting,
FPS32 fitting, aligned identity and boundary review, reusing only the original
frontend and raw RoMa image matches. This is not a new frontend/GPU/end-to-end
measurement. Read that run's final report/status before claiming quality
acceptance or default promotion. Never select reruns by their score.
