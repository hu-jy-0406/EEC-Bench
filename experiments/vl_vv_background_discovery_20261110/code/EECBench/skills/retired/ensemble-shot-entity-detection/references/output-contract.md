# Output and artifact contract

## Directory layout

Use a new run directory and preserve intermediate evidence:

```text
RUN_DIR/
  run_manifest.json
  input_bundle/
    shot_manifest.json
    prompt_bound_registry.json
    prompt_bound_registry_semantic.json
    frame_*.jpg
  detector_runs/
    detector_1.json
    detector_2.json
    detector_3.json
    detector_4.json
    coverage_diagnostics.private.json
  codex_attempts/
    adjudicator_initial.json                # immutable raw model response
    adjudicator_initial.events.jsonl
  adjudication/
    anonymized_candidates.json
    adjudicator_initial.json
    initial_context_projection.json        # pre-pending proof ledger, raw preserved
    initial_context_quarantine.json        # complete context and old->new index map
    initial_context_projection_audit.json  # independent reconstruction
    initial_context_review_dispositions.json # both complete scope reviews and lineage
    initial_identity_review_preparation.json # physical mode; raw/derived hashes
    pending_identity_review_dispositions.json # physical gate scope accounting
    verification_targets.json
    intra_cluster_divergent_footprint_challenges.json
    verifier_1.json                         # when targets exist
    verifier_2.json                         # when targets exist
    intra_cluster_split_consensus.json
    intra_cluster_split_revision_firewall.json
    adjudicator_pre_granularity.json
    granularity_group_member_input.json
    granularity_group_member_plan_1.json
    granularity_group_member_plan_2.json
    granularity_group_member_resolutions_1.source_blind.json
    granularity_group_member_resolutions_2.source_blind.json
    granularity_group_member_consensus.json
    granularity_group_member_application_plan.json
    granularity_group_member_resolutions.source_blind.json
    granularity_group_member_firewall.json
    granularity_group_member_failure.json       # only after planner failure
    adjudicator_post_group_member.json       # provisional, never final inventory
    accepted_compact_assembly_candidate_bank.json
    accepted_compact_assembly_candidate_bank.private.json
    accepted_compact_assembly_input.json
    accepted_compact_assembly_plan_1.json
    accepted_compact_assembly_plan_2.json
    accepted_compact_assembly_resolutions.json
    accepted_compact_assembly_firewall.json
    accepted_compact_assembly_failure.json  # only after planner failure
    partition_gate_handoff.json
    adjudicator_decisions.json
    source_map.json
    granularity_group_member_panel_positions.private.json
    granularity_group_member_resolution_panel_audit.private.json
    single_detector_consensus_gate.json
    nonmajority_generic_identity_gate.private.json
    ensemble_audit.json
  matching/
    frozen_inventory.json
    prompt_bound_matches.json
  final_semantics.json
```

Raw detector ledgers are immutable. The complete `source_map.json`, including
detector-local IDs, is written only after graph partition and prompt-bound
matching have frozen. A derived fixed panel membership view is present earlier in
`anonymized_candidates.json` for the initial inventory adjudicator only.

In physical mode, `initial_identity_pending_v0.2` may derive an unsupported but
otherwise structurally valid comparable identity assertion as `unresolved` when
references are valid and nonempty but lack the required exact-union witness, or
when references are valid empty arrays. Malformed types, invalid indices, unknown
partners, ownership errors and non-comparable confirmed claims remain fatal. It changes no
evidence, existence judgment, proposal ownership or graph scope. The immutable
raw response stays in `codex_attempts`; the derived ledger is separately validated
and saved in `adjudication`. Its failed raw semantic contract remains a failed
attempt with `recovery_status=pending_identity_review`, known call usage and
separate raw/derived validity flags; there is no extra model call or retry hidden
by this recovery. Preserve the first preparation audit, exact pair scopes, JSON
pointers and both artifact hashes. Reapplying preparation to the derived ledger
cannot discharge the first audit's obligations.

Each pending pair forces both complete endpoint scopes into both independent
verifiers through neutral questions. The private conversion reason and original
judgment are not verifier inputs. After the physical gate and before graph
partition, disposition accounting follows proposal lineage and distinguishes
contract resolution from unresolved rejection/abstention/coverage risk. Neither
successful execution nor a resolved typed contract is a pixel-accuracy claim.
Every valid initial-declared pair also enters both independent verifiers as a
neutral question over both complete endpoint scopes, including rejected or
deferred endpoints. This creates no positive evidence or automatic promotion.

`initial_context_then_pending_v0.2` separates two initial-only operations:
raw response -> context projection -> pending-assertion derived ledger. The
context policy is `initial_context_quarantine_v0.1`; it never changes the
final/verifier schemas. A context observation must contain the full own scope
and equal the union of at least three complete, disjoint initial scopes. Only
unreferenced items or unresolved whole_part/group_member references qualify.
Positive references, other relations, partial scopes, unknown IDs, illegal
indices, or nonempty initial revision resolutions remain fatal. Classification
uses the raw partition once and includes every qualifying item, even when its
IDs happen to be allowed by existing partner declarations. Own and binary
evidence remains governed by the existing contract, without a new exception.

