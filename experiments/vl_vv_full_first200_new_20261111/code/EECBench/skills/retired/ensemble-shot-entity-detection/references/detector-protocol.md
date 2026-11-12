# Detector-only three-pass inventory protocol

Policy version: `single_shot_detector_three_pass_coverage_v0.4`.

This is the complete model-visible policy for one homogeneous detector call.
Do not append adjudication, verification, graph-partition, prompt-bound matching,
grounding, relation, or cross-shot policy to a detector prompt.

## Input boundary

Inspect exactly one shot. Use all attached reference frames jointly and only the
provided attachment-to-frame mapping. The prompt-bound registry, other detector
outputs, other shots, expected differences, and cross-shot consistency are
prohibited inputs. Do not use shell tools, search the workspace, spawn agents, or
infer relations.

Return one shot-level physical-entity inventory. The detector proposes content;
it does not decide whether an entity is prompt-bound.

## Entity scope

Include bounded, visually distinguishable, temporally coherent physical content
that is useful as a scene-graph node:

- people, animals, furniture, movable objects, containers, bounded collections,
  functional architectural fixtures, and bounded mounted physical objects;
- separable objects resting on or inside a large host when their own boundary,
  state, handling, or trajectory establishes an independent identity;
- a stationary fixed or mounted object when its persistent physical boundary and
  identity are visible. Motion and interaction are not prerequisites.

Low contrast, small image area, a peripheral or background location, partial
occlusion, and lack of interaction are not by themselves exclusion reasons. Use
a broader name plus an uncertainty flag when physical identity is supported but
the subtype is not.

Exclude empty space, undifferentiated surfaces or substrates, illumination,
shadows, reflections, textures, color patches, non-physical phenomena, depicted
content, entities inferred only from commonsense, and regions without a bounded
coherent physical identity. There is no discovery quota: a reviewed region or
content stratum may contain no eligible entity.

Treat clothing, footwear, hair, body parts, and ordinary accessories as part of
a person while worn. Keep held or carried objects separate when their own
boundary, state, coherent motion, or interaction supports an identity. Do not
merge a spatially separable object into a large support merely because boxes
overlap or one contains the other.

Physical distinctness and graph-node partition are different judgments. Keep
ordinary integrated parts with their whole. Use one node for a compact local
assembly whose constituents remain positively coupled. Split a constituent only
when the shot directly shows separate handling or use, detachment or a standalone
state, relative motion, or an independent trajectory. Different names, colors,
materials, abstract functions, theoretical removability, and internal boundaries
alone are insufficient. If partition remains unresolved, use one broader node
with an uncertainty flag rather than double counting.

## Canonical category scope

A passive homogeneous collection has one canonical scope: all visible passive contents of one physical category within one clearly bounded storage or display fixture, across its internal shelves, bays, rows or slots. The fixture is excluded from the content node. Internal dividers, crop, color differences, or separately localizable subgroups alone do not split this collection. Different fixtures, individually framed artwork or separately mounted complete display fixtures, heterogeneous neighbors, and objects separately handled or used during the shot remain separate. Same-role covering or control panels serving one bounded fixture use one whole-array scope, excluding that fixture, unless directly observed independent handling, use or motion warrants a split. Apply these scopes at discovery and final partition regardless of whether proposals initially used whole collections or subdivisions. A shared unbounded surface alone never establishes this organization.

## Required three-pass method

Complete all three passes internally before emitting the single final JSON
ledger. All four detectors use this identical method.

### Pass 1: provisional physical inventory

Inspect all frames together and build a provisional inventory before applying
salience or graph-node exclusions. Track the same physical content across time.
Do not stop after foreground actors, manipulated objects, or large furniture.
At this pass, noticing a candidate and accepting it into the final ledger are
separate decisions.

### Pass 2: deterministic coverage and residual-recall audit

Reinspect the original pixels independently of the provisional list.

1. Review every cell of this fixed image-plane grid:
   `upper_left`, `upper_center`, `upper_right`, `middle_left`,
   `middle_center`, `middle_right`, `lower_left`, `lower_center`, and
   `lower_right`.
2. Review every content stratum:
   `actors_and_independently_handled_objects`,
   `freestanding_and_supported_objects`,
   `containers_open_storage_and_bounded_collections`,
   `fixed_architectural_and_mounted_objects`, and
   `peripheral_cropped_and_exterior_bounded_objects`.
3. Compare every adjacent pair in the ordered reference-frame list for regions
   newly revealed by motion, an occlusion change, or a framing change.
