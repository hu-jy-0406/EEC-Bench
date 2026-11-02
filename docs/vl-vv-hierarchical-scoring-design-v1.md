# Hierarchical EEC scoring with prompt-bound / prompt-unbound pillars — design v1

Status: **proposal, 2026-10-06. Not implemented.** No prompts, gates, schemas
or scores have been changed. Section 10 lists the judgment calls that need the
owner's confirmation before implementation; section 11 records the owner's
decisions of 2026-10-20 (all four judgment calls resolved; the B/U rows are not adopted).

## 0. Summary

The episode score becomes a 3 × 3 matrix. Rows give the provenance of the
content. Columns give the evaluation criterion.

| Row (provenance) | Fidelity (V-L) | Within-shot stability (V-V) | Cross-shot continuity (V-V) |
| --- | --- | --- | --- |
| **B** Prompt-bound (intended) content | **F_B** | **W_B** | **X_B** |
| **U** Prompt-unbound (unintended) content | ∅ — undefined: no reference text exists | **W_U** | **X_U** |
| **S** Shot structure (content-free) | (counted in F_B: the shot plan is prompt text) | **W_S** | **X_S** |

The tree used for aggregation:

```
EEC  = mean over applicable { B, U, S }
├── B  Intended content     = mean{ F_B , C_B }      C_B = mean{ W_B , X_B }
├── U  Unintended content   = mean{ W_U , X_U }                    ← headline contribution
└── S  Shot structure       = mean{ W_S , X_S }
```

Five design rules:

1. **Provenance is decided per checked subject, from the text.** A thing is
   prompt-bound if the prompt refers to it. A relation is prompt-bound if the
   prompt states it. Everything else that is visible is prompt-unbound.
   Detector IDs (`pb…`/`ge…`) are evidence, not the decision (section 2).
2. **Within a cell, confirmed events pool.** Each cell uses the existing
   penalty rubric v2 product. Rubric, confidence factors, partial-review rule
   and duplicate rule are unchanged.
3. **Across cells, scores are averaged, not pooled.** Each node is the
   unweighted mean of its *applicable* children.
4. **Every cell has an explicit state: `scored`, `not_applicable`,
   `not_audited` or `failed`.** "Nothing to evaluate" never becomes 100 or 0.
   Applicability comes from an audited support set, defined so that it cannot
   shrink because content was inconsistent (section 5).
5. **Leaderboards aggregate leaf-first.** Each leaf is averaged over the
   videos where it applies, and then the tree is applied. A model cannot
   raise its score by producing videos without unbound content (section 6).

The current scores remain exactly recoverable as column views. The legacy
V-L score equals F_B. The legacy within-shot and cross-shot scores are the
event-pooled products of their columns. So no history is lost.

## 1. Why the current V-L / V-V split cannot show unbound performance

Evidence comes from all 66 discovery-v2 review results of the 14 tested
videos in `vl_vv_old_vs_new_20261005`, `vl_vv_v2_results_20261005` and
`vl_vv_partial_review_20261006`. Repeat runs and re-reviews of the same
candidates are included, so the labels are not independent. The census
script is in the session scratchpad, not the repository.

1. **Discovery almost never examines unbound entities.** Of 131 scored
   V-V labels (confirmed or partly confirmed), **1** cites a prompt-unbound
   (`ge…`) entity: an unprompted shirtless man in p047 Wan2.1. Cross-shot
   labels cite `pb…` entities 115/115 times. The cause is in discovery. The
   only enforced audit, the continuity ledger with
   `required_continuity_subjects`, covers prompt-bound characters and places.
   Checklist items C1/C2 mention recurring props and background figures, but
   no gate makes discovery inventory unbound content. An empty U bucket
   therefore means "not looked at", not "consistent". A U score of 100 computed from current
   outputs would be exactly the artificial perfect score the owner wants to
   avoid.
2. **Unbound content is hidden under bound place IDs.** The 18 scored
   `setting_background` labels all cite place or object `pb…` IDs. Their
   texts describe both elements the contract states and elements it does not
   state.
   - #014 Wan2.1: "Courtyard buildings" and "Pale stone facade" are contract
     objects, so this change is bound.
   - p047 Wan2.1: the Shot2 blue sign has no contract counterpart, so it is
     unbound.

   Neither the entity IDs nor the subcategory can make this distinction.
