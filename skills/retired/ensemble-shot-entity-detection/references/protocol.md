# Single-shot inventory-first ensemble protocol

## Boundary and role isolation

Process exactly one shot at a time. This protocol reduces stochastic discovery
omissions; it must not make two shots agree. Other shots, their entities, and
expected cross-shot differences are prohibited inputs until this shot's final
entity set has been frozen.

The stages have separate authority:

1. four homogeneous detectors independently propose complete all-entity
   inventories from the same ordered frames;
2. a panel-aware inventory adjudicator clusters same-scope physical content and
   freezes existence, physical identity, salience, and entity scope;
3. two source-blind targeted verifiers recheck only supplied weak or conflicting
   clusters, after which the same adjudicator performs one physical-inventory
   revision;
4. the selected deterministic post-verification policy freezes physical anchors:
   `physical_v0.6` uses typed exact-scope physical evidence and explicit conflict
   resolution, independent of names or source support; `legacy` uses the
   one-source and configured generic-identity gates described below;
5. two isolated identical-input source-blind group/member family planners and a
   deterministic exact-consensus firewall audit explicit competing partitions
   and produce only provisional candidate scopes;
6. from the unchanged pre-group frozen baseline, a deterministic source-blind
   candidate bank enumerates mandatory questions, two isolated judges review every
   candidate, and a deterministic exact-consensus firewall alone applies final
   coarsenings;
7. a prompt-bound matcher classifies the final frozen accepted nodes against a
   semantic registry;
8. the orchestrator projects the prompt-unbound subset and later grounds it.

The prompt-bound registry is withheld from stages 1--6. The matcher sees no
prompt-bound detector boxes and cannot revise the inventory. Relation extraction
occurs later from frozen entity IDs.

## Entity scope and granularity

The graph unit is an observation-conditioned interaction unit, not necessarily
the smallest physically distinguishable part. Physical distinctness and
graph-node partition are orthogonal: visible boundaries may establish multiple
physical constituents while a later partition stage represents them as one node.

Apply these general scope rules:

- include distinguishable people, animals, furniture, movable objects,
  containers, and functional architectural fixtures when graph-worthy;
- include a separable object resting on, inside, held by, or carried by a large
  host when its own boundary, handling, carrying, state, or coherent motion
  supports an independent identity; containment or overlap is insufficient;
- treat clothing, footwear, hair, body parts, and ordinary accessories as part of
  a person while worn; split a constituent only after removal or another directly
  observed independently trackable state or interaction;
- merge ordinary integrated parts into their whole when positive visual evidence
  shows a continuous housing, joint, or direct operational coupling;
- treat a compact local assembly as one node only when positive cohesion supports
  it and no independence or protected-relation review blocks it. Lack of observed
  independence is not positive cohesion;
- a fixed coordinated repeated set can have positive cohesion when homologous
  same-role components occupy a stable complementary arrangement around one
  clearly bounded external reference and jointly realize one boundary, covering,
  control, or display scope in at least two common-visible frames. The excluded
  reference may create a gap, and a continuous connector need not be visible;
  merely sharing a substrate, support, proximity, or appearance is insufficient;
- do not merge across a large host or support, a person or animal, a protected
  holder/item or load relation under the shared rule below, or loose objects that
  merely share proximity or support outside the canonical fixture-collection policy,
  actual temporary packing or transport payloads, or worn/body scope cases;
- direct independence evidence is limited to separate handling or use,
  detachment or a visibly standalone state, relative motion, or an independent
  trajectory. Internal boundaries, different names, materials or colors,
  theoretical removability, abstract function, proposal repetition, and confirmed
  physical existence are not independence witnesses;
- use a group only when it is the chosen partition for the same member content;
  never retain both a group and its members as final nodes;
- outside canonical collections and coordinated arrays, keep same-category physical instances separate when original pixels resolve
  distinct boundaries or trajectories; otherwise preserve uncertainty;
- exclude undifferentiated scene substrates, empty space, illumination fields,
  non-physical visual phenomena, depicted content, and entities inferred only
  from commonsense unless another explicit mode changes scope;
- do not promote an unresolved visual region without evidence of a bounded,
  temporally coherent physical identity or independently supported interaction.

### Shared holding/container scope rule

