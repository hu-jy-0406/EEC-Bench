# Isolated physical identity verification v0.6

Review exactly the supplied targets in this one shot. Inspect all ordered original
frames. Proposal names, boxes and locations are fallible hints. Independently
locate the actual content before judging. Do not discover additional candidates,
infer provenance, count source votes, consult another role's verdict, or seek a
desired final entity set. Category uncertainty is independent of physical scope.

Return the supplied base `protocol_version`, `schema_version` equal to
`physical_identity_review_v0.6`, the given shot and verifier IDs, exactly one review
per target, and warnings. Unresolved visual judgments are valid answers.

For every review and proposed physical unit record:

- `existence_judgment`: `confirmed`, `rejected`, or `uncertain`.
- `salience_judgment`: `graph_worthy`, `background_integrated`, or `ambiguous`.
- `proposal_scope_judgment`: `resolved_single_scope`, `mixed_scope`, or `unresolved`.
  Resolved means all proposal IDs in that scope identify the same complete physical
  content. A coherent object inside a mixed larger claim does not resolve the claim.
- `category_resolution`: `resolved`, `subtype_unresolved`, or `category_unresolved`.
  Unknown category/subtype does not negate a clearly substantiated physical object.

Graph worthiness follows physical entity scope, not narrative prominence,
foreground position, movement, or ease of removal. A clearly bounded functional
architectural or mounted fixture may be graph-worthy even when static and fixed
to its surroundings. Assess its complete visible boundary and coherent scope;
being attached does not alone make it background. `background_integrated` means
an undifferentiated substrate or a dependent constituent whose separately claimed
node is excluded by the entity-scope policy. State that concrete scope reason in
the evidence. An unresolved visual patch still needs physical evidence; a useful
category name does not make it graph-worthy. Keep existence and salience judgments
separate when reporting a real object that is ineligible as a separate node.

Every item in `evidence` or `observed_independence_evidence` includes `frame_id`,
`coarse_locator`, legacy `support_quality`, `anonymous_proposal_ids`, `cue_type`,
and `observation`. The latter describes the actual visible cue and limitations,
not a confidence rating. The proposal IDs identify precisely the scope supported
by that observation. Do not bind a parent's observation to a child by changing IDs.
When the supplied prompt requires exact original-scope coverage, include at least
one valid exact-own observation for each such scope. Weak or unresolved evidence
is valid; a pair-union observation is separate and cannot be relabeled to fill this
requirement. Other targets retain their existing evidence requirements. Coverage
does not require a positive judgment or certify visual truth.

Allowed cue types and their meanings:

- `physical_boundary`: a coherent complete independent unit with its own boundary.
- `direct_interaction`: handling, motion, or use directly establishes a physical unit.
- `temporal_continuity`: visible continuity establishes the same claimed unit across frames.
- `same_instance_continuity`: positive evidence aligns both complete compared claims
  to one physical content. Category similarity or lack of separation is insufficient.
- `simultaneous_separation`: both compared units have independently localized,
  distinct physical boundaries in the cited frame. Give both locations.
- `independent_interaction_or_trajectory`: direct handling or different observed
  motion establishes different identities for both complete compared scopes; for
  example one small transparent unit is lifted while the other stays localized.
  An incomplete edge is permissible when this direct cue resolves identity.
  Ordinary camera motion, two names for one trajectory, or presumed semantic
  function cannot establish distinctness.
- `integrated_component`: visible attachment/integration supports a component scope.
- `non_entity`: a visible artifact or nonphysical pattern explains the candidate.
- `unresolved`: available pixels leave the physical scope or correspondence open.
- `category_only`: evidence informs taxonomy only, not physical existence or identity.

In `identity_comparisons`, cover each supplied challenge partner exactly once.
Other supplied partners may also be compared. Each entry has `other_cluster_id`,
`judgment`, `scope_relation`, and zero-based `evidence_indices` into this review's
`evidence`. Judgment is `confirmed_same_scope`, `confirmed_distinct`, or `unresolved`.
Scope relation is `comparable`, `whole_part`, `group_member`, or `unresolved`.
Determine it from complete asserted physical content. Image-plane enclosure,
support or proximity alone establishes neither whole-part nor group-member. A
fixture-only claim excludes stored or supported contents; a contents-only claim
excludes the fixture. "Only" is about asserted content, not a category shortcut;
do not remove integral components or rewrite an explicit assembly. Whole-part
requires a claimed whole and its actual constituent; group-member requires a
claimed group containing that member. Independently bounded objects can have
comparable scopes while one supports or encloses the other. Comparable scope does
not prove distinctness; retain the exact-union evidence requirements. If the
relation itself is uncertain, use `scope_relation=unresolved`; do not use a known
relation enum to evade unresolved identity. Graph composition is separate.
Only comparable scopes can receive a confirmed judgment. Whole-part and group-member
entries use unresolved identity and never imply a same-scope alias. A confirmed
same-scope comparison needs `same_instance_continuity`; confirmed distinct needs
`simultaneous_separation` or `independent_interaction_or_trajectory`. Referenced evidence must cover exactly the union of
both complete compared proposal scopes. Unresolved comparisons may have no evidence
indices and do not become aliases. `same_instance_with_cluster_ids` must equal
exactly the partners with comparable `confirmed_same_scope` judgments.

Keep `graph_partition_judgment`, `same_graph_node_with_cluster_ids`, and
`observed_independence_evidence` separate from physical identity. Sharing a graph
node does not make members the same physical instance. Use `keep_as_separate_node`,
`merge_into_compact_composite`, or `uncertain`; a merge nomination requires the
partner IDs. An independence observation cannot simultaneously nominate a merge.
These are local advisory answers only; do not execute downstream graph partition.

For a supplied intra-cluster divergent-footprint challenge, inspect the original
pixels. Boxes trigger review and do not prove multiple instances. Use
`intra_cluster_split_judgment` as `keep_single_physical_instance`,
`split_into_multiple_physical_instances`, or `uncertain`; use `not_reviewed` when
there is no such challenge. A split requires at least two confirmed, graph-worthy,
resolved units. `proposed_physical_units` must partition every original target
proposal ID exactly once. Preserve each proposal's original claimed content; do not
retarget an unsupported proposal to another visible object. Each unit needs its
own exact-scope physical evidence. Supply every unit pair in
`pairwise_physical_separation_evidence`, with unit IDs, original frame ID, distinct
coarse locators, and the legacy moderate/strong support quality. When not proposing
a split, both split arrays must be empty. Do not invent units to complete a split.

When the request explicitly enables `single_survivor_scope_retention_v0.1`,
follow the additional [scope-retention protocol](scope-retention-protocol.md)
and its extended schema. Keep the complete original reviews and split answers;
the separate request may propose one supported subset and an unresolved
complement. An empty request array is valid. The complement is not another
confirmed physical unit, and no request creates acceptance by itself.

Physical boundaries can be resolved for a static object without an observed action.
A cropped object can be confirmed using sufficient coherent boundary or direct
interaction evidence. A textured patch with no such evidence remains uncertain
even if given a specific noun. Report the limitation rather than forcing certainty.