3. **The detector ledger is not a census of unbound content.**
   - 4/14 videos have no `ge…` entity at all, although every video shows
     unprompted surroundings.
   - Only 2/14 have a `ge…` entity observed in two or more shots.
   - The ledger also splits stated worn items into `ge…` entities. In p032
     Wan2.2, glasses, wristwatch and ear stud are all in Character 1's
     description.

   Support taken from the ledger alone would make the unbound cross-shot cell
   N/A in 12/14 videos, which is wrong. It would also put prompt-described
   accessories in U.

Consequence: a re-bucketing of existing outputs cannot produce a meaningful U
score. The U pillar needs (a) a text-grounded binding on every V-V label and
(b) an explicit audit of unbound content, which defines its support.

## 2. Provenance rules

**Prompt-bound content** is content for which the prompt or contract supplies
a reference: a literal quote naming the thing or stating the relation.
**Prompt-unbound content** is visible content without such a reference. The
generator invented it. This is the same test that already defines V-L ("can
the text be quoted?"), applied to the *subject* of a V-V label.

| Subject | Bound when | Notes |
| --- | --- | --- |
| Character, animal, object, structure | The prompt/contract refers to it, by name or by the role it plays. A wall where the prompt places "a pale poster wall" is bound even if it is rendered wrongly; that is a V-L error, not unbound content. | Unstated separable things are unbound: props, furniture, background buildings, signage, bystanders. |
| Intrinsic appearance: face, body, hair, worn clothing and accessories, colour, material | Inherits the binding of its owner. | The man's unstated hairstyle is B. Glasses or a bracelet the ledger split into `ge…` are B when they are worn by a bound character. |
| Place | The place itself (a scheduled location) is bound. Its lighting, weather and time of day inherit that binding. | A place is a container. Its walls, furniture, buildings and vegetation are separate subjects, bound only if stated. |
| Relation: arrangement, left/right, contact, support, holding, relative state | The prompt states that relation. | Any relation that involves an unbound entity, and any unstated arrangement of bound entities, is unbound. |
| Shot plan, frame stream, global rendering style | Structure (row S) | Not depicted content, so provenance does not apply. |

Why intrinsic appearance inherits but relations do not: naming a referent
fixes *which individual* must appear, so its identity and appearance
consistency is consistency of intended content. Naming two entities fixes no
arrangement between them, so the arrangement exists only because the model
chose it.

**Single binding per V-V label.** A V-V label concerns either bound or
unbound content, never both. A change that mixes the two is reported as two
issues, for example "the stated sofa became an armchair" and "the unstated
bookshelf vanished". This keeps one-issue-one-cell, keeps partial review
consistent (the true part keeps the binding of the claim), and stops a mixed
claim from hiding U events inside B.

**V-L labels are always B.** They are judged against text. This includes a
"prominent unrequested extra" (`presence_count`): the cast requirement that
was violated is bound. A dual-labelled issue can therefore deduct in B and U.
For example, an unrequested person pops into one shot: V-L `presence_count`
counts in F_B, and V-V `presence_instability` on that person counts in W_U.

## 3. Leaves (cells)

Each scored label goes to exactly one cell. Its V-V subcategory determines
the column and whether it is structural. Its binding chooses between B and U.

| Cell | Labels |
| --- | --- |
| F_B | All V-L labels, including `shot_structure` |
| W_B / W_U | V-V within: `identity_drift`, `appearance_drift`, `object_instability`, `presence_instability`, `background_drift`, `physical_integrity`, `relation_break` (row chosen by subject binding) |
| X_B / X_U | V-V cross: `character_identity`, `character_appearance`, `object_identity`, `setting_background`, `environment_lighting`, `instance_count`, `state_action_continuity`, `spatial_continuity` (row chosen by subject binding) |
| W_S | V-V within: `unintended_cut`, `rendering_instability` |
| X_S | V-V cross: `transition_realization`, `rendering_style` |

A missed required cut therefore deducts in F_B (V-L `shot_structure`) and in
X_S (V-V `transition_realization`). These are two criteria: the shot plan was
not followed, and no visible boundary exists. This mirrors how every other
dual label already works.

**Facet factors (diagnostic, not separately weighted).** Inside each content
cell, the events are split into an *entity* factor (identity, appearance,
presence, count, integrity) and a *relation & state* factor
(`relation_break`, `spatial_continuity`, `state_action_continuity`). Cell
scores are products, so the factors multiply exactly to the cell score. This
lets the page say, for example, "X_U = 56 = entity 75 × relation 75".
Relations are visible without a second normalization layer. F_B gets the same
kind of factor split by V-L subcategory group:
- entities & attributes;
- actions & relations;
- setting/camera/style;
- continuity & shot plan.

## 4. Cell score

The cell score uses the existing penalty rubric v2. It is unchanged:

```
S_c = 100 · Π_{g ∈ G_c} (1 − D_g / 100)
D_g = max over labels ℓ in duplicate group g of  base(sev_ℓ) · conf(ℓ)
base = {minor 10, moderate 25, major 50, critical 80};  conf = {high 1, medium 0.75, low 0.5}
```

- Partly confirmed labels deduct for their confirmed part (scoring v4 rule).
- `duplicate_of` must stay inside one cell. This is the current same-bucket
  rule, now applied per cell. Duplicates must share their binding.

**Why pool events inside a cell but not normalize by support.** The
evaluator detects and verifies violations; it does not issue a verdict for
each unit. Dividing by a unit count would make the score depend on census
granularity. One bookshelf counted as twenty books would dilute every error.
It would also reward rich scenes for producing more units. Support is
therefore used for applicability and reporting, and a normalized rate is
reported separately as analysis (section 6.3).

**Legacy views are exact.** All V-L labels are in F_B, so legacy V-L equals
F_B. Every within-shot V-V label is in exactly one of W_B, W_U and W_S, and
duplicate groups never straddle cells. So:

```
legacy within = W_B · W_U · W_S / 100²
legacy cross  = X_B · X_U · X_S / 100²
```

These hold up to rounding. An N/A cell has no events and acts as factor 1.

## 5. Support and applicability

### 5.1 Cell states

| State | Meaning | Score | Effect on parents |
| --- | --- | --- | --- |
| `scored` | Support > 0 and the audit covered it | 0–100 (100 means "audited, no confirmed event") | Included |
| `not_applicable` | No content of this kind exists in this episode (reason code) | null | Excluded, and its parent's weights renormalize |
| `not_audited` | Content exists but the evaluator's audit record does not cover it | null, shown as "not audited" | Excluded, and the parent is flagged `incomplete` |
| `failed` | Upstream stage failed | null | Excluded, and the case is listed as failed |

`not_audited` is kept separate from N/A so that an evaluator coverage gap is
never presented as a property of the video. In production the discovery
validation gates (5.3) should make it impossible. It remains for historical
runs and stage failures.

### 5.2 Support per cell

Support is the set of **audited units**. The audit can only add units.
Units cited by a scored event in the cell are always added, because a
confirmed event proves that content exists.

| Cell | Unit | Opportunity (outcome-independent) | N/A when |
| --- | --- | --- | --- |
| F_B | contract claim | all claims; at least one in every contract | never |
| W_B | (bound subject, shot) visible in `shot_scan` | bound subjects scheduled or seen in the shot | no bound subject is visible anywhere (`nothing_bound_visible`) |
| X_B | bound subject in the continuity ledger with ≥ 2 shots | subjects scheduled in ≥ 2 shots (`required_continuity_subjects`) ∪ visibly recurring | `single_shot_episode` or `no_recurring_bound_subject` |
| W_U | (unbound subject, shot) visible in `shot_scan` | unbound inventory of the shot | audit confirms no unbound content in any shot (`no_unbound_content`) |
| X_U | unbound subject with a recurrence opportunity | unbound subjects in a **revisited place** (a place scheduled in ≥ 2 shots) ∪ unbound subjects seen in ≥ 2 shots | `single_shot_episode`; `no_revisited_place_and_no_recurring_unbound`; or `no_unbound_content_in_revisited_places` (audited) |
| W_S | shot | every shot | never (at least one shot exists) |
| X_S | boundary | every boundary in `shot_transitions` | `single_shot_episode` |

**Outcome independence.** The X_U opportunity comes from the prompt's place
schedule, which is fixed before generation. It does not come from detector
identity matches.

A matched-identity definition would create a loophole. A background object
that changes completely between visits fails to match, then drops out of the
support. The cell becomes N/A and the inconsistency is never penalized.
Inconsistency would then remove itself from the test.

On the first-200 contracts, 199/200 episodes revisit at least one place, and
on average 95.7% of an episode's shots lie in a revisited place. So
structural N/A for X_U will be rare on this dataset. When it does occur, it
will mostly be an audited "the revisited place shows no unbound content",
for example extreme close-ups against a uniform backdrop.

**Prompt density shifts content between rows.** The source-derived contracts
are dense. #014 binds 12 entities, including the facade and the masonry;
p047 binds 14 objects. A large part of the background is therefore bound in
this dataset. U support per episode must be reported, and U scores from
datasets with different prompt density must not be compared without it.

### 5.3 Gates that make N/A trustworthy (discovery v3)

These gates run in the existing validation repair loop. Problems go back to
the model; no automatic normalization is applied.

1. **Binding on every V-V label.** `subject.binding` must be one of
   `prompt_bound`, `prompt_unbound` or `structure`.
   - `structure` is used if and only if the subcategory is structural.
   - `prompt_bound` needs at least one `{contract entity label, literal
     quote}` reference. The quote is checked as a substring of the prompt or
     contract. For a relation, the quote must state the relation.
   - `prompt_unbound` must cite at least one unbound-inventory subject. It
     must not cite a contract entity as the changed element.
2. **Ledger reconciliation.** Every detector `ge…` entity must be accounted
   for in one of three ways:
   - (a) it is an unbound-inventory subject;
   - (b) it is dismissed as worn by, or part of, a bound subject, with the
     wearer ID and, when stated, the quote;
   - (c) it is dismissed as a detector error, with a reason.

   This fixes the glasses/watch artefact. It also prevents a lazy "no unbound
   content" claim while unbound detections are still unexplained.
3. **Revisited-place audit.** Every revisited place gets an entry in the
   unbound continuity ledger. The entry lists its salient unbound subjects
   with per-shot signatures and an assessment
   (`consistent`/`inconsistent`/`uncertain` plus linked issue IDs). If the
   place has no unbound subjects, the entry carries an explicit
   `no_unbound_content` claim with a reason.
   - Inconsistent subjects must link issues.
   - Unbound V-V labels must be referenced by their subject.

   This copies the existing gate on the bound continuity ledger.
4. **Within-shot inventory.** Each `shot_scan` entry lists
   `bound_subject_ids` and `unbound_subject_ids` that were inspected.
5. **(Optional, phase 2) N/A claims are reviewed.** Review checks each
   `no_unbound_content` claim against the frames, like a candidate. If the
   claim is rejected, that place's U cells become `not_audited`. Without this
   step, N/A depends on one Luna/low call.

## 6. Aggregation

### 6.1 Episode level (per-video display)

```
node score = (1 / |A|) · Σ_{child ∈ A} score(child),   A = applicable (scored) children
node state = not_applicable if A is empty; else scored, flagged incomplete if any child is not_audited/failed
```

Every node displays its coverage, for example "U: 1/2 applicable".

**Effective weights when every cell applies:**

| F_B | W_B | X_B | W_U | X_U | W_S | X_S |
| --- | --- | --- | --- | --- | --- | --- |
| 1/6 | 1/12 | 1/12 | 1/6 | 1/6 | 1/6 | 1/6 |

The three pillars are equal partners by design. B splits its third between
fidelity and consistency, because intended content has two references: the
text and the video itself. Unintended content has only the second. The weights
are a stated convention, not a calibrated optimum. Section 9 lists the
sensitivity analysis.

### 6.2 Benchmark level (leaderboard) — leaf-first

1. For each model and each leaf c, compute the mean over the videos where c
   is `scored`: `S̄_c = mean_{v ∈ V_c} S_c(v)`. Report `|V_c|` next to it.
2. Apply the same tree to the leaf means to obtain B̄, Ū, S̄ and EEC.

Do **not** average per-video EEC scores. Per-video renormalization treats a
video without unbound content as neutral, so a model that often omits
unbound content would be rated on its easier remainder. Example:

| | F_B | W_B | X_B | W_U | X_U | W_S | X_S | per-video EEC |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Model X, video 1 | 80 | 100 | 75 | N/A | N/A | 100 | 100 | 91.88 |
| Model X, video 2 | 80 | 100 | 75 | 100 | 50 | 100 | 100 | 86.25 |
| Model Y, videos 1–2 (identical) | 80 | 100 | 75 | 100 | 50 | 100 | 100 | 86.25 |

The two models have identical performance on every cell they were tested on.

- Averaging per-video EEC gives X 89.06 and Y 86.25. X benefits from the
  missing U content in its video 1.
- Leaf-first aggregation gives both 86.25.

Uncertainty: report a bootstrap over videos (≥ 1,000 resamples) for each leaf
and node. If the same video was evaluated several times, either resample
videos and keep their runs together, or first take the per-video median as
the current reports do.

### 6.3 Support-normalized analysis (B vs U)

To test the scientific claim "unintended content breaks more often than
intended content", the score is the wrong statistic, because it depends on
how much content of each kind exists. Use break rates over the same audited
units:

```
r_c = Σ_v broken_c(v) / Σ_v n_c(v)
```

- **Cross-shot cells:** a unit is a ledger subject. It is broken if it links
  at least one scored event in that cell.
- **Within-shot cells:** a unit is a (subject, shot) pair cited by a scored
  within-shot event.

Compare r_{X_U} with r_{X_B} and r_{W_U} with r_{W_B}. Use only videos where
both cells are applicable (a paired comparison), with a cluster bootstrap
over videos. This gives sentences such as "x% of recurring unprompted
subjects change across shots versus y% of prompted ones". It is the clearest
way to show what the unbound evaluation adds.

## 7. Implementation plan (after confirmation)

| Step | Change | Model calls |
| --- | --- | --- |
| Discovery v3 | `prompts/vl_vv_issue_discovery_v3.txt`, `schemas/vl-vv-issue-discovery-v3.schema.json`, validators in `run_vl_vv_issue_discovery.py`. Adds `subject` binding per V-V label, `unbound_inventory` / unbound continuity ledger, `ledger_dismissals` and shot-scan subject lists. Gates 5.3.1–4. Everything else in v2 (checklist, labels, transitions) is unchanged. | Same single call; output grows (amount to be measured) |
| Review v3 | Unchanged: it judges the claim. Optional phase 2: review `no_unbound_content` claims (5.3.5). | Same |
| Scoring v5 | Same Luna/low severity and duplicate call as v4. The duplicate validator becomes cell-aware. | Same |
| `scripts/vl_vv_hierarchy.py` (new) | Deterministic. Builds cells, states, support, facets, nodes, EEC, legacy view and break-rate counts. Writes `episode_scoring/hierarchy.json` with `rule_version: eec_hierarchy_v1`. | 0 |
| `scripts/summarize_vl_vv_hierarchy.py` (new) | Leaf-first model aggregation, applicability counts, bootstrap CIs, paired break rates. | 0 |
| Results page | Scorecard and leaderboard (section 8). | 0 |
| Flags | `--discovery-protocol v3` (new default once validated); v1/v2 chains unchanged and runnable. Batch directories record the chain as today. | — |

**Historical results.** Discovery v1/v2 runs keep their legacy scores. If the
hierarchy is computed for them, U cells must be `not_audited`, never 100.
Labels must be attributed by a stated proxy:
- structural subcategories go to S;
- every other label goes to B, flagged `legacy_attribution`.

Use these only for B/S comparisons. A real U score needs a v3 discovery
rerun. That is API-only (`--mode from-registry` on the frozen registries);
re-segmented episode videos also need fresh detection.

**Validation before adoption.** Run the 14 frozen videos × 3 runs with v3,
then check:

- (a) the legacy column views behave like the v2/v4 runs;
- (b) binding accuracy, by hand-checking about 50 labels against the
  contract;
- (c) U-cell applicability and N/A reasons;
- (d) run-to-run stability per cell;
- (e) break rates B vs U;
- (f) discovery token and USD cost change, reported as standard-API
  estimates.

## 8. Presentation

**Paper.**

- *Figure (method):* the 3 × 3 matrix. Hatch the U × Fidelity cell with the
  caption "no reference text: only self-consistency can evaluate it". This
  one figure carries the motivation. Prompt-alignment metrics see only the
  F_B cell. Character-consistency metrics see mostly X_B. UEC-Bench adds the
  whole U row and separates structure failures from content consistency.
- *Main table:* rows are models. The columns are:
  - EEC;
  - B, with F_B, W_B and X_B under it;
  - **U, with W_U, X_U and applicability n/N**;
  - S, with W_S and X_S.

  Bold the U block. Put legacy V-L/V-V in the appendix.
- *Analysis figure:* paired break rates r_U vs r_B per model, within-shot and
  cross-shot, with bootstrap CIs.
- *Definitions box:* provenance rule (section 2), cell formula (section 4),
  applicability states (5.1), leaf-first aggregation (6.2).

**Webpage.**

- *Per-video scorecard:* the same 3 × 3 matrix. Each cell shows its score,
  its support n and its event count.
  - `not_applicable` cells are grey, with the reason code in plain words, for
    example "no unbound content in the revisited kitchen".
  - `not_audited` cells are striped.
  - The U × Fidelity cell is hatched.
  - Clicking a cell lists its events (issue, label, verdict, severity,
    confirmed part) and its facet factors.
  - Pillar chips show coverage, for example "U 1/2".
- *Leaderboard:* EEC, B, **U (+ n/N)**, S, with expandable leaves, sorting by
  any column, a model filter, and legacy scores in a collapsed column group.

## 9. Statistical notes and limitations

- **Not human-calibrated.** Equal weights and rubric v2 are conventions.
  Report rank stability (Kendall τ between models) under three changes:
  - leaving one pillar out;
  - EEC computed from B and U only;
  - flat leaf weights (1/7 each).
- **N/A by audit depends on the auditor.** Gate 5.3.2 (ledger
  reconciliation) and the optional review (5.3.5) limit lazy claims, but N/A
  remains a model judgment where the detector found nothing.
- **Six keyframes per shot.** Short within-shot events can fall between
  samples. This affects W_B, W_U and W_S alike.
- **Run-to-run variance.** Luna/low discovery varies between runs, as the
  2026-10-05 and 2026-10-06 reports show. The new cells, especially U, need
  their own stability check before paper claims.
- **Prompt density.** It moves content between B and U. Always publish U
  support with U scores.

## 10. Judgment calls to confirm

1. **Structure is a third pillar inside EEC, with equal weight.** It holds
   missed cuts, flashes and style switches, so that they neither inflate nor
   contaminate entity consistency. The alternative is EEC = mean(B, U) with S
   reported beside it.
2. **Intrinsic appearance of a referenced entity is B.** The alternative is
   to count every unstated attribute as U. That would move most character
   consistency into U and leave X_B almost identical to F_B.
3. **Discovery assigns the binding** inside its existing call, with
   quote-checked gates. The alternative is a separate text-only binding call
   after review.
4. **Review of N/A claims is phase 2**, not included in v1.

## 11. Owner decisions (2026-10-20)

These decisions replace the corresponding proposals above. With decisions 3
and 4 the per-issue B/U rows, their support audits and N/A machinery
(sections 2, 3, 5 and 7 as far as they concern U) are **not adopted**; the
document is kept as history. Nothing here is implemented.

1. **A missed required transition is a V-L issue** (replaces the dual
   counting in section 3). A required cut that does not happen, or a broken
   required continue, means the video did not follow the prompt's shot plan:
   V-L `shot_structure` only, not also V-V `transition_realization`. The
   current branch pipeline still reports it in both branches; changing that
   awaits the owner's go-ahead. Whether an unrequested extra cut inside a
   shot (`unintended_cut`) should also be V-L was not decided.
2. **Entity provenance is decided per entity, by mention.** An entity is
   prompt-bound if it appears in the prompt or contract (by name or by the
   role it plays) and prompt-unbound otherwise. Its attributes do not change
   this. V-L assessment is attribute-specific: only what the text states
   about an entity can be violated. (An earlier note in this section, also
   dated 2026-10-20, read the owner's answer as attribute-level binding; the
   owner corrected that reading the same day.)
3. **Detected issues are not classified as prompt-bound or prompt-unbound**
   (resolves judgment call 10.3: no per-issue binding, no quote-checked
   binding gate). The prompt's role in V-V is to decide whether a detected
   change is a real problem, so that changes the prompt allows are not
   flagged, not to categorize issues. The existing branch pipeline (V-V
   normal-change test with text-supported causes; entity register with
   per-entity provenance; scoring v5 unintentional subset) is sufficient.
4. **No review of N/A claims** (judgment call 10.4). It was proposed only as
   an optional later step for the U cells, which are not adopted.