Apply the shared holding/container scope rule to the exact candidate members, not their names. Protected holding/carrying includes an actor with an external held item and an inanimate mechanism or support retaining an independent load. Physical distinctness or containment alone does not establish that holder/payload relation. A visible holding or load state suffices; a pickup or movement need not be observed. Being stationary, small, portable or inanimate does not select a branch. Actual temporary packing, loading or transport payloads remain protected; ordinary storage is not temporary transport merely because later transport is possible.

A compact container-content functional unit requires positive original-pixel evidence that the bounded container structure organizes, constrains or presents the complete included content as one local functional scope. Identify that structure and organization beyond merely being inside, touching or resting on a support. Stable placement, tight enclosure, presumed conventional purpose or lack of observed separate handling alone is insufficient. Observed operation is unnecessary when visible structural organization directly supports the unit. An assembly-kind label never supplies this evidence or overrides protection.

When the only positive organization is one bounded fixture's passive same-category storage/display arrangement, the canonical collection contains its complete eligible contents and excludes the fixture. Adding the fixture requires independent positive evidence for the complete container-plus-content functional scope, not relabeling that collection. External references and independent context remain excluded. An external actor carrying a supported functional whole stays outside it; that external relation alone does not establish an internal member-payload relation.

Check actual protection and member independence before choosing cohesion. Present or uncertain protection, or observed or uncertain member independence, blocks coarsening. Absence of observed separate handling neither supplies cohesion nor by itself establishes absent protection. Unresolved classification or evidence preserves the frozen anchors; do not invent a positive explanation. All stage-specific full-scope, common-frame, context, agreement and geometry checks still apply. Graph grouping never makes physical constituents same-instance aliases.

Canonical names are lowercase singular nouns or short noun phrases. Put color,
material, state, and position in attributes or locators. Use a broader name plus
an uncertainty flag when subtype is unresolved. When a partition stage coarsens
nodes, preserve constituent semantics in structured attributes.

## Homogeneous detector panel

All four detectors receive the same ordered frames, mapping, scope rules, schema,
and complete-inventory instruction. The only prompt differences are the required
`detector_id` and consequent local IDs. Heterogeneous search paths are reserved
for an explicit ablation. The worker limit controls concurrency only. The
complete model-visible detector policy is
[detector-protocol.md](detector-protocol.md); never append this full downstream
protocol or its adjudication, verification, partition, matching, grounding,
relation, or cross-shot sections to a detector prompt.

Each detector sees all reference frames simultaneously and produces one
shot-level inventory through three ordered internal passes: provisional physical
inventory, deterministic spatial/content/temporal coverage, and conservative
precision/identity/granularity cleanup. The coverage pass reviews all nine fixed
image-plane cells, five fixed content strata, and every adjacent ordered frame
pair. It also re-localizes every provisional collection, assembly, multi-element,
large, cropped, or immediately neighboring bounded-looking scope from original
pixels and audits the claimed boundary plus a narrow exterior perimeter. A
heterogeneous neighbor requires repeated coherent-boundary evidence and a direct
separation cue; the audit must not decompose integrated or homogeneous content or
promote a patch, shadow, reflection, compression artifact, or other unresolved
appearance. A region may legitimately add nothing; the audit is not an entity
quota.
For each proposal the detector records:

- `evidence_frame_ids`: a compact set of best frames justifying existence,
  identity, and attributes;
- `coarse_locators`: descriptions tied to cited frames;
- `frame_presence`: exactly one entry for every supplied frame, using:
  - `visible` when the instance is sufficiently visible and localized for a
    downstream grounding attempt, with a tight
    `bbox_xyxy_normalized=[x1,y1,x2,y2]` around only that instance;
  - `absent` when evidence supports that the instance is outside the frame or not
    present then, with a null box;
  - `occluded` when continuing identity is supported but the boundary is not
    currently groundable, with a null box;
  - `uncertain` when the frame does not support a reliable determination, with a
    null box.

Before emitting a ledger, compare each candidate trajectory with all other
candidates in that ledger. Do not emit an alternate name for an already
represented footprint or a chimeric identity that copies different entities at
different times. Containment is insufficient: a small entity within a larger box
remains distinct when boundary, handling, state, trajectory, or interaction
supports it. A visible internal boundary alone does not decide final graph-node
partition.

