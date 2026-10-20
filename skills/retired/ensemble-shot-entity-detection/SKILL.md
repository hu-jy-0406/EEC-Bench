---
name: ensemble-shot-entity-detection
description: Build an auditable prompt-unbound entity set for exactly one video shot with four isolated homogeneous boxed detectors, panel-aware physical-inventory adjudication, conservative graph-node partition stages, and final matching to a prompt-bound semantic registry. Use for entity-node extraction from sampled frames; do not use it for cross-shot matching, relation extraction, or GPU grounding.
---

# Ensemble Shot Entity Detection

Build one reliable prompt-unbound entity set for one shot without letting prior
prompt-bound detections suppress visual search. First discover and verify physical
content from the shot images alone. Resolve graph-node partition only after
existence and physical identity are frozen. Only then classify the final accepted
nodes against the prompt-bound semantic registry and project the unbound subset.

## Required inputs

- one `shot_id` and only that shot's ordered reference-frame paths;
- the attachment-to-frame-ID mapping;
- a frozen prompt-bound semantic registry containing stable IDs, names,
  descriptions, and entity types, used only by the final matcher;
- a new output directory that will not overwrite an earlier run.

Do not provide prompt-bound names, descriptions, detector status, or boxes to any
detector, inventory adjudicator, verifier, or graph-partition planner. Do not
provide detector boxes to the prompt-bound matcher. If inputs from more than one
shot are supplied, split the request and complete each shot independently. Never
expose another shot, its entities, or expected cross-shot consistency to any role.

Before an actual detection run, read
[references/detector-protocol.md](references/detector-protocol.md),
[references/protocol.md](references/protocol.md) and
[references/output-contract.md](references/output-contract.md) completely.
The orchestrator uses all three references. Each detector model receives only
the frozen detector-only reference; downstream model roles continue to receive
this Skill plus the general protocol and output contract.

## Fixed Pipeline 2 entry point

For repeatable EEC-Bench runs, prefer the repository runner:

```bash
cd EECBench
python scripts/run_prompt_unbound_prefilter.py EXPERIMENT_DIR \
  --entity-detection-mode ensemble \
  --ensemble-max-workers 4 \
  --ensemble-shuffle-seed 1729
```

The detector count is four. `--ensemble-max-workers` controls concurrency, not
the number of detectors. The runner hashes this Skill and its references into
every per-shot manifest and preserves raw ledgers, intermediate decisions, and
partition audits. Keep `--entity-detection-mode single` only for the frozen
one-call baseline and ablation.

`--ensemble-identity-review-policy physical_v0.6` selects the experimental
structured identity contract. Read `references/verifier-protocol.md` for the
verifier's complete role policy. In this mode, separate physical existence,
proposal-to-instance correspondence and category certainty. A specific name
never rescues unresolved physical evidence; a broad name never invalidates a
clearly supported physical object. Positive same-content evidence is required
for a same-scope alias, and absence of a separation witness means unresolved,
not automatically the same instance. The structured gate replaces both legacy
source-support/name gates described below; it uses exact scope and direct
evidence, including any explicit adjudicator resolution of a review conflict.
The default `legacy` mode remains available for comparison. Record the selected
mode and schema hashes; never apply v0.6 interpretations retroactively to old
reports.

The default-off `--ensemble-scope-retention-policy
single_survivor_scope_retention_v0.1` is restricted to `physical_v0.6`. When
selected, also read
[references/scope-retention-protocol.md](references/scope-retention-protocol.md).
Two independent exact-subset proofs can permit one supported survivor while the
remaining original proposals stay uniquely owned and nonaccepted. This is not
an ordinary physical split or a discovery path. Full original-scope reviews,
final physical and identity evidence, external pair questions, and graph lineage
protections still apply. Disabled runs retain the existing split contract.

Determine `scope_relation` from the complete asserted physical content.
Image-plane enclosure, support or proximity alone establishes neither
`whole_part` nor `group_member`. A fixture-only claim excludes stored or supported
contents; a contents-only claim excludes the fixture. "Only" describes asserted
content, not a category shortcut: it does not remove integral components or
rewrite an explicit assembly claim. Whole-part needs a claimed whole and its
actual constituent; group-member needs a claimed group containing that member.
Independently bounded objects may have comparable scopes while one supports or
encloses the other. Comparable scope does not prove distinctness; exact-union
boundary, interaction or continuity evidence remains required. If the relation
itself is uncertain, use `scope_relation=unresolved`. Known non-comparable
relations still use `judgment=unresolved`; do not use a relation enum to evade an
unresolved identity question. Later graph composition is separate.

