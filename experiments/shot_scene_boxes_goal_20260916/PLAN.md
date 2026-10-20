# Goal: accurate all-entity 3D boxes in fixed per-shot scenes

Status: implementation and bounded method comparison completed on 2026-09-16. All41 entity outputs, estimated trajectories, per-frame poses, seven new method variants, common-MSE comparison and audits delivered. See RESULT.zh.md. This is not a claim of ground-truth 3D accuracy or reliable physical cross-shot alignment.

## Requirements / completion evidence

1. Each supplied entity in Study2 shot1/shot3 receives a 3D box in its own shot's fixed scene frame. Frozen full inventory is 19/22; do not silently restrict output to 17/21 static. Moving entities: representative box plus per-frame trajectory; explicitly confirmed by user on 2026-09-16.
2. Independent per-shot processing, explicit per-frame camera poses, shared within-shot scale. No across-shot information in reconstruction/fitting/classification. Never use a constant camera merely because old adapters did.
3. Research before model selection; use public primary sources and current model revisions. Compare credible advanced candidates against the old GeoCalib/Boxer baseline. Track runtime/setup cost as well as quality.
4. Common evaluation: frozen confirmed static intersection (11 pairs), gravity-preserving positive-scale similarity, plain unweighted eight-corner MSE, no Huber or orientation term. Resolve arbitrary cuboid corner numbering with the same 24 proper corner permutations for every method. Seek a global yaw optimum by a piecewise sinusoidal correlation envelope; report numerical coverage and degeneracies, not an unsupported generic global certificate.
5. Report raw coordinate MSE, dimensionless MSE (divide by target RMS radius squared), reverse-direction check, fitted scale and per-entity residuals. Equal entity weight; fixed complete intersection, no cherry-picked subsets. Scale-invariant normalization prevents units alone determining rank. Do not shrink or jointly change both scene geometries to win alignment.
6. Best achievable MSE is the requested comparison criterion, supplemented by original-image reprojection, all-entity coverage, geometric validity and within-shot stability, so distorted/shrunken/missing boxes cannot masquerade as accurate geometry. Known cup-holder anomaly not used as a reconstruction target. Reprojection is input-conditioned, not ground-truth 3D validation.
7. Deliver selected method's reusable runner, complete boxes/poses/provenance, original-frame and 3D visuals, comparison table and limitations. Validate camera motion with a meaningful synthetic transform check and real recovered trajectories. Avoid claiming ground-truth accuracy without GT.

## Staged experiments

- Freeze existing original JPEGs and 2D registries; start with six supplied frames per shot, expand or track if evidence warrants. User permits extra references; do not overwrite existing JPEGs.
- Baseline: existing Codex3D, Boxer+CodexCamera, GeoCalib+Boxer outputs under identical corner-MSE comparator.
- Primary geometry candidates: DA3NESTED-GIANT-LARGE-1.1 (depth + pose + metric prior) and Pi3X (independent multi-view geometry). Apply each separately within each shot. Combine its point/depth evidence and poses with BoxerNet; compare depth-conditioned versus direct point/mask fits as justified.
- Secondary candidate: DVLT (Déjà View) if released checkpoint and ROCm-compatible inference are practical. Assess SAM 3/3.1 masks/tracking and SAM 3D object completion if initial boxes remain weak. Read actual official release/inputs before using.
- Lucida and CalibAnyView: research lead, not claimed run; verify code and weights availability before promising reproduction.
- Dynamic labels stay independent per shot if rejudged. No new entity discovery unless requested/needed; supplied frozen entities remain coverage denominator.

## Primary-source research (accessed 2026-09-16)

- DA3: https://github.com/ByteDance-Seed/Depth-Anything-3 and https://arxiv.org/abs/2511.10647 . Current README deprecates original Giant/Large in favor of -1.1; nested model adds metric scaling; ray-head pose is slower but generally more accurate. Supports predicted full extrinsics/intrinsics and multi-view consistent depth. Start from current strongest nested checkpoint, not old weights.
- Pi3X: https://github.com/yyfz/Pi3 . Dec2025 engineering update, ICLR2026 Pi3 foundation: permutation-equivariant multi-view points and c2w poses; Pi3X improves confidence, smoothness and approximate metric scale. Independent comparator.
- DVLT: https://github.com/nv-tlabs/dvlt . May2026 paper, released code/weights, iterative transformer with compute adjustable recurrence and benchmark comparisons to DA3/Pi3/MapAnything/VGGT. ROCm integration not yet validated.
- Boxer: https://github.com/facebookresearch/boxer and https://arxiv.org/abs/2604.05212 . Complete 7DoF boxes from images, 2D prompts, calibration/gravity and optional point depth. Existing local weights usable; current historical run omits depth. Official code says depth materially helps; unknown camera calibration route not validated in original paper.
- Lucida: https://arxiv.org/abs/2608.30821 and https://lucida-r2s.github.io/ . Aug2026 multi-view parsing and iterative grounding; scene-level mAP beats Boxer in reported setup. Project page currently exposes no code link in fetched content; availability unresolved, no implementation claim.
- CalibAnyView: https://arxiv.org/abs/2605.14615 . May/Aug2026 multi-view intrinsics/gravity, not alone full camera translation or depth.
- SAM3D: https://github.com/facebookresearch/sam-3d-objects . Object completion potentially useful but heavier integration and image-conditioned hallucination risk; compare observed geometry, do not equate plausible meshes with accurate boxes.

## Safety / reproducibility

Reuse allocated node after live CPU/GPU inspection; bind ROCr by checked UUID, never physical ordinal. Never mutate shared Python environment, historical predictions or releases. Pin source revisions/model file hashes and exact inputs. All heavy computations/download setup on allocated compute node. New goal does not authorize unrelated external services; configured Codex processing remains authorized.