Evidence citations are not a substitute for the presence ledger. A detector must
not read the registry, another detector output, context outside its allowed role
inputs, or another shot. Its top-level `coverage_audit` is private completion
metadata: validate exact frame, grid, stratum, and adjacent-pair structure plus
the validity and within-list uniqueness of every referenced local ID, then strip
it before anonymization. Spatial and stratum entity lists are best-effort
cross-indexes; omissions are recorded as nonfatal private diagnostics rather
than triggering detector retry. Temporal pair IDs mean newly revealed or
materially confirmed by that pair and are independent of the pass-2 residual
list. The audit is not evidence, confidence, support, a vote, or input to any
downstream model role.

## Panelized union and box challenge

Replace detector-local IDs with opaque proposal IDs and deterministically shuffle
the combined records using the manifest seed. Preserve four fixed panel records,
each containing one `panel_id` and the opaque proposal IDs produced by that
detector. Fixed panel labels expose homogeneous source membership, not local IDs,
self-confidence, specialization, relative quality, or authority.

The inventory adjudicator is the only model role that sees panel membership. It
may use within-panel partition patterns and cross-panel repeatability to identify
conflicts requiring inspection. Panel agreement is not visual proof, an existence
gate, a calibrated vote, or authority to reject a singleton. Original pixels
remain decisive.

The orchestrator also compares proposal trajectories only within each private
detector ledger. For a candidate visible in at least the fixed number of frames,
flag it when another same-ledger proposal has symmetric tight-box IoU above the
fixed threshold in at least the fixed fraction of its visible frames. Record
whether one track covers it or the covering track changes over time. Expose
anonymous proposal IDs, framewise IoU values, and fixed thresholds, but not local
IDs. This is a mandatory review trigger, never an automatic merge or deletion.

## Inventory adjudicator: physical-content authority

The persistent inventory adjudicator receives the same-shot frames, scope policy,
panelized anonymous union, and box challenges. The registry and full source map
are withheld. It must:

1. assign every anonymous proposal ID to exactly one nonempty cluster;
2. treat detector boxes as low-trust position hints that may be shifted,
   oversized, undersized, or attached to nearby content;
3. independently re-localize each proposal's claimed visual content in original
   pixels; correcting coordinates may not retarget a proposal to different nearby
   content;
4. cluster aliases by physical content before wording, but only at the same
   candidate graph scope;
5. retain distinct physical anchors when a frame resolves separate boundaries or
   when manipulation or trajectories establish distinctness, even if supplied
   boxes overlap, span both, or miss one;
6. resolve every box-trajectory challenge against pixels and reject or abstain on
   incoherent identities that merely copy other tracks;
7. assign `accept`, `reject`, or `abstain` based on existence, physical identity,
   salience, and scope, with representative evidence and a complete cluster-level
   presence ledger;
8. emit no relation, source guess, empty cluster, residual scan, or newly
   discovered entity.

This stage does not choose between graph partitions of physically distinct
anchors. For an explicit group/member conflict, accept the supported, separately
localizable member anchors and keep the supported group-level proposal or
proposals in one separate rejected alternative. Add `group_member_conflict` only
when rejection prevents simultaneous group/member double counting; the reason
must state that the represented content itself is supported. Do not use this flag
for hallucination, failed identity, or failed existence. For a possible accepted-
only compact assembly without an explicit group proposal, preserve the anchors
and add `possible_compact_assembly_partition` for later review.

`accept` at this point means a real, graph-worthy physical anchor. It does not
mean prompt-unbound, and it is not yet the final graph partition. The adjudicator
is not another detector.

## Targeted verification and physical-inventory revision

The orchestrator consults the private source map only to select clusters under
fixed triggers:

- distinct detector support is at most two of four;
- the initial decision is `abstain`;
- physical identity is ambiguous or uncertainty is explicit;
- a possible compact-assembly or component conflict exists;
- two provisional clusters form a review-only possible same-instance pair from
  shared naming, proposal heads, coarse same-frame locator evidence, or an
  anonymous same-detector trajectory challenge.
- two or more proposals already assigned to one initial cluster have persistently
  divergent, non-containing footprints over the fixed minimum co-visible frames.
  This intra-cluster trigger uses only anonymous proposal geometry, never source
  labels or detector counts.