The pure quarantine sidecar records full original observations and hashes,
source JSON pointers, complete owners, all original reference rows and their
projected indices. Each cluster has a complete ordered old-index-to-new-index
map with null for quarantined context. All retained evidence stays byte-value
identical; only already-unresolved qualifying references lose those indices.
Do not copy evidence, create a comparison, enlarge proposal IDs, alter decisions
or ownership, or fill missing proof. The independent projection audit reconstructs
all changes from raw data; the original pending preparer then validates its
separate derived result. Its recorded input path points to the context projection,
not directly to the model response. Record actual raw strict validity separately:
quarantining an otherwise legal context does not itself make a paid call fail.
An actually invalid raw response retains its failure and usage even when derived
preparation allows review; no additional model invocation is implied.

Route all context owners to both complete neutral verifier reviews, preserving
existing pair questions without creating pairs from context co-occurrence.
Private sidecar, raw judgments and routing reasons never enter verifier inputs.
The resumed revision receives only the current proof ledger plus a general
provenance instruction. Before graph partition, independently audit complete
review coverage and every original proposal's final disposition. Missing/partial
or duplicate-verifier coverage makes execution incomplete. Reject/abstain or
changed scope stays visible as coverage risk, never automatic acceptance. Sidecar
observations supply neither exact-scope positive proof nor independent evidence.
Before accepting a verifier report, the additional context coverage check requires
at least one valid exact-own observation for every already forced original scope.
Other targets retain their existing evidence requirements. Weak or unresolved
observations are valid; pair-union evidence is separate and must not be relabeled.
Failure uses the existing one-repair allowance for that verifier, retaining its
successful peer; persistent failure stops before revision. The final coverage
audit still runs and coverage does not establish pixel accuracy.

## Manifest and input boundaries

`run_manifest.json` records protocol and component versions, status, timestamps,
the one allowed shot, frame and input hashes, model and CLI versions, the fixed
four-detector homogeneous method, worker concurrency, role-specific input
boundaries, every retry, prompt/schema/stage-source hashes, runtimes, token usage,
and artifact hashes. The detector-only policy version, path, and hash are recorded
separately from the full downstream Skill hashes, together with the facts that
the full downstream Skill and private coverage audits are not detector/downstream
cross-role inputs respectively. A private deterministic detector-coverage
diagnostic records missing spatial/stratum cross-index memberships without
changing ledger validity, evidence, support, downstream inputs, or retry status.
The `nonmajority_generic_identity_gate` manifest block records only its version,
reviewed and abstained counts, frozen detector denominator, non-majority rule, and
the fact that its source-derived details were supplied to no model. Its detailed
private artifact is written only after prompt-bound matching has frozen.

The `granularity_family` manifest block records `planner_count=2`, valid and
failed planner indices, invocation and synthetic-empty-plan counts, per-planner
family counts, the exact-consensus requirement, consensus/applied counts, and
missing-structure, partition-disagreement, and overlap-conflict counts. Every
attempt record includes `planner_index`; separate ephemeral workdirs and
identical role inputs are explicit isolation facts. It also marks its application
as a provisional candidate-scope audit that cannot become final without the
accepted-only second gate. `partition_gate_handoff.json` hashes the frozen
pre-group baseline, provisional view, second-gate status, and final decision
content so the authority boundary is explicit in the artifacts.

The `intra_cluster_spatial_split_audit` block records review-only challenge
count, exact two-verifier consensus count, observed revision splits, and explicit
facts that detector source/count information was unused, boxes did not act, and
the exact proposal-partition firewall was enforced.

Role boundaries are mandatory:

- detectors receive only same-shot frames, frame mapping, schema, and the frozen
  standalone detector-only policy; they do not receive the full downstream Skill;
- the inventory adjudicator additionally receives the panelized anonymous union
  and review-only box challenges, but no registry, detector-local IDs,
  self-confidence, or source quality information;
- targeted verifiers receive selected anonymous cluster views and same-shot
  frames, but no panel membership, counts, registry, or source map. Their compact
  proposal view preserves IDs, proposed names, granularity, coarse locators and
  every per-frame presence status and box. Prior adjudicator verdicts/reasons,
  confidence, uncertainty flags and duplicate descriptions are absent;
- both group/member planners receive byte-identical source-blind anonymous
  proposals, a filtered post-gates baseline, and same-shot frames in separate
  ephemeral workdirs;
- accepted-only judges receive the public mandatory candidate bank, accepted
  resolved box-free cluster semantics from the unchanged pre-group frozen
  baseline, evidence, presence, and same-shot frames;
- the matcher receives `prompt_bound_registry_semantic.json`, the final frozen
  accepted inventory view, and same-shot frames;
