# Prompt entity binding and schedule v1

User-authorized 2026-09-21. Supply an episode-level prompt registry and shot schedule before evaluation, then bind frozen global visual records after final identity review. Binding does not change discovery, identity, motion, registration or original score gates.

## Input contract

`--prompt-registry PATH` accepts `schema_version: prompt_registry_v1`, ordered `shot_ids`, and `entities`. Each entity has a unique `prompt_entity_id`, `name`, `description`, `evidence: [{fact_id, quote}]` referencing exact substrings of the supplied normal narrative facts, and one `schedule` row per shot in manifest order. Each row contains `shot_id`, `expectation` (`required`, `not_required`, `forbidden`, `unknown`) and a nonempty `reason`.

`required` means expected to appear during the shot, not visible at every sampled frame. `not_required` means no required observation, not physically absent. `forbidden` records a supplied constraint, not an evaluator verdict. Registry entities are physical instances; clothing/body parts described as attributes and scene context do not automatically become independent entities. Preexisting EntityBench-style metadata should be converted explicitly to this contract, retaining source evidence; this is not an automatic parser for every external schema.

The runner validates and copies this input before launching discovery. Missing input leaves binding explicitly `not_run`; it must never silently classify everything unbound. No registry/schedule is automatically invented for production runs. Study3's user-requested fallback fixture is derived from normal narrative only, with provenance and limitations.

## Placement and evidence

`global_entity_table → prompt_binding` reserves one API slot. One isolated configured GPT-6 Astra/medium call receives all episode global entities with local names, original per-frame 2D boxes, frozen registry/schedule, and every original supplied keyframe. No anomaly scores, intended test errors, geometry fitting outcomes or appearance verdicts enter this call. Original files and request hashes are saved. No image sampling, rewriting boxes, external upload destination change or user configuration change.

Output is a sidecar `prompt_binding/results.json` and readable `bindings.md`. Each global record has `bound`, `unbound` or `unknown`, one confirmed prompt ID only for bound, candidate IDs for unknown, original-frame witnesses, prompt fact references and a reason. Inventory coverage, witness membership, fact references and competing same-shot assignments are validated. Nonliteral appearance drift alone does not make a bound entity unbound. Collection/instance scope uncertainty remains unknown.

Prompt correspondence does not create visual identity edges. Multiple global records in different shots/scenes can correspond to one prompt ID; their visual records remain separate. Existing ambiguous links remain unresolved. Episode-level membership is independent of schedule; an unscheduled appearance may still be bound.

## Schedule and scores

The output retains all prompt entries, including those with no bound visual counterpart, and all scheduled shot rows. Per-shot matched and candidate global records are listed; no match means `observation: unknown`. `schedule_assessment` remains `not_evaluated`. This stage does not infer absence or implement schedule-compliance/prompt-fidelity scores.

Full runs append `prompt_binding_report` after BOTH binding and appearance report. It partitions unchanged v6 appearance entity scores by binding status: original RMS-deficit aggregate, auxiliary arithmetic mean, separate DINO mean, explicit null counts and record IDs. Counts are frozen visual records, not deduplicated prompt IDs. These conditional appearance groups are **not complete SB/SU**. Existing spatial/presence scores retain their populations; this change does not introduce mixed-pair attribution or a new total score.

Binding may overlap appearance/boundary computation. Identity/presence/spatial early stops include binding when explicitly supplied, but do not add appearance. Historical Flow1 rejects this new option. Existing runs without a registry retain the previous execution plan.

## Commands

```bash
# Add to the current temporal_v2 integrated invocation:
--prompt-registry /absolute/path/prompt_registry.json

# Test the new stage on a completed audited run; no GPU/front-end rerun:
python EECBench/scripts/gs_prompt_binding.py run \
  --case EXISTING_CASE --registry REGISTRY.json --out NEW_BINDING_DIRECTORY
python EECBench/scripts/gs_prompt_binding.py report \
  --binding NEW_BINDING_DIRECTORY/results.json \
  --appearance-csv EXISTING_CASE/appearance/report/entities.csv \
  --out NEW_BINDING_DIRECTORY/appearance_groups.json
```

Run CPU/API work on a low-load node in an existing owned allocation. No new GPU required. Save successful/failed call records and account API usage once from `prompt_binding/calls/*/status.json`. Standard API equivalents use existing pipeline pricing; they are not actual billed amounts.

Validation: [Study3 report](../experiments/prompt_binding_study3_20260921/REPORT.md). This is a fresh binding component call on frozen frontend/identity results, not a new full evaluation or independent human calibration.


## Comparison evidence extension — 2026-09-21

User-authorized witness protocol `own_and_comparison_v2`: `witnesses` retains own positive frames. New `comparison_witnesses` rows explicitly name another frozen `global_entity_id`, `shot_id`, and `frame_id`; that entity must actually have a positive observation in the cited frame. Cross-shot/cross-scene contrasts may explain a bound/unbound/unknown decision. They do not create a current-entity occurrence or identity edge, and cannot replace own positive evidence for bound. Model input explicitly lists positive observed_frame_ids. No additional verifier or model call.

Old saved bindings without the new field remain valid with an empty comparison list. Cross-entity frames must be explicitly attributed in new output; do not silently infer a comparison identity from a shared frame.34tests pass. The diagnosed Study3 table comparisons pass in an explicitly attributed test fixture; historical raw responses/scores remain unchanged. Validation adds0tokens/USD0API; a fresh model/whole-pipeline run with this extended schema has not been performed.

## Conditional output schema and failure accounting — 2026-09-22

Production requests now use `gs_prompt_binding.OUTPUT_SCHEMA`, with disjoint
`anyOf` row variants for the existing three binding states:

| State | prompt_entity_id | candidate_prompt_entity_ids | fact_ids | Own witnesses |
|---|---|---|---|---|
| bound | Nonempty string | Empty | Nonempty | Nonempty |
| unbound | null | Empty | Empty | Existing witness rules |
| unknown | null | May list candidates | Empty | Existing witness rules |

This promotes the schema already exercised in the Study4 recovery; it does not
alter the decision prompt, scoring, or `materialize` semantic gates. `fact_ids`
assert support for a confirmed correspondence, while uncertain alternatives use
candidate IDs and the reason. The former request schema permitted combinations
that the semantic validator rejected, including unknown rows carrying fact IDs.
The structural `SCHEMA` remains available to legacy readers and downstream
alignment; old bindings without comparison witnesses retain existing support.

The call validates the raw response against its actual request schema before
recording success. Explicit schemas supplied by alignment/compiler callers are
retained. Binding then validates inventory, witness ownership, valid IDs,
instance competition and frozen sources. A failure at either layer is recorded
as `status=failed`, with `validation_phase`, `validation_status`, and the actual
transport status. Raw responses and usage are retained without auto-editing
fields or adding retries/model calls. Schema constraints address this field
combination bug; visual uncertainty and semantic evidence still need validation.

Regression and fresh production-entrypoint validation:
`experiments/prompt_binding_schema_fix_20260922/REPORT.md`.