The trigger requests inspection and never determines an outcome. Send every
target and explicit challenge pair to two isolated verifiers with the same frames
and no registry, panel membership, source map, or detector counts. Each verifier
reports existence, graph salience, same-physical-instance conflicts, advisory
same-graph-node conflicts, typed independence evidence, original-frame evidence,
and a reason. For every supplied intra-cluster footprint challenge it also returns
one required split judgment. A proposed split must partition every proposal in
that target cluster exactly once into at least two verifier-local physical units;
each unit must be independently confirmed as real and graph-worthy, and every
unordered unit pair must have direct same-frame evidence with a distinct locator
for each visible boundary. Boxes, names, alternating visibility, weak evidence,
overlap, and containment do not satisfy this requirement. Non-split judgments
carry empty unit and pairwise-evidence arrays. It cannot add a candidate, split a
cluster, or decide the final ledger.

The verifier input is a compact evidence projection. Preserve every selected
target and proposal ID, proposed name, granularity, location hint, per-frame
visibility and box, cluster index, and explicit challenge. Supply all original
frames. Omit prior adjudicator verdicts and reasons, proposal confidence and
uncertainty flags, aliases, attributes, and repeated presence descriptions.
Evidence locators must describe boundaries, continuity or separation, and
limitations of visibility. This reduces repeated and priming text without
altering evidence thresholds or dropping frames.

Normalize unit IDs away and retain a split permission only when both isolated
verifiers produce the exact same proposal-set partition. Resume the original
adjudicator once with both source-blind reports and only those exact consensuses. It must
regenerate a complete ledger over every proposal exactly once. It may change
existence, identity, salience, or scope decisions and merge true same-content,
same-scope duplicates. It may split one challenged initial cluster only after
independently confirming the physical boundaries in the original frames and only
with the exact consensus proposal partition. A deterministic firewall rejects any
other revision split under the default policy; the consensus is permission to
review, never an automatic split. The explicitly enabled
`single_survivor_scope_retention_v0.1` adds the separately authenticated
[one-survivor transition](scope-retention-protocol.md): exact two-verifier subset
proof, at most one accepted survivor, and uniquely owned nonaccepted residuals.
It never supplies an ordinary physical-split unit for the residual or changes an
original proposal's content. Protected deferred parents remain ineligible.
Neither permission has graph-partition authority: verifier graph fields
and absence of independence are advisory for later stages. It must preserve
accepted member anchors, supported rejected group alternatives and their
`group_member_conflict` markers, and accepted-only partition markers. Confirmation
that a rejected group alternative depicts real content does not promote it while
the mutually exclusive members remain accepted.

## Single-detector unanimity gate

This section applies only to `identity_review_policy=legacy`.

After revision and before graph partition, compute distinct detector support from
the private source map. For every final `accept` cluster with support exactly one,
map its proposals back to the relevant initial verification targets. Both
verifiers must provide complete reviews for every such target, and every review
must simultaneously report:

- `existence_judgment=confirmed`;
- `salience_judgment=graph_worthy`.

When revision split an initial target, cluster-level confirmation cannot be reused
by proposal overlap. Each accepted one-source child must exactly match a physical
unit in the two-verifier consensus, and both verifier reports must confirm that
exact unit's existence, graph worthiness, and visual evidence.

If either verifier is missing, incomplete, uncertain, contradictory, or reports
that the target is not graph-worthy, change the cluster to `abstain`, set
`final_entity=null`, and add `single_detector_consensus_gate_not_unanimous`.
Retain the full record for audit. Do not turn gate failure into silent deletion or
automatic rejection.

## Generic-identity evidence gate

This section applies only to `identity_review_policy=legacy`. Experimental
`physical_v0.6` replaces this gate and the one-source gate with an exact-scope
physical identity gate. Its adjudicator and verifier schemas keep existence,
within-cluster correspondence, between-cluster identity and category certainty
separate. The gate ignores names, free-text uncertainty flags and evidence-quality
adjectives. Category uncertainty alone never changes acceptance. Missing or
conflicting physical evidence requires abstention unless the revision records
the exact axis, target and proposal scope with a direct resolving observation.
Same-instance aliases require positive same-content, same-scope evidence;
unresolved identity is not an alias. The role-specific verifier policy is
`references/verifier-protocol.md` and excludes downstream workflow instructions.

Immediately after the one-source gate and before either graph-partition stage,
apply a second deterministic precision gate against the same frozen detector
roster and source map. It changes a still-accepted cluster to `abstain` only when
all of these predicates hold together:

- with legacy `nonmajority` mode only, twice distinct-detector support is no greater than the frozen detector count; current `all_support` mode applies the remaining evidence predicates at every support count;
- both the final canonical name and final entity name end in a narrow generic
  placeholder head rather than a resolved physical category;
- normalized uncertainty flags explicitly leave identity, category, class, kind,
  name, type, or subtype unresolved or present only speculative alternatives;
- neither every expected verifier's complete relevant review supplies strong
  confirmed, graph-worthy visual evidence nor every expected verifier supplies
  direct observed-independence evidence for the exact scope.

Map a revised cluster to every intersecting initial verification target. All such
targets must satisfy a rescue; one strong review and one moderate review do not.
For a child produced by an exact consensus split, parent-level confirmation is not
reused: only matching physical-unit evidence can rescue it. A missing verifier,
partial target, or inexact split mapping fails the rescue closed.

The placeholder vocabulary and uncertainty matcher are versioned and narrow.
Aliases and speculative detector names do not override the final adjudicated
placeholder identity. Concrete mounted objects, fixtures, containers, tools, and
other resolved physical categories are outside this gate even at low support.
Support is therefore never a standalone existence decision. Preserve the
candidate and all evidence in a private audit record, set `final_entity=null`, and
add the configured `all_support_generic_identity_evidence_gate` or legacy `nonmajority_generic_identity_evidence_gate` flag when its full conjunction fires.
Do not expose its source-derived diagnostics to any later model role.

## Explicit group/member family resolution

Run two isolated ephemeral group/member planners in parallel. Both receive the
same post-gate baseline, anonymous proposals, original frames, schema, and general
policy. Their model-visible views remove detector panels, source mappings,
counts, and provenance-derived diagnostics. Neither can see the other's output
or change existence, physical identity, or naming.

Every rejected baseline cluster marked `group_member_conflict` is a mandatory
original-pixel review target for each planner. Each plan lists the complete target
set in `reviewed_group_alternative_cluster_ids` and accounts for every target
exactly once: as a non-anchor in one family or in
`excluded_group_alternatives`. An exclusion records all accepted, resolved
candidate member anchors visually covered by the group claim plus the subset, if
any, that is independently graph-worthy context. Under
`zero_supported_member_anchor_exclusion_v0.1`, candidate anchors may be empty
when the claimed group scope cannot be resolved from the pixels, or with
`insufficient_supported_member_anchors` when no eligible accepted, resolved
baseline anchor can be supported as covered by the group claim, even if that
group scope is resolvable. When supported eligible anchors exist, list all of
them; the same insufficient-anchors reason may also retain a nonempty mapping
that cannot support a valid family. An empty-anchor exclusion is a conservative
no-op with unresolved coverage, not evidence of absent physical content, recovery
of rejected/abstained members, or merge authorization. Do not invent anchors or
relabel a resolvable scope as unclear. Other empty-list reason guards remain
unchanged. Omission is an invalid planner output, not an empty vote.

A valid family contains:

- at least two accepted, resolved baseline clusters, each anchoring exactly one
  visually distinct member content unit;
- at least one rejected baseline cluster containing only a supported group-level
  alternative marked `group_member_conflict`;
- every whole baseline cluster and every proposal in that family exactly once;
- direct pixel evidence that each group proposal spans exactly the same member
  content, with all referenced units visible in every cited frame;
- no abstained content, large host/support, protected holder/item or load relation
  under the shared rule, ordinary duplicate, or uncertain visual scope. Contents-
  only collections exclude their fixture; a complete container-content functional
  scope requires its own positive evidence and all remaining family qualifications.

A passive homogeneous collection has one canonical scope: all visible passive contents of one physical category within one clearly bounded storage or display fixture, across its internal shelves, bays, rows or slots. The fixture is excluded from the content node. Internal dividers, crop, color differences, or separately localizable subgroups alone do not split this collection. Different fixtures, individually framed artwork or separately mounted complete display fixtures, heterogeneous neighbors, and objects separately handled or used during the shot remain separate. Same-role covering or control panels serving one bounded fixture use one whole-array scope, excluding that fixture, unless directly observed independent handling, use or motion warrants a split. Apply these scopes at discovery and final partition regardless of whether proposals initially used whole collections or subdivisions. A shared unbounded surface alone never establishes this organization.

Each planner records only typed shot-observed independence witnesses. A witness
names one member pair and cites frames where both are visible. Families are
disjoint within a plan, and neither planner has final-decision or naming
authority.