- no model receives prompt-bound detector status or boxes, the full private
  source map, detector-local IDs, or another shot.

The CLI sandbox does not enforce a filesystem read allowlist, so these are
validated procedural boundaries. Missing required outputs after the role's one
configured retry prevent successful final semantics. Retry frames, original
proposal universe, required target scopes, schema, and evidence policy stay
fixed. Detector, matcher, group/member, and accepted-only planner retries reuse
their role prompt; verifier retries may append recorded failure feedback.
Adjudicator revision permits one bounded same-thread contract/accounting repair
with the recorded failure and diagnostics, retaining the existing exact-scope
and split constraints. Preserve each attempt's actual prompt and accounting;
retries never count as independent evidence votes.

## Detector ledger

Each detector conforms to
`schemas/codex_entity_detector_ledger_v0.8.schema.json` and returns protocol
`single_shot_inventory_first_boxed_granularity_v0.5`. Each proposal contains
identity and naming fields, attributes, representative `evidence_frame_ids`,
coarse locators, uncalibrated self-confidence, uncertainty, and
`frame_presence`. There is no per-ledger search-variant output field; all four
calls use the same method by orchestration contract.

`frame_presence` contains every supplied frame ID exactly once. Every entry has a
status from `visible`, `absent`, `occluded`, or `uncertain` and a nonempty visual
reason or locator. A visible entry has a valid tight
`bbox_xyxy_normalized`; every other status has
`bbox_xyxy_normalized=null`. Representative evidence is nonempty but need not
list every visible frame.

All four prompts use the same method. Only detector and local IDs differ.
Self-confidence is removed from every downstream model view and is never
averaged.

Every ledger also carries a mandatory private `coverage_audit`. Its
`reviewed_frame_ids` exactly equals the chronological input frame list;
`spatial_cells` contains each of the nine fixed image-plane cells exactly once;
`content_strata` contains each of the five fixed strata exactly once; and
`temporal_reveal_checks` contains every adjacent ordered frame pair exactly once.
Every referenced local ID exists and is unique within its list. Spatial-cell and
content-stratum entity lists are best-effort private cross-indexes: missing a
final entity is recorded as a nonfatal deterministic diagnostic and does not
invalidate the semantic ledger. Temporal `added_local_ids` are final entities
newly revealed or materially confirmed by that adjacent-frame comparison; they
are independent of the required-but-empty-allowed pass-2-only
`residual_added_local_ids`. Empty represented-ID arrays are allowed and impose no
discovery quota.

The raw detector ledger preserves this audit, but anonymization copies only
proposal fields. `coverage_audit` must not appear in
`anonymized_candidates.json`, the private source map, any adjudicator/verifier/
partition/matcher prompt, agreement counts, confidence, evidence, or votes.

## Panelized anonymous union

Flatten the four ledgers, replace source/local IDs with opaque proposal IDs, and
deterministically shuffle the records using the manifest seed. Retain proposal
semantics and `frame_presence`. Also emit exactly four `detector_panels`, each
with a fixed `panel_id` and the opaque proposal IDs from that detector. The panels
contain no local IDs, score, specialization, ordering preference, or quality
rank.

Compute review-only trajectory coverage within each private detector source and
attach anonymous `box_redundancy_challenges` containing target and covering
proposal IDs, framewise symmetric tight-box IoU, temporal match ratio, and fixed
thresholds. Containment or intersection-over-target is not the spatial metric.
No challenge automatically removes a proposal.

Only the initial inventory adjudicator sees `detector_panels`. Panel agreement is
a repeatability and partition-pattern diagnostic, never calibrated probability or
visual proof. Later model roles receive views that strip panels and
provenance-derived diagnostics.

## Physical inventory adjudication and verification

The schema paths below describe legacy identity review. With
`identity_review_policy=physical_v0.6`, use adjudication and verification schemas
v0.6, retaining the base protocol version and adding
`schema_version=physical_identity_review_v0.6`. They additionally preserve
physical existence/salience, proposal scope, category certainty, explicit
three-state identity comparisons and scope-bound direct evidence. A revision
resolution identifies the disputed axis, initial targets and its complete
containing final cluster's proposal set, and
indices into its own direct observations. `same_instance_with_cluster_ids`
equals only confirmed same-scope comparisons, never possible aliases. These
fields are validated before partition; the new physical identity gate audit
is saved as `adjudication/physical_identity_gate.json`. Both old post-verification
gates are marked unapplied in this mode. Old reports are never silently upgraded.

Every adjudicator evidence item, including unresolved observations in rejected or
abstained clusters, is locally limited to its owner's proposal IDs plus IDs from
partners in that owner's own identity comparisons. Reverse declarations do not
create local links. This is a maximum allowance, not a requirement that every
weak observation cover the whole owner. Do not copy evidence, invent a partner or
relabel a scope. The separately authenticated initial context projection is the
only narrow broad-context exception. Eligible reverse-owner union proof remains
usable by the existing undirected gate without a new local link.