Every `adjudicator_evidence` item, including unresolved evidence in a rejected or
abstained cluster, may use only its own proposal IDs and IDs owned by partners in
that cluster's own `identity_comparisons`. A reverse declaration elsewhere does
not create a local link. This is a maximum allowance, not a requirement that all
weak observations cover the complete owner. Meaningful local comparisons can
remain unresolved; never invent a partner, copy evidence or relabel a scope to
pass validation. Eligible original reverse-owner union proof can still serve the
undirected gate without a new local link. The narrow initial context preparation
below remains the only exception for qualifying broad observations.

The initial-only `initial_identity_pending_v0.2` preparation keeps a failed raw
identity assertion auditable while allowing its existing review stage to resolve
it. Only a structurally valid comparable same/distinct assertion with valid
nonempty references but no required exact-union identity witness, or valid empty
references, is derived as
`unresolved`. Evidence, proposal ownership, existence, names and graph scope stay
unchanged. Preserve the raw response and conversion audit separately. Both full
endpoint scopes must enter both independent verifiers as neutral pair questions,
even when ordinary target heuristics would omit them. Verifiers receive no prior
assertion or conversion audit. Invalid IDs, frames, references, ownership, schema
or non-comparable confirmed relations remain fatal. Do not apply this preparation
to verifier or revised outputs. Trace each pending pair through the final physical
gate; rejected, abstained or incompletely mapped endpoints retain an explicit
coverage risk. Contract resolution does not establish pixel truth or independent
verifier agreement when it relies on an adjudicator revision.
Every valid initial-declared pair also enters both verifiers as a neutral question
over both complete scopes, including rejected or deferred endpoints. Reviewing an
endpoint does not promote it or supply a missing observation.

The preparation envelope `initial_context_then_pending_v0.2` first applies
`initial_context_quarantine_v0.1`. Prefer exact-own or exact-pair observations in
the proof ledger. A broad initial observation spanning three or more complete
original scopes cannot prove one exact scope or a binary identity claim. Preserve
such context privately, with its original content, owners, references, hashes and
an explicit evidence-index map; remove it only from the derived proof arrays.
This narrow projection permits only unreferenced context or references already
marked unresolved whole-part/group-member. Any positive or other reference,
partial owner scope, unknown ID or malformed record remains fatal. Normal own-
and two-scope evidence is not covered by this exception. All eligible wide context
is classified against the same raw partition, including context that was already
inside the declared partners' allowed IDs. Never add a comparison or enlarge an
observation to make it legal. Run the pending-assertion preparation only after
this projection, preserving both audits separately. An independent audit must
reconstruct the projection. Both verifiers must review every complete involved
scope, without seeing this private context or its previous verdict. Final and
verifier contracts stay strict; a missing review makes execution incomplete,
while rejection, abstention or changed scope remains an explicit coverage risk.
The revision uses the supplied current indices, never old indices from context
memory. A newly scoped observation requires inspecting the original pixels.
Before accepting either verifier report, the additional original-scope coverage
check requires at least one valid exact-own observation for each already forced
context scope. Other targets retain their existing evidence requirements. Weak
or unresolved observations are valid; pair-union evidence is separate and cannot
be relabeled as an own-scope observation. An invalid report uses that verifier's
existing one-repair allowance while retaining its successful peer. Persistent
failure stops before revision; complete coverage does not certify pixel truth.

Under `undirected_exact_union_revision_distinct_v0.1`, a valid revised distinctness
proof may be stored at either complete endpoint of the unordered pair. The
comparison and resolution reference an observation covering the exact union of
both complete final scopes. The resolution's owner array is exactly its containing
final cluster; its `target_cluster_ids` cover all contributing initial targets on
both sides. The gate references that original location for both sides; it
never copies evidence, changes scope or creates a reciprocal claim. Any existing
contrary, unresolved or incompatible scope declaration still blocks the pair.
Unary eligibility and the split firewall remain required. Audits preserve the
source cluster and exact indices and distinguish one adjudicator observation from
independent agreement. Missing reverse bookkeeping is not an observed conflict.