Resolve each valid plan deterministically:

- no independence witness: select the supported group partition;
- every unordered member pair has a typed witness: keep the frozen member
  partition;
- some but not all member pairs have witnesses: fail closed to the frozen member
  baseline.

A gross group-proposal/member-track incompatibility in a structurally valid
family records a private `group_witness_invalid` and preserves baseline members.
It is not malformed output and does not cause a new visual sample. Retain the
exact group proposal, member and frame evidence; do not infer that two member
anchors are incompatible merely because this group proposal is misplaced.
The explicit stage cannot use that invalid group witness. An independently
nominated accepted-only candidate must instead pass both judges' complete
anchor and cohesion-reference localization reviews. Unresolved or conflicting
anchor scope blocks that candidate, without blocking a separately supported
subset. Noneligible candidates do not create overlap conflicts for eligible
ones; all other overlap protection remains in force.

Normalize a family by its complete frozen baseline-cluster scope, complete
proposal scope, and accepted member-anchor set. Ignore planner-local family,
unit, and witness IDs and free-text wording. Emit a provisional group candidate
only when both valid plans contain exactly one identical normalized family and
both per-plan resolutions select `group`. Exact agreement on `members` preserves
the baseline.
A family omitted from either plan, any scope/member/partition disagreement, a
duplicate signature, or a cross-plan overlapping or nested component preserves
the affected baseline clusters. A planner that fails both identical-input
attempts makes the shot incomplete; it is not an empty vote. When no eligible
rejected group alternative exists, write two validated synthetic empty plans and
make no model call. The presence of any marked alternative requires both planner
reviews even if structural exclusions are ultimately necessary.

Detector panel positions are computed only for private audit after matching,
over the consensus application plan alone. They neither qualify a family nor
select group versus members. The assembler may create an auditable provisional
view only for exact-consensus validated family clusters; it preserves all
proposal accounting and leaves every nonfamily cluster unchanged. That view is
never the baseline of the next stage and has no final coarsening authority.

## Accepted-only compact-assembly consensus

A passive homogeneous collection has one canonical scope: all visible passive contents of one physical category within one clearly bounded storage or display fixture, across its internal shelves, bays, rows or slots. The fixture is excluded from the content node. Internal dividers, crop, color differences, or separately localizable subgroups alone do not split this collection. Different fixtures, individually framed artwork or separately mounted complete display fixtures, heterogeneous neighbors, and objects separately handled or used during the shot remain separate. Same-role covering or control panels serving one bounded fixture use one whole-array scope, excluding that fixture, unless directly observed independent handling, use or motion warrants a split. Apply these scopes at discovery and final partition regardless of whether proposals initially used whole collections or subdivisions. A shared unbounded surface alone never establishes this organization. For passive homogeneous collections, structured `collection_scope_review` names an accepted external fixture and confirms scope/exclusions with two jointly visible evidence frames; other kinds use null. Passive fixture-organized contents are not temporary transport payloads merely because they are stored. Scattered items, heterogeneous independent contents linked only by shared storage/support, and actual packing/transport payloads remain protected. Different constituent categories neither supply positive cohesion nor negate directly demonstrated integrated or functional organization; all other scope, independence and protection requirements remain. Selecting an assembly kind cannot bypass them.


Against the unchanged post-gate, pre-group frozen baseline, deterministically
build a mandatory candidate bank. Raw neighborhoods are limited to member maps
in either valid explicit family plan, including structured exclusions and
non-consensus variants, and exact-scope verifier-declared partner maps. Those
explicit member maps define candidate anchors directly after mapped independent
context is removed, so lexical synonyms or number variation cannot erase a
planner-local closure. A second conservative seed groups otherwise unscoped
accepted anchors marked `possible_compact_assembly_partition` only when their
anonymous proposals share an exact normalized `(canonical_head, entity_type)`
pair. Detector frequency, panels, counts, scores, and boxes do not form or rank
candidates.

A validated verifier review may nominate an exact target-plus-partner set only
when it confirms real, graph-worthy content, recommends one graph node, and
reports no independence witness. Map each initial target's full proposal set to
one unique accepted resolved baseline anchor; any changed, missing, or ambiguous
scope drops the whole nomination. Normalize duplicate partner IDs and reject
self references. Preserve each declaration separately, without transitive
closure or automatic merging. Its private provenance never reaches the judges;
the nominated anchors receive the same final two-judge cohesion and protection
checks as all other candidates.