Canonical resolution ownership is the complete containing final cluster on every
axis. For retained-distinct identity, referenced evidence covers the full pair
union while the resolution owner remains its endpoint. A merged final cluster's
own scope can itself be a union. The initial ledger always uses the canonical
schema. Explicit `revision_output_policy=implicit_owner_wire_v0.1` selects
`schemas/codex_entity_revision_wire_v0.1.schema.json` for revision and its original
one same-thread repair. This wire omits only resolution-row owner arrays; cluster
and observation proposal arrays remain model outputs, as do resolution axes,
initial target IDs and local evidence indices. Preserve raw wire and usage, then
write separate canonical materialization and pointer-audit artifacts. Validate
complete ownership, both schemas and the physical extension before the unchanged
base, deferred-partition, exact-split and physical gates. No evidence is supplied
by materialization; failed paid attempts remain in accounting.

The first-revision obligation preview is partial and refers to current scopes.
Complete inputs and review obligations remain in effect. Absence from the preview
is not clearance; scope changes require reassessing obligations, and checklist
addresses are not indices into the returned evidence ledger.

In legacy mode, initial, revised, and post-partition ledgers conform to
`schemas/codex_entity_adjudication_v0.5.schema.json`. Every anonymous proposal
appears in exactly one nonempty cluster. The initial adjudicator and its revision
may merge same-content aliases at the same candidate graph scope, but cannot add
an entity or coarsen physically distinct anchors to choose a graph partition.

With physical review v0.6, `adjudicator_pre_granularity.json` is the immutable
physical-inventory authority. Post-partition decisions are a derived graph
ledger: a synthetic graph node is not a new physical same-instance assertion and
is not labeled as a v0.6 physical adjudication. The separately validated
`graph_physical_anchor_lineage.json` records the exact physical anchor IDs,
proposal sets and complete-record hashes behind every accepted graph node.
Every accepted physical anchor must appear exactly once; partial anchors,
rejected/abstained proposal promotion, omissions and duplicates fail. Existing
frozen-component audits retain the original typed physical evidence. No synthetic
same-instance or category certainty is invented during graph coarsening.

An accepted physical anchor requires nonempty same-shot evidence, resolved
identity, graph salience, valid scope, a complete final entity, and exhaustive
cluster-level presence. Rejected and abstained clusters have `final_entity=null`
and remain auditable. No prompt-bound field appears in the adjudication schema.

When supported group and member proposals cover the same content, accepted member
anchors and the rejected group alternative remain separate until the family
stage. The rejected group alternative carries `group_member_conflict` only when
its rejection prevents double counting. Accepted anchors without an explicit
group alternative may carry `possible_compact_assembly_partition`. The revision
must preserve these deferred-partition structures.

In legacy mode, weak-target reports conform to
`schemas/codex_entity_verification_v0.5.schema.json`, cover exactly all requested
clusters, and refer only to existing cluster IDs. Each review reports physical
identity in `same_instance_with_cluster_ids`, independently from advisory graph
partition in `graph_partition_judgment` and
`same_graph_node_with_cluster_ids`. A confirmed existence judgment requires
same-shot evidence. Reports cannot add candidates or directly decide the ledger.

Every review also contains required `intra_cluster_split_judgment`,
`proposed_physical_units`, and `pairwise_physical_separation_evidence` fields.
Targets without an intra-cluster footprint challenge use `not_reviewed` and empty
arrays. A challenged split partitions all target proposal IDs exactly once into
at least two units; every unit is confirmed and graph-worthy with its own visual
evidence, and every unit pair has direct strong or moderate same-frame boundary
evidence. Non-split outcomes use empty arrays. Two reports authorize only their
exact common normalized proposal partition. The persistent adjudicator still
must confirm it from pixels, and the deterministic revision firewall permits no
other split.

## Single-detector gate

This section applies only to `identity_review_policy=legacy`.

The gate consumes the revised ledger, initial target mapping, both verifier
reports, and the private source map. For each accepted cluster supported by one
distinct detector, map its proposals to all intersecting initial verification
targets. Keep `accept` only if both verifier reports completely cover every
relevant target and all reviews simultaneously confirm existence and graph
worthiness. Otherwise emit `abstain`, `identity_status=ambiguous`,
`final_entity=null`, and `single_detector_consensus_gate_not_unanimous`.

If revision split an initial target, an accepted one-source child additionally
must match an exact consensus proposal-set unit confirmed by both verifiers.
Intersection with a larger cluster-level review never counts as unit-level
confirmation.

`single_detector_consensus_gate.json` records detector support, mapped target IDs,
per-verifier judgments, unanimity, and the deterministic result. The gate does not
silently delete an entity or convert uncertainty into rejection.

## Non-majority generic-identity evidence gate

This section applies only to `identity_review_policy=legacy`; its configured
`all_support` variant uses the same evidence predicates at every source count.