Initial output is canonical. The selected revision policy is recorded explicitly:
`canonical` retains the canonical fields; `implicit_owner_wire_v0.1` uses the
revision-only schema explicitly specified for that turn and omits only each
resolution row's redundant owner array. The model still chooses the axis, initial target IDs and
local evidence indices; clusters and observations retain their proposal arrays.
For every axis the owner is the complete containing final cluster, even when a
retained-distinct observation covers both endpoints. A merged final cluster can
itself own a union. Preserve raw wire separately from deterministic canonical
materialization and its pointer audit; validate the full canonical contract and
all existing gates. Repair uses the selected format, same thread and original
retry limit. Materialization supplies no visual evidence or split authorization.

The first-revision obligation preview is partial and applies to current scopes.
Full supplied inputs and review obligations remain in effect; absence from the
checklist is not clearance. Reestablish obligations after scope changes. Checklist
addresses are not evidence indices for the returned ledger.

The accepted-only partition contract is v0.5: both judges independently locate
every exact anchor in all common-visible frames, bind positive cohesion to a
localized accepted reference or a member's visible intrinsic structure, and
agree on at least two complete common frames. Uncertain scope is a valid
non-merge result. Member boxes need not overlap; different judges' locations
for the same anchor must be compatible. This verifies scope accounting and
geometric consistency, not the truth of model-written visual descriptions.

The reference coverage policy is
`all_candidate_common_visible_reference_frames_v0.1`. Both reference observations
and each member/reference relation account for every candidate common-visible
frame exactly once. A nonvisible or unresolved reference uses `uncertain`, null
boxes and an explicit limitation; never copy or interpolate a box to fill coverage.
Coarsening still requires at least two frames with positive, geometrically
compatible complete anchor/reference evidence and supported member relations in
both plans. Different positive citation subsets cannot hide otherwise jointly
reviewed frames. Insufficient shared reference coverage is reported separately
from an observed localization conflict.

## Execution contract

1. Act only as orchestrator. Do not substitute the orchestrator's own entity
   discovery for a missing agent.
2. Run four isolated detector calls. Except for `detector_id` and local IDs,
   give them identical ordered shot frames, frame mapping, entity-scope policy,
   schema, and complete-inventory method. Assign no specialized region, temporal
   direction, entity category, or attention priority. A detector must not see the
   registry, another detector's output, context outside its allowed inputs, or
   another shot. Its complete model-visible policy is the standalone
   detector-only reference; do not append downstream adjudication, verification,
   partition, matching, grounding, relation, or cross-shot instructions.
3. Each detector inspects all supplied frames together and returns one shot-level
   inventory through the detector-only protocol's provisional-inventory,
   deterministic-coverage, and conservative-cleanup passes. Every candidate has
   representative evidence plus an exhaustive per-frame presence ledger. Every
   `visible` entry contains a tight normalized box around only that entity; other
   statuses use a null box. Its mandatory private `coverage_audit` accounts for
   every frame, all nine image-plane cells, all five content strata, and every
   adjacent frame pair exactly once. Cross-indexed entity IDs must be valid and
   unique within each list, but an entity omitted from a spatial or stratum
   cross-index is recorded as a nonfatal private diagnostic rather than causing
   detector retry. Temporal pair IDs record entities newly revealed or materially
   confirmed by that pair and are independent of the pass-2-only residual list.
   Empty reviewed regions are valid; there is no entity quota. For every
   provisional collection, assembly, multi-element scope, large or cropped
   proposal, and bounded-looking neighboring region, the detector re-localizes
   the content from original pixels and audits its internal boundary plus a narrow
   exterior perimeter. Separate a heterogeneous neighbor only with repeated
   coherent-boundary evidence and a direct separation cue; do not decompose
   ordinary integrated or homogeneous content or promote a low-contrast visual
   artifact. Before returning, remove same-footprint aliases and incoherent
   identities that copy one track in early frames and another track later. A frame
   is `visible` only when downstream grounding is reasonable there, and its box
   must contain all and only the claimed physical content.
