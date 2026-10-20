# Multi-keyframe image-driven scene registration test

Authorized 2026-09-16. Objective: expose spatial-relation inconsistency, not maximize entity agreement. Freeze both independently produced Pi3X scenes, 19/22 boxes, original six JPEGs per shot, per-frame K/camera-to-scene, 11 static matches. Never feed expected cup-holder anomaly into matching, transform selection or optimization.

Predeclared alignment support: four common large environmental structures g01 painting, g04 desk/table, g10 rug, g12 radiator. Pixel features only; their predicted box centers/corners do not fit the transform. Other visible entity rectangles, expanded 5px, mask moving objects and portable/plant contents. This selection is a reference assumption to test, not proof those structures are consistent. Fit does not require all reference regions to agree; report incompatible regions explicitly.

Run official RoMa v2 matching on all6x6 original frame pairs. Save raw correspondences/confidence before filters. Add classical SIFT as independent image-based check. Lift valid corresponding pixels through each frame's own frozen depth/local points and full camera-to-scene pose. Do not assume same camera across frames. Estimate one positive-scale, gravity-constrained scene3->scene1 transform robustly; refine symmetric per-frame reprojection using only correspondence evidence. Also compare per-reference and frame-subset solutions to detect an impossible single transform.

Validation: spatial holdout tiles reserved before fit; separate frame subsets and structural regions for consistency checks. Adjacent video frames are correlated, not independent samples. Report geometric support distribution, 2D match/pose/reprojection error, held-out evidence, transform stability and excluded regions. Do not choose transforms by known anomaly, cosine mean, or all-entity box MSE.

Freeze selected transform(s), then export all41 boxes/trajectories into Shot1 scene. Calculate all55 common-static unordered relation cosines using same vector orientation. Inspect the pencil cup -> dark green mug pair only downstream. Retain per-candidate results if alignment is ambiguous; unknown is not a consistency pass. Compare original box-MSE transform for diagnostics. No per-entity movement/warping to erase anomalies. Existing inputs/scores remain immutable.

Primary sources consulted: https://github.com/Parskatt/RoMaV2 (v2.0.1 code/weights), https://github.com/naver/mast3r (possible fallback); frozen Pi3X local reconstruction from preceding experiment. Do not call any method universally SOTA.