The second post-verification gate consumes the revised ledger, exact split
consensus, both verifier reports, private source map, and the explicit complete
detector roster. It reviews accepted clusters without a strict detector majority.
It abstains only when both final adjudicated names have a narrow generic
placeholder head, normalized uncertainty flags explicitly leave physical
identity/category/subtype unresolved, and the complete relevant verifier record
has neither unanimous strong confirmation nor unanimous supported direct
independence evidence. A concrete final category remains untouched regardless of
low support, and support alone never changes a decision.

For revised clusters intersecting multiple initial targets, every expected
verifier must rescue every target. Exact split children use only matching
verifier-local physical-unit evidence; parent evidence is ineligible. A fired gate
sets `decision=abstain`, `identity_status=ambiguous`, and `final_entity=null`, adds
`nonmajority_generic_identity_evidence_gate`, and retains all prior evidence.

`nonmajority_generic_identity_gate.private.json` records the versioned placeholder
lexicon and uncertainty matcher, frozen denominator, mapped targets, per-verifier
evidence qualities, rescue predicates, and result. It is written after matching,
contains source-derived support, is marked private, and is never supplied to a
model or used by a partition planner.

## Group/member family plan and firewall

Both `granularity_group_member_plan_1.json` and
`granularity_group_member_plan_2.json` conform to
`schemas/codex_granularity_family_plan_v0.3.schema.json` with protocol
`single_shot_granularity_family_plan_v0.3`. The two isolated planners receive
byte-identical model views containing the post-gate baseline and anonymous
proposals but no panels, source mappings, counts, provenance-derived diagnostics,
or output from the other planner.

Each plan's `reviewed_group_alternative_cluster_ids` is exactly the set of
rejected baseline clusters marked `group_member_conflict`. Every reviewed ID
appears exactly once, either as a non-anchor cluster in one family or as one
`excluded_group_alternatives` record. Each exclusion contains a typed reason,
all accepted resolved `candidate_member_anchor_cluster_ids` visually covered by
the rejected group claim, and an
`independent_context_anchor_cluster_ids` subset. Under
`zero_supported_member_anchor_exclusion_v0.1`, candidate anchors may be empty
for an unresolvable visual scope or an explicit
`insufficient_supported_member_anchors` exclusion when the planner cannot support
any eligible accepted/resolved anchor as covered by the group claim. A resolvable
group with zero eligible anchors is a conservative no-op, not a format error and
not proof of absent physical content. Do not invent anchors or relabel a resolvable
scope as unclear to satisfy the contract. When covered eligible anchors are
supported, list all of them; the same insufficient-anchors reason may also retain
a nonempty mapping that cannot support a valid family. Other empty-list reason
guards remain unchanged. An excluded group cannot also appear in a family and
cannot recover rejected/abstained content or authorize a merge. The application
audit records each planner's zero-anchor report under
`empty_supported_anchor_exclusions` with `unresolved_coverage_risk=true`, even if
only one planner makes that report; it does not certify member absence or pixel
truth. A nonempty independent-context subset uses
`contains_independently_graph_worthy_context`. The deterministic application plan
carries the same coverage fields and records any otherwise valid but unapplied
alternative as `not_selected_by_exact_consensus`.

Each family contains at least two accepted resolved member anchors and at least
one rejected supported group alternative marked `group_member_conflict`. Content
units anchor every accepted family cluster exactly once. Proposal roles cover the
whole family scope exactly once, every group role covers all units, every member
role covers one unit, all group same-content evidence comes from frames where all
units are visible, and families are disjoint. Abstained content and large-host
scope are invalid.

A supported bounded homogeneous collection remains a valid group candidate when
member enumeration or observation-conditioned subdivision is unstable under
view, crop, occlusion, or scale. Its family scope must exclude the large
host/support and any independently graph-worthy context.

Each plan records only four typed shot-observed independence witnesses: separate
handling/use, detachment/standalone state, relative motion, and independent
trajectory. The deterministic resolution is group when no witness exists,
members when every pairwise boundary has a witness, and frozen-baseline members
when evidence covers only some boundaries.

Structurally valid group-proposal/member-track conflicts yield private
`group_witness_invalid` records with exact proposal, member and frame evidence,
rather than failed planner calls. They invalidate that group witness in the
explicit stage and do not create member-to-member prohibitions. The final stage
requires independent, complete anchor and reference localization. An unresolved
candidate cannot create an overlap conflict for an otherwise eligible subset.
Invalid scope, IDs, witnesses, missing planners and forged resolutions still fail.