4. Persist every detector ledger unchanged. Retry a failed detector at most once
   with identical role inputs. If four valid ledgers are not obtained, mark the
   ensemble incomplete rather than changing the denominator.
   The current CLI then runs up to three external residual rounds per source.
   Each isolated continuation sees only its own frozen ledger and this shot's
   frames. Return only new physical candidates with unused local IDs and explicit
   novelty evidence; never rewrite, delete, or re-emit original proposals. Validate
   every frame times nine grid cells, all four edges in first and last frames, and
   every adjacent pair for both revealed and disappearing content. Preserve each
   delta and extended ledger privately. An empty delta stops that source; after
   additions, run another round. Retry invalid/failed calls once with identical
   inputs. Per-round schemas constrain known paths, IDs and frames; private
   cell cross-index visibility disagreements are diagnostic and never rewrite a
   candidate. Failed retries make the shot incomplete. Reaching the round budget
   with valid additions preserves all four extended ledgers for adjudication and
   records open coverage and budget exhaustion. Closure is a search stop condition,
   not an execution-validity requirement or proof of accuracy. Extended ledgers retain exactly four source identities. The option
   `--ensemble-detector-closure-max-rounds 0` disables this stage for ablation.
5. Replace local IDs with opaque proposal IDs and deterministically shuffle the
   union. Preserve fixed `detector_1` through `detector_4` panel membership for the
   inventory adjudicator, but withhold detector-local IDs, self-confidence, and
   any quality ranking. Compute same-detector high-IoU trajectory challenges as
   mandatory review signals; box overlap never deletes or merges automatically.
6. The persistent inventory adjudicator sees the panelized union, challenges, the
   same-shot frames, and no registry. Detector boxes are low-trust position hints.
   It independently re-localizes claimed visual content in the original pixels
   and freezes existence, physical identity, salience, and scope. It may merge
   aliases only when they represent the same physical content at the same
   candidate graph scope. It cannot discover an entity or coarsen physically
   distinct anchors merely to choose a graph partition.
7. When a group-scope proposal conflicts with proposals for two or more separately
   localizable member units, the adjudicator preserves the real members as
   accepted physical anchors and preserves the supported group proposal in a
   separate rejected alternative marked `group_member_conflict`. When accepted
   anchors may form a compact assembly but no explicit group alternative exists,
   mark the relevant anchors `possible_compact_assembly_partition`. These markers
   defer graph partition; they do not decide it.
8. Use the private source map only to select weak or conflicting clusters for two
   isolated homogeneous verifiers. Verifiers inspect supplied existence,
   salience, same-instance, and graph-partition questions but cannot see the
   registry or discover entities. Their compact views retain all target IDs,
   proposal names and granularity, frame IDs, visibility, boxes, location hints,
   and explicit challenges, with all original frames. Omit prior adjudicator
   verdicts and reasons, source attribution, confidence, and repeated prose.
   Verification evidence must identify physical boundaries, continuity or
   separation, and visibility limitations; supplied names are not proof.
   Independently flag persistent, non-containing
   divergent proposal footprints inside one initial cluster as review-only
   physical-instance challenges; this trigger uses no source labels or detector
   counts and never splits automatically. For each challenge, a verifier may
   propose a split only as a complete proposal-set partition whose units are all
   confirmed and graph-worthy, with direct original-frame separation evidence for
   every unit pair. Resume the original adjudicator once with their source-blind
   reports and only the exact partition consensuses shared by both verifiers. The
   revision may correct existence, identity, salience, or scope, merge true
   same-content duplicates, and split a challenged initial cluster only after its
   own pixel review and only with the exact consensus partition; graph-partition
   findings remain advisory.
9. Select the post-verification policy before graph partition. In
   `physical_v0.6`, apply only the structured physical-identity gate described
   above. The rest of this step applies only to `legacy` identity review.
   Apply the deterministic single-detector gate. A final
   accepted cluster supported by exactly one distinct detector remains accepted
   only when both isolated verifiers completely and independently confirm
   `existence_judgment=confirmed` and `salience_judgment=graph_worthy` for every
   relevant complete initial target. A final unit produced by splitting an initial
   target requires both reports to confirm that exact proposal-set unit; overlap
   with a confirmed larger target is insufficient. Otherwise change it to
   `abstain`, retain it in the audit, and set `final_entity` to null.
   Then apply the generic-identity evidence gate. The current CLI policy is
   `all_support`: a detector majority never exempts a generic identity from
   its evidence requirements. Abstain when both final names retain a narrow
   placeholder head, explicit identity/category/subtype uncertainty remains, and
   complete records supply neither unanimous strong visual confirmation nor
   unanimous direct independence evidence at the exact physical-unit scope.
   Concrete physical categories are protected. The legacy `nonmajority` mode
   additionally limits this conjunction to nonmajority support and is an explicit
   ablation only. Preserve diagnostics privately; votes alone never prove existence.

