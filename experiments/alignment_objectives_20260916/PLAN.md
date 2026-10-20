# Unified alignment exploration — frozen plan

Scope: Study2 Shot3 -> Shot1; Study0 and Study1 are numerical same-view controls.
Reuse frozen static graphs and identity correspondences. No new detection, image
encoding, geometry inference, identity reassignment or production-score edits.

Two independent factors:
1. Objective: historical gravity-constrained corner Huber; center least squares;
   center Huber; center Huber + undirected horizontal long-axis sin-squared loss;
   axis-first with both 180-degree branches inspected; anchor-only center+axis.
2. Coordinate representation: gravity-aligned camera-origin coordinates versus
   independently constructed scene coordinates. When free similarity parameters
   and dimensionless objective are preserved these should be equivalent.

Transform: positive uniform scale, one yaw, xyz translation, hard gravity.
Final export includes ALL static boxes in actual Shot1 OpenCV camera coordinates,
including boxes not used to fit. One transform per shot, no per-object fitting.

Correspondences already known, kept fixed. Axis eligibility: both horizontal
aspect ratios >= 1.2 (also sensitivity 1.1, 1.5); opposite box-edge directions
are equivalent. No long-axis constraint on near-square footprints.

Predeclared parameter exploration: Huber delta 0.05 scene-baseline units;
axis weights 0, .001, .01, .03, .1, .3, 1.0, plus pure center L2 and axis-first.
Additional delta .025/.1 and loss/anchor sensitivity kept explicitly separate.
No selection to maximize cup-holder anomaly or final cosine consistency.

Evaluation: center residual AND axial residual; leave-one-entity-out prediction
and yaw stability; per-frame subset fits; synthetic known-transform recovery,
object motion/swap and axis-sign invariance; compare the two axial branches;
verify coordinate-change equivalence; show all pair cosines as diagnostics only.
Cross-validation is against imperfect reconstructed centers, not physical truth.
Report failure if center and orientation evidence cannot support one stable pose.

Background: Yang et al., TEASER, https://arxiv.org/abs/2001.07715 — robust
registration with correspondences and outliers. This experiment implements a
small gravity-constrained center/axis optimizer, NOT TEASER or a certified solver.

Historical correction: existing corner optimizer already used per-entity Huber
on eight-corner RMS with 24 cuboid symmetries; scene-frame coincidence was a
separate experiment, followed by a direction-only yaw pilot with scale/origin fixed.