`granularity_group_member_consensus.json` normalizes each family by the complete
frozen baseline-cluster scope, complete proposal scope, and accepted member-anchor
set. Planner-local IDs and evidence wording do not affect identity. The
provisional application plan contains a family only when both valid plans contain
exactly one identical normalized family and both per-plan resolutions select `group`. Exact
`members` agreement, omission, structural or partition disagreement, duplicate
signatures, and overlapping or nested cross-plan components leave the baseline
unchanged. A planner that fails both identical-input attempts emits
`granularity_group_member_failure.json` and makes the shot incomplete. An
baseline with no marked rejected group alternative emits two validated synthetic
empty plans with zero model calls; any marked alternative requires both planner
reviews.

Detector panel positions are added only to post-matcher private audit over
`granularity_group_member_application_plan.json`; removing those audit fields
must leave the source-blind application resolution unchanged.

The firewall preserves proposal accounting and every nonfamily cluster exactly.
A provisionally applied group receives a deterministic name derived from the
already supplied group alternative and preserves accepted member semantics in
`graph_components`. This assembled view exists for audit only: it never replaces
the frozen pre-group baseline, never feeds matching, and never has final graph-
partition authority.

## Accepted-only compact-assembly plans and firewall

Apply the shared holding/container scope rule in `protocol.md` to the exact
candidate. `holder_with_held_or_carried_item` includes visibly established actor
holding and inanimate holder/independent-load relations, even when stationary;
it is not inferred from a holder name, physical distinctness or containment alone,
nor cleared by absence of observed handling.
`temporary_storage_or_transport_payload` requires actual temporary packing,
loading or transport evidence, not merely possible later movement. A
`small_container_contents_unit` needs positive complete-container-plus-content
organization with `same_small_container_functional_unit` evidence. Merely being
small, inside, supported or static, or selecting that kind, is insufficient.
Visible structure may directly support the unit without an observed operation.
When only passive same-category fixture organization is established, the complete
contents-only collection excludes that fixture; changing kind cannot absorb it.
Existing `description` fields explain these distinctions. `absent` still has
empty evidence; `present/uncertain` still cites original-frame evidence. Any
present/uncertain protection or observed/uncertain member independence blocks
coarsening, including an otherwise positively supported functional unit. External
carrying of a supported whole does not itself prove an internal payload relation.

A passive homogeneous collection has one canonical scope: all visible passive contents of one physical category within one clearly bounded storage or display fixture, across its internal shelves, bays, rows or slots. The fixture is excluded from the content node. Internal dividers, crop, color differences, or separately localizable subgroups alone do not split this collection. Different fixtures, individually framed artwork or separately mounted complete display fixtures, heterogeneous neighbors, and objects separately handled or used during the shot remain separate. Same-role covering or control panels serving one bounded fixture use one whole-array scope, excluding that fixture, unless directly observed independent handling, use or motion warrants a split. Apply these scopes at discovery and final partition regardless of whether proposals initially used whole collections or subdivisions. A shared unbounded surface alone never establishes this organization.

Every family has `collection_scope_review`: null for existing kinds, or for `passive_homogeneous_collection` an object containing `fixture_anchor_cluster_id`, `content_category`, `complete_fixture_content_scope`, `passive_unhandled_content`, `fixture_excluded`, `heterogeneous_neighbors_excluded`, `independently_framed_subjects_excluded`, `evidence` and `description`. All five checks are true; two evidence frames show the external accepted fixture and every member. Both judges must agree on fixture identity. Cohesion kind is `same_fixture_bounded_passive_homogeneous_content`.

Each planner output conforms to
`schemas/codex_accepted_compact_assembly_plan_v0.5.schema.json` with protocol
`single_shot_accepted_compact_assembly_plan_v0.5`. Both isolated judges receive
identical same-shot inputs. `reviewed_accepted_cluster_ids` covers every supplied
accepted resolved cluster exactly once and `reviewed_candidate_ids` covers every
mandatory bank candidate exactly once.

The model view excludes proposal membership, detector boxes, rejected and
abstained clusters, confidence, uncertainty flags, panels, counts, source maps,
and provenance-derived diagnostics. The public candidate-bank artifact contains
only its protocol, shot ID, deterministic candidate IDs, exact peer-anchor IDs,
and context-anchor IDs. Its private companion records derivation for audit but is
not a model input. Candidate bank protocol v0.3 adds exact-scope verifier-declared
partner member maps: each initial target's full proposal set must identify one
unique accepted resolved baseline anchor. Normalize repeated partner IDs, reject
self references, and drop an entire nomination on missing or changed scope.
Store verifier declaration provenance only in the private bank audit. Never
form transitive closures or grant a nomination coarsening authority.
Explicit-stage member maps define candidate closure directly
after mapped context removal. Only otherwise unscoped marked accepted anchors use
normalized proposal head/type overlap for conservative semantic cohorting;
frequency, panels, counts, and boxes are never used. Both the bank and the judge
view are built against the unchanged pre-group frozen baseline, so a provisional
explicit-stage merge cannot hide its constituent anchors.

Each candidate appears exactly once as either a family with the exact bank anchor
set or a structured exclusion. A judge cannot freely create, omit, subset, or
expand a family.

For each family:

- content units map every anchor exactly once and cite frames where that anchor is
  visible;