10. Audit explicit group-versus-members families with two isolated ephemeral
    planners running on byte-identical source-blind inputs. Each receives the
    post-gate baseline, anonymous proposals, original frames, and no detector
    panels or counts. Each planner must inspect every rejected
    `group_member_conflict` alternative in the original pixels and account for
    it exactly once as either one family non-anchor or one structured exclusion;
    an omitted alternative invalidates that planner output. An exclusion retains
    its candidate accepted member anchors and any independently graph-worthy
    context-anchor subset. A passive homogeneous collection has one canonical scope: all visible passive contents of one physical category within one clearly bounded storage or display fixture, across its internal shelves, bays, rows or slots. The fixture is excluded from the content node. Internal dividers, crop, color differences, or separately localizable subgroups alone do not split this collection. Different fixtures, individually framed artwork or separately mounted complete display fixtures, heterogeneous neighbors, and objects separately handled or used during the shot remain separate. Same-role covering or control panels serving one bounded fixture use one whole-array scope, excluding that fixture, unless directly observed independent handling, use or motion warrants a split. Apply these scopes at discovery and final partition regardless of whether proposals initially used whole collections or subdivisions. A shared unbounded surface alone never establishes this organization. Apply the shared holding/container scope rule below: contents-only fixture exclusion is not a ban on a positively supported complete container-content functional unit. Resolve each valid plan deterministically.
    For an eligible family with positive compact-scope evidence and no blocking
    protection, select its supported group partition when no typed independence
    witness is present; witnesses over every member boundary retain members;
    partial evidence fails closed to the frozen baseline. Form a provisional group candidate only when both plans
    independently identify the exact same frozen family scope and member-anchor
    set and both resolutions select `group`. Planner-local IDs and free-text
    wording are not identity.
    A gross group-proposal/member-track incompatibility in an otherwise valid
    family invalidates that exact group witness. Preserve its baseline members
    and privately record the group proposal, member and frames. It does not
    establish incompatibility between the members themselves. The accepted-only
    gate independently re-localizes its exact anchors and cohesion reference.
    Invalid IDs,
    scope, witnesses, or missing required planners still fail validation.
    Omission, structural or partition disagreement, overlap, or nesting retains
    the baseline. This stage's assembled view is audit-only and must never replace
    the frozen baseline or become final inventory; every provisional group still
    requires the accepted-only second gate. An exhausted planner retry makes the
    shot incomplete. Detector provenance is audit-only and never selects the partition.
11. Build a deterministic mandatory candidate bank for the accepted-only stage.
    Candidates come only from source-blind member-map neighborhoods emitted by
    either explicit-family plan, including structured exclusions and
    non-consensus variants, exact-scope verifier-declared partner maps, plus
    conservative same-role semantic cohorts among
    anchors marked `possible_compact_assembly_partition`. Explicit planner member
    maps define their peer-anchor closure directly after mapped context is removed;
    exact normalized proposal `canonical_head` and `entity_type` overlap is used
    only to cohort otherwise unscoped marked anchors. Verifier partner maps are
    nominations only: each initial target must still match one accepted resolved
    anchor by its entire proposal set. Drop changed, missing, or ambiguous scope;
    normalize repeated partner IDs, reject self references, and never take a
    transitive closure. Keep verifier provenance private. The
    public bank contains only candidate IDs, frozen anchor IDs, and context-anchor
    IDs—never proposal IDs, derivation, boxes, panels, counts, or frequency.