4. Perform a candidate-boundary and perimeter scope audit for every provisional
   collection, compact assembly, container-content unit, large host or support,
   multi-element proposal, proposal cropped by an image edge, and proposal that
   lies immediately beside another bounded-looking region. First re-localize the
   claimed content from the original pixels without trusting its provisional box.
   On the clearest usable frame, trace the smallest apparent external footprint
   containing only the claimed content; then inspect every visually distinct
   region inside that footprint and a narrow perimeter immediately outside it.
   Confirm the scope on a second usable frame when one exists.

   Classify each inspected region as an intended member or integrated constituent,
   a separately localizable neighboring physical object, or unresolved/non-entity
   appearance. Propose a separate neighbor only when the original pixels show its
   own coherent boundary in at least two usable frames, or in one clear frame
   together with direct separate handling, state, motion, or trajectory evidence,
   and at least one scope-separation cue such as a visible gap or non-shared
   contour, independent mounting or support, a depth discontinuity, or distinct
   rigid or material structure. A different name, category, color, texture, or
   presumed function alone is not evidence of a separate object. A shared wall,
   shelf, table, container, or other background support alone does not make
   heterogeneous neighbors one collection.

   This is a scope-completeness audit, not an instruction to decompose every group.
   Keep homogeneous repeated members, ordinary integrated parts, and positively
   coupled compact assemblies at their existing scope unless the entity-scope
   rules independently require separation. Never emit both a broad proposal and a
   nested proposal for the same physical content. Do not turn a low-contrast
   patch, shadow, illumination boundary, reflection, texture, depicted content,
   compression artifact, or off-frame inference into an entity. If physical scope
   remains unresolved, keep one conservative broader proposal with an uncertainty
   flag instead of inventing a second object.

Add a residual candidate only when the original pixels satisfy the entity-scope
rules. A persistent fixed object can qualify through coherent multi-frame
boundary and identity evidence. A transient candidate needs comparably direct
one-frame boundary plus handling, state, or trajectory evidence. Do not invent an
entity to fill a grid cell or content stratum.

### Pass 3: conservative precision, identity, and box audit

Review the combined provisional inventory once more:

- remove aliases for the same physical content at the same candidate scope;
- reject a chimeric track that follows one entity in early frames and another in
  later frames;
- reject unsupported patches, effects, surfaces, depicted content, integrated
  subparts, and unresolved regions;
- preserve separately bounded, independently trackable content even under box
  containment;
- verify that each visible-frame box follows only the claimed entity rather than
  a holder, support, neighboring object, or the whole scene;
- repeat boundary closure for every scope-audited proposal and verify that each
  visible-frame box contains all and only its intended physical content; it must
  neither absorb a separately bounded heterogeneous neighbor nor copy the
  neighbor's footprint. When the claimed scope cannot be localized in a frame,
  use `uncertain` with a null box rather than copying a stale or borrowed box;
- apply the granularity rules once, after coverage is complete.

Emit only the final cleaned inventory plus its private coverage audit.

## Detector ledger contract

Set `source_kind` to `detector`, use the assigned `detector_id`, and use unique
local IDs. Each entity contains:

- `proposed_name`, `canonical_head`, `entity_type`, and `granularity`;
- attributes with original-frame evidence;
- nonempty representative `evidence_frame_ids` and `coarse_locators`;
- one `frame_presence` entry for every supplied frame;
- uncalibrated `self_confidence` and `uncertainty_flags`.

Use `visible` only when the instance is sufficiently localized for downstream
grounding. A visible entry has a tight full-frame-normalized
`bbox_xyxy_normalized=[x1,y1,x2,y2]` around only that entity. `absent`,
`occluded`, and `uncertain` entries have a null box and a concise visual reason.
Representative evidence need not enumerate every visible frame.

The top-level `coverage_audit` is mandatory and private:

- `reviewed_frame_ids` lists every supplied frame once in chronological order;
- `spatial_cells` contains every fixed grid cell exactly once, a valid
  `best_frame_id`, and a best-effort cross-index of final local IDs represented
  there;
- `content_strata` contains every fixed stratum exactly once and the final local
  IDs recognized during that review as a best-effort cross-index;
- `temporal_reveal_checks` contains every adjacent ordered frame pair exactly
  once, with any newly revealed cells and final entities newly revealed or
  materially confirmed by that comparison;
- `residual_added_local_ids` lists final candidates first added in Pass 2 and may
  be empty.

All referenced local IDs must exist and must not repeat within one list. Spatial
and stratum lists are private diagnostic cross-indexes, not a second entity
ledger; accidentally omitting a final entity from one or both cross-indexes does
not invalidate that entity. `temporal_reveal_checks[].added_local_ids` is
independent of `residual_added_local_ids`: the former records what a frame pair
revealed or materially confirmed, while the latter records only what was first
added during Pass 2. Audit records do not constitute evidence, confidence,
detector support, or votes, and must not be exposed to any downstream model role.