- `common_visible_frame_ids` exactly equals the intersection of visible frames
  across all anchors and contains at least two frames;
- under `all_candidate_common_visible_reference_frames_v0.1`, reference
  observations and each of the two member/reference relations cover that entire
  intersection exactly once, including frames outside the witness's positive
  citation subset. Nonvisible references use the existing `uncertain` status,
  null boxes and an explicit limitation; unresolved relations use uncertain/null.
  No box or visual evidence is synthesized to satisfy coverage. Both plans must
  still share at least two positive frames with complete, compatible anchor and
  reference locations and supported relations across every pair. The private
  audit distinguishes `insufficient_common_reference_frames` from a genuine
  `same_reference_localization_conflict`; the schema remains v0.5;
- one permitted cohesion witness covers every unordered pair exactly once and
  cites at least two common-visible frames;
- cohesion positively establishes one permitted kind: canonical passive fixture
  collection, integrated part-whole, compact container-content functional unit,
  fixed mounting/coordinated array, or direct mechanical/operational coupling;
  shared head/type, support, proximity, overlap or appearance alone is insufficient;
- every pair has all four independence checks over all supplied frames;
- all six protected-relation kinds are reviewed;
- every bank context anchor is reviewed and excluded from the minimal cohesive
  closure;
- every independence outcome is `not_observed` and every protected-relation
  outcome is `absent` before the family is eligible.

For `fixed_coordinated_array`, the auditable cohesion kind
`stable_complementary_same_role_array_about_external_reference` is available when
at least two common-visible frames directly show homologous same-role components
in a stable complementary arrangement around one clearly bounded external
reference. The reference and intervening gap stay outside the family; no hidden
connector may be invented or required. A shared substrate, support, or host alone
does not qualify, and heterogeneous independently mounted or independently
functioning subjects remain separate.

This resolver is the only final coarsening authority. It requires both judges to
classify the same candidate as a family with exact assembly-kind agreement.
Either structured exclusion, an unclear
review, or any overlapping/nested positive candidate component keeps the
pre-group frozen anchors, even when the explicit planners emitted a provisional
group. A
missing valid judge output after retry records
`accepted_compact_assembly_failure.json` and makes the shot fail before matching.
An empty candidate bank writes two validated synthetic empty plans and skips calls.

Applied families use a deterministic shared semantic name core when safe and a
fixed assembly-kind fallback otherwise; models have no naming authority. They add
`assembly_kind` and `graph_components` attributes.
The firewall preserves proposal accounting, rejected and abstained clusters, and
every accepted nonfamily cluster exactly.

## Prompt-bound matching

The v0.6 physical gate separately records
`distinct_revision_proof_policy=undirected_exact_union_revision_distinct_v0.1`.
Each pair audit retains the original revision proof owner, exact source/partner
proposal sets, full initial-target set, comparison/resolution indices, and exact
union-witness indices. `revision_distinct_proof_used` distinguishes an available
proof from one actually used by the gate. Both pair directions may cite the same
original proof without a duplicated observation or a generated reciprocal claim.
Existing contrary/unresolved identity or incompatible scope relations still block
the pair; unsupported unary/split scope cannot supply a proof. The pending identity
disposition audit independently checks these references and reports unresolved
risk on a missing or inconsistent proof. No record establishes pixel truth.

After the provisional explicit-family firewall and the final accepted-candidate
firewall validate, write `adjudicator_decisions.json` and
`matching/frozen_inventory.json`. The matcher conforms to
`schemas/codex_prompt_bound_matching_v0.5.schema.json` and covers every accepted
post-partition cluster ID exactly once, with no rejected or abstained cluster.
`bound` has exactly one known registry ID, `unbound` has none, and `ambiguous`
cites one or more plausible registry IDs. Every result cites a supplied frame and
a reason.

The matcher output changes only projection membership. It cannot mutate an
inventory node. Bound and ambiguous nodes are excluded from
`final_semantics.json` but preserved in the audit.

## Ensemble audit and grounding schedule

For every final cluster, `ensemble_audit.json` records names, aliases, source
members, distinct-detector agreement, granularity, representative evidence,
exhaustive presence, physical-inventory decision, mapped verifier reports,
immutable final entity, prompt-bound match when accepted, projection decision,
and uncalibrated confidence basis. Synthetic post-partition clusters retain their
original proposal membership, allowing source support and verifier targets to be
reconstructed by proposal intersection.

Final unbound entity IDs are consecutive in stable inventory order. The grounding
schedule maps each final ID to exactly the final cluster presence frames with
`status="visible"`. It never derives the schedule from sparse representative
evidence. An unbound entity without any visible frame fails validation.

## Pipeline-compatible final semantics

`final_semantics.json` keeps the existing entity schema: `id`, `name`,
`attributes`, `entity_confidence`, and representative `evidence_frame_ids`, plus
empty `relations` and warnings. Only final accepted nodes classified `unbound`
enter this file.