12. Run two isolated, identical-input accepted-only candidate judges against the
    unchanged pre-group frozen baseline. They see
    the public bank, accepted resolved cluster semantics, evidence, presence, and
    original frames. Each must review every bank candidate exactly once as either
    an exact-anchor family or a structured exclusion; it cannot freely propose a
    family. A positive family requires a minimal cohesive closure, positive
    evidence of one permitted cohesion kind in at least two frames, complete clear
    independence and protected-relation reviews, and explicit exclusion of every
    supplied context anchor. Shared support, proximity, overlap, or semantic-head
    agreement alone is not cohesion. A fixed coordinated repeated set may use
    positive evidence that homologous same-role components occupy stable
    complementary positions around one clearly bounded external reference and
    jointly realize one boundary, covering, control, or display scope. The
    external reference is context, not a family member; its gap does not make the
    set noncompact and a continuous connector need not be visible. This does not
    extend to shared substrates or to heterogeneous independently mounted or
    independently functioning subjects. For passive homogeneous collections, emit structured `collection_scope_review` naming an excluded accepted fixture and common category; confirm complete visible content, passive status, heterogeneous-neighbor exclusion and individually-framed-subject exclusion with two jointly visible frames. Other assembly kinds use null. This is the only stage with final coarsening
    authority: apply a bank candidate only under exact two-judge
    anchor-set and assembly-kind consensus. Overlap, uncertainty, or either
    exclusion leaves the pre-group frozen nodes unchanged, even when both explicit
    planners produced a provisional group. Failed retries make the shot
    incomplete; an empty bank produces two synthetic empty plans and zero calls.
13. Freeze the resulting accepted graph nodes. Run one isolated prompt-bound
    matcher over those immutable nodes, the same-shot frames, and the semantic
    registry without detector boxes. It classifies every accepted node exactly
    once as `bound`, `unbound`, or `ambiguous` and cannot add, remove, merge, split,
    rename, or otherwise revise a node.
14. Project only `unbound` nodes into `final_semantics.json`. Preserve bound,
    ambiguous, rejected, and abstained outcomes in `ensemble_audit.json`. Schedule
    grounding from accepted `visible` presence frames, not merely representative
    evidence citations. Do not infer relations in this skill.

## Non-negotiable decisions

- Use the detector union rather than intersection or majority as the ordinary
  existence gate. Panel agreement measures repeatability, not visual proof or
  calibrated probability. The one-source unanimity rule and the narrow
  generic-identity evidence conjunction are conservative post-review
  abstention exceptions; neither turns detector count into direct existence
  authority.
- A one-source candidate may survive only after both verifiers confirm its
  existence and graph worthiness. A four-source candidate may still be rejected
  when original-frame evidence contradicts it.
- Detector panels are visible only to the initial inventory adjudicator. Fixed
  panel labels encode homogeneous run membership, not specialization, quality, or
  authority. The full source map and detector-local IDs remain private.
- Detectors discover. The inventory adjudicator and its revision freeze physical
  content, identity, existence, salience, and scope. Verifiers recheck supplied
  targets. Explicit-family planners only nominate and audit candidate scopes;
  accepted-only judges plus their firewall alone authorize final coarsening. The
  matcher only classifies final frozen nodes against the registry.
- Cluster physical visual content before names. Different names, subtypes,
  attributes, relative-location phrases, or detector repetition do not prove two
  instances. Retargeting a proposal to different nearby content is forbidden.
- Treat detector boxes only as low-trust position references. Re-localize against
  original pixels before using spatial evidence. High symmetric tight-box IoU is
  a review trigger, not an automatic identity decision; containment is not its
  substitute. Persistent non-containing divergence among proposal boxes already
  assigned to one cluster is likewise only a review trigger; no box geometry can
  split a cluster without exact two-verifier proposal partitions and persistent-
  adjudicator confirmation from original pixels.
- Preserve two physical anchors when an original frame simultaneously resolves
  separately localizable boundaries, or when manipulation or trajectories
  establish distinctness, even if supplied boxes overlap or one box spans both.
- Spatial overlap, containment, contact, attachment, or support alone proves
  neither identity nor graph-node membership. A held or carried item retains a
  separate physical anchor when its own boundary, state, trajectory, or
  interaction establishes a distinct identity; later graph grouping does not
  change that physical correspondence.
- Treat clothing, footwear, hair, body parts, and ordinary accessories as
  constituents of a person while worn. A constituent may become a separate node
  when removal or another independently trackable state or interaction is directly
  observed.
- Physical distinctness and graph-node partition are different judgments. A
  visible boundary may establish physical constituents without requiring multiple
  final graph nodes.