The public bank exposes only deterministic candidate IDs, peer-anchor cluster
IDs, and context-anchor cluster IDs. It strips proposal IDs, semantic-pair
derivation, raw neighborhoods, and provenance. Exact duplicate peer sets collapse
deterministically while retaining the union of context anchors. Candidate
variants may overlap; overlap is a firewall no-op rather than a hidden question.

Run two isolated ephemeral judges in parallel with byte-identical role inputs.
Each sees all original frames, the public bank, and only accepted, resolved
cluster names, granularity, attributes, evidence, and box-free presence. It does
not see proposal IDs, detector boxes, rejected or abstained clusters, uncertainty
flags, confidence, detector panels, counts, or source mappings.

Each judge lists every accepted cluster ID and candidate ID once. It accounts for
every candidate exactly once as either one family with the exact bank anchor set
or one structured exclusion. It cannot freely propose a family, omit or resize a
candidate, discover, reject, split, rename, classify, or infer relations. A
family reviews every supplied context anchor and directly excludes it from the
minimal cohesive closure; uncertain membership blocks coarsening.

A proposed family is valid only when:

- `common_visible_frame_ids` is exactly the intersection of visible frames for
  all anchors and contains at least two frames;
- every unordered pair has exactly one permitted positive cohesion witness using
  at least two family-common visible frames;
- positive evidence establishes one permitted cohesion kind: canonical passive
  fixture collection, integrated part-whole, compact container-content functional
  unit, fixed mounting/coordinated array, or direct mechanical/operational coupling;
  a shared semantic head, type, support, proximity, overlap or appearance alone
  does not establish any of them;
- every pair is reviewed over every supplied frame for all four independence
  kinds: separate handling/use, detachment/standalone state, relative motion, and
  independent trajectory;
- all six protected relations are reviewed: large host/support, person/animal,
  protected holder/item or load relation under the shared definition, loose
  shared-support/proximity items, temporary
  storage/transport payload, and worn/body scope;
- every independence outcome is `not_observed` and every protected-relation
  outcome is `absent`.

Under accepted-plan v0.5, every content unit also has an `anchor_scope_review`
covering all common-visible frames exactly once. Each observation identifies
the entire visible claim with a normalized box, correspondence/coverage status,
boundary evidence and limitations. Every cohesion witness has a
`reference_review` bound to an existing accepted anchor, or to visible intrinsic
structure within a member. It covers each witness frame and both exact members
with typed relationships and localized member/reference loci. External
references remain excluded. An arbitrary enclosing rectangle or unbounded
surface does not establish a physical structure. Honest uncertain or partial
observations are valid outputs that prevent coarsening.

Two judges must agree on the reference identity and relationship, with compatible
same-anchor and same-reference localization on at least two identical frames
covering the complete family. Local connection relationships require connected
loci; complementary arrays around a bounded external reference do not require
member overlap or contact. The final firewall recalculates the scope audit and
all existing checks. Geometry checks internal consistency and cannot certify
that two model reports did not share a visual error.

Permitted cohesion kinds include canonical passive homogeneous fixture collections, integrated part-whole structure, one compact
container-content functional unit under the shared holding/container rule, a
common fixed mounting, a stable complementary
same-role array around an excluded bounded external reference, and direct
mechanical or operational coupling. The complementary-array witness requires at
least two common-visible frames showing homologous construction, stable
complementary placement relative to the same bounded reference, and a joint
boundary, covering, control, or display scope. The reference remains outside the
family; its intervening gap does not invalidate the array and no visible
continuous connector is required. This does not license grouping heterogeneous
independently mounted or independently functioning subjects. Proximity, overlap,
contact, similar appearance, semantic relatedness, shared camera motion, or a
common substrate/support alone are not cohesion. Complete complementary-array
or canonical fixture-collection organization is positive evidence for those kinds;
it is not a requirement replacing the distinct positive evidence for other
permitted cohesion kinds. A selected kind never overrides protection or missing
complete-scope evidence.