## Required invariants

1. Exactly four valid homogeneous detector ledgers exist, or the run is
   incomplete. Worker concurrency does not change this denominator.
2. Every input and output refers to one identical shot; no model sees another
   shot or an expected cross-shot answer.
3. Registry content is absent from detector, adjudicator, verifier, and partition
   planner prompts and is introduced only after final graph partition freezes.
4. Every original detector proposal appears exactly once in every complete
   adjudication ledger, including after synthetic graph-node coarsening.
5. The initial adjudicator and revision cannot add entities or choose a graph
   partition; verifiers cannot decide one; partition planners cannot change
   existence or physical identity; the matcher cannot mutate final nodes.
6. Only the initial inventory adjudicator sees fixed panel membership. The full
   source map and detector-local IDs remain withheld from every model call.
7. Every proposal and cluster presence ledger covers every reference frame once.
   Detector-visible entries have valid tight boxes; all other detector statuses
   have null boxes.
8. Every detector coverage audit exactly covers all input frames, nine fixed
   spatial cells, five fixed content strata, and adjacent frame pairs; every
   local-ID reference is valid and unique within its list. Missing spatial or
   stratum cross-index membership is a nonfatal private diagnostic; temporal
   pair membership is independent of pass-2 residual membership. The audit is
   stripped before all downstream inputs.
9. Physical-inventory accounting equals accept plus reject plus abstain.
10. Required verification has two valid reports covering every selected target.
11. Every accepted physical cluster passes the selected post-verification policy.
    Legacy one-source clusters require unanimous exact-unit verifier confirmation;
    physical_v0.6 requires direct physical/scope evidence and exact-scope resolution
    of material review conflicts, independent of source support or category certainty.
12. Group/member candidate nomination requires two valid isolated plans with
    exact normalized family-scope, member-anchor-set, and `group` partition
    consensus; each plan exactly accounts for every rejected
    `group_member_conflict` alternative as a family or structured exclusion, and
    panel provenance never changes its source-blind provisional resolution. Its
    assembled view is audit-only and cannot replace the frozen baseline.
13. Final coarsening requires mandatory exact-once accepted-candidate review by
    two valid judges, exact anchor-set and assembly-kind consensus, positive
    multi-frame evidence of a permitted cohesion kind, complete clear context/independence/protection
    review, and a passing write firewall applied to the unchanged pre-group
    frozen baseline. Either judge may veto a provisional explicit-stage group.
14. Rejected, abstained, and nonfamily clusters are unchanged by final
    coarsening; the original proposal multiset is conserved by both firewalls.
15. Matcher accounting exactly covers accepted post-partition nodes.
16. Only unbound matches appear in final semantics; bound and ambiguous matches
    remain audited.
17. Every final entity has at least one visible grounding frame. Final IDs are
    unique and consecutive, and every evidence/presence ID is a supplied frame.
18. Relations remain empty at this stage.
19. Agreement counts distinct detector sources with denominator four and remains
    an uncalibrated stability signal.
20. A successful run hashes every required input, policy, schema, stage source,
    prompt, and artifact. An exhausted required role emits no successful final
    semantics.
21. Box challenges compare proposals only within one detector and trigger
    original-frame review rather than automatic deletion or merging.
22. Persistent non-containing divergent footprints inside an initial cluster use
    no source/count information and trigger review only. A revision split requires
    exact two-verifier proposal-set consensus, direct pairwise physical-separation
    evidence, persistent-adjudicator pixel confirmation, and a passing deterministic
    split firewall. Only the explicitly enabled
    `single_survivor_scope_retention_v0.1` permits a separate one-survivor
    transition under its [extended contract](scope-retention-protocol.md).
    Preserve its extended raw verifier reports, validated core projections,
    authenticated consensus and ownership/gate audits separately; residuals are
    nonaccepted original proposals, never invented confirmed physical units.

## Residual-discovery delta artifacts

When enabled, `detector_closure/<detector_id>/` preserves `original_ledger.json`, `extended_ledger.json` and `source_audit.json`. Each `round_XX/` preserves the frozen input ledger, identical retry prompt, attempt JSON/JSONL/stderr/accounting, validated delta, extended ledger and round audit. `detector_closure/stage_audit.json` records status, convergence, rounds, sources, invocations and all token usage including failures. The standalone schema is `codex_detector_closure_delta_v0.2.schema.json`. Original detector ledgers stay immutable; extended ledgers feed anonymization with their original four source IDs. Each round also preserves its specialized output.schema.json and SHA-256. Cross-index visibility disagreements remain private diagnostics without candidate mutation or retry. Exhausting the round budget with valid additions is explicitly unclosed, with budget_exhausted_sources recorded; the runner still adjudicates all four valid extended ledgers. Invalid candidate or failed source retries make the shot incomplete. Neither closed nor open coverage certifies visual accuracy. No model sees another source or the private coverage audits.