- Accepted-only coarsening requires positive cohesion, not merely the absence of
  observed independence. Valid cohesion includes canonical passive homogeneous fixture collections, integrated part-whole structure, one compact container-content functional unit, a common fixed mounting or coordinated array, or direct mechanical or operational coupling.
- Apply the shared holding/container scope rule in `references/protocol.md` to
  the exact candidate members. Protected holding/carrying includes an actor with
  an external item and an inanimate mechanism or support retaining an independent
  load. Physical distinctness or containment alone does not establish this
  holder/payload relation. A visible holding/load state is enough; pickup or movement need not be
  observed. Stationary, small, portable or inanimate is not an exemption. Actual
  temporary packing/loading/transport remains protected; possible future
  transport does not make ordinary storage a temporary payload.
- A compact container-content functional unit needs positive original-pixel
  evidence that its bounded structure organizes, constrains or presents the
  complete included content as one local functional scope. Mere containment,
  contact, support, stable placement, tight enclosure, presumed conventional
  purpose or no observed separate handling is insufficient. Actual operation
  need not be observed when visible structure directly supports that scope.
  When the only organization is passive same-category storage/display within a
  fixture, use the complete contents-only collection and exclude the fixture.
  Adding it requires independent positive evidence for the full functional whole;
  changing an assembly-kind label cannot provide that evidence or waive protection.
- Check actual member protection and independence before choosing cohesion.
  Lack of observed handling does not by itself establish absent protection.
  An external actor carrying a supported functional whole remains outside it;
  that external relation alone does not establish an internal member-payload
  relation. Unresolved scope or protection preserves the frozen anchors, and
  every stage-specific scope, frame, context, agreement and geometry check remains.
- For a coordinated repeated set, stable complementary placement of homologous
  same-role components around one bounded external reference can itself be
  positive array evidence across at least two common-visible frames. The reference
  is explicitly excluded. A visible continuous connector is unnecessary, but a
  shared substrate, support, proximity, or appearance without complete
  complementary organization is insufficient; heterogeneous independently
  mounted or independently functioning subjects remain separate.
- Do not extend compact-assembly coarsening across a large host or support, a
  person or animal, a protected holder/item or load relation under that shared
  definition, loose objects merely sharing
  proximity or support outside the canonical fixture-collection policy, actual
  temporary packing or transport payloads, or worn/body
  scope cases. Any present or uncertain protected relation blocks coarsening.
- Preserve visible constituent semantics as `graph_components` and an
  `assembly_kind` attribute when nodes are coarsened. Partition planners have no
  naming authority.
- Representative evidence justifies existence and identity; it is not a
  visibility inventory. Every supplied frame must receive exactly one presence
  status for every detector proposal and every adjudicated cluster.
- Detector `coverage_audit` records are private completion metadata. Validate
  their exact frame, grid, stratum, adjacent-pair structure and every referenced
  local ID, then strip them before anonymization. Missing spatial/stratum
  cross-index membership is a nonfatal private diagnostic. Temporal pair IDs are
  independent of pass-2 residual IDs. These records are not entity evidence,
  confidence, detector support, votes, or inputs to any downstream model role.
- A `bound` match means the frozen visual node is the same physical instance as a
  registry entry. Spatial or interaction relations to a registry entity do not
  establish identity. Ambiguous identity remains audited and is not projected as
  unbound.
- Never launch relation extraction or cross-shot reconciliation here. Grounding
  may run later only because the pipeline entry point explicitly requests it.

## Completion

Finish only when four immutable detector ledgers with valid private coverage
audits exist; every original proposal is accounted for exactly once; required
verifier reports and the single-detector gate are complete; both graph-partition
stages complete or deterministically skip; every accepted final node has a
complete per-frame presence ledger; and the matcher covers every accepted
post-partition node exactly once. A required role that fails after its one
configured retry makes the shot incomplete rather than silently weakening the
protocol. Keep the frozen frames, original proposal universe, required target
scopes, schema, and evidence policy fixed. Detector, matcher, group/member, and
accepted-only planner retries reuse their role prompt; verifier retries may
append recorded failure feedback. Adjudicator revision permits one bounded
same-thread contract/accounting repair with the recorded failure and diagnostics,
under the existing exact-scope and split constraints. Preserve the actual prompt
for every attempt; a retry is not an independent evidence vote. Report failures,
abstentions, runtime, token usage, and that confidence remains uncalibrated.