This second gate has the only final coarsening authority. Its deterministic
resolver applies a family only when both valid plans classify
the same mandatory candidate as a family with the same assembly kind and both
reviews are completely clear. Either structured exclusion, kind disagreement,
an uncertain context/independence/protection review, or overlapping/nested
positive candidates leaves the pre-group frozen anchors unchanged, including
when the explicit stage emitted a provisional group. A judge that fails both
identical-input attempts makes the shot incomplete; it is not an empty vote. An
empty bank writes two validated synthetic empty plans and makes no model call.
Applied families use a deterministic shared semantic name core when one is safe,
otherwise a fixed generic assembly-kind name, and retain `assembly_kind` and
`graph_components`. The firewall preserves the complete proposal multiset.

## Frozen-inventory prompt-bound matching

After both partition stages validate, freeze accepted cluster identities, names,
members, granularity, evidence, attributes, and presence. Create a semantic
registry containing only `registry_id`, `name`, `description`, and `entity_type`.
Do not include prompt-bound detector status or boxes.

One isolated matcher sees the same-shot frames, semantic registry, and every
accepted frozen node. It classifies each node exactly once:

- `bound`: the visual node is the same physical instance as exactly one registry
  entry;
- `unbound`: it is not any registry instance;
- `ambiguous`: same-instance membership cannot be resolved visually.

A spatial or interaction relation to a registry entity does not make a node
bound. The matcher cannot add a node, rescan for missing entities, merge or split
nodes, change names or granularity, or overrule existence. Ambiguous matches stay
in the audit and are excluded from the unbound projection.

## Decision and stopping rules

- Inventory `accept` means visual existence, resolved physical identity, graph
  salience, and valid entity scope; graph partition may still be deferred.
- Inventory `reject` means evidence contradicts the proposal, it is a same-scope
  duplicate, it violates scope, or it is a supported mutually exclusive group
  alternative retained for later family resolution.
- Inventory `abstain` means existence, boundary, salience, or physical identity
  remains unresolved, including a failed one-source unanimity gate.
- Absence from another detector is not negative visual evidence. Agreement labels
  describe repeatability only.
- Record model and CLI versions, protocol and component versions, frame paths and
  IDs, token usage, runtime, hashes, every failure, and every retry.
- Retry each failed detector, verifier, matcher, group/member planner, or
  accepted-only planner at most once. Preserve the same frozen frames, original
  proposal universe, required target scopes, schema, and evidence policy.
  Detector, matcher, group/member, and accepted-only planner retries reuse their
  role prompt. A verifier retry may append the recorded failure feedback.
  Adjudicator revision permits at most one same-thread contract/accounting repair
  with the recorded failure and diagnostics, under the existing exact-scope and
  split constraints. These retries do not create independent evidence votes.
  Do not change the detector denominator or silently skip a required role.
- Stop successfully only when four ledgers with valid private coverage audits
  exist, every proposal remains
  accounted for exactly once, all required verifiers and the selected
  post-verification policy are complete, both partition firewalls validate or deterministically
  skip, accepted final nodes have exhaustive presence, and the matcher covers
  exactly those nodes.

## Validation plan before benchmark use

Treat this as a proposed protocol until calibrated. Measure human-labeled entity
precision and recall, repeated-run stability, false change on controlled matched
shots, sensitivity to controlled add/remove edits, abstention coverage, grounding
quality, token cost, and wall time. Never encode a development example's expected
entity difference in prompts or skills.

## External own-source residual closure

After the four valid initial ledgers, the current CLI runs up to three residual rounds per detector, with a configurable zero-to-four round budget. Each fresh isolated call sees only that source's own ledger, the detector-only policy and original frames. Delta-only additions require unused local IDs, visible boundary evidence and separation from nearby existing candidates. No original proposal may be changed, removed or repeated. Audit every frame times nine cells, first/last edges and both temporal reveal and departure for every adjacent pair. Validate candidate presence and novelty evidence strictly. Per-round schemas fix known paths, frame IDs, existing IDs and role identifiers. Private cell cross-index visibility disagreements are diagnostic; they never change candidate evidence or trigger visual resampling. A failed call retries once identically; an empty delta closes a source. Failed retries make the shot incomplete. Valid additions at the round limit instead record open coverage and budget exhaustion, and all four valid extended ledgers proceed to adjudication. An empty delta is not proof of completeness, and lack of one is not evidence of invalid candidates. The extended ledgers retain four detector identities; repeated rounds never count as independent votes. Preserve original ledgers, per-round inputs/deltas/prompts/attempts, extended ledgers, and source/stage accounting. None of this private closure metadata is supplied downstream.
