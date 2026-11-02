# Spatial relations v0.1

This downstream stage runs AFTER frozen WeDetect/Codex entity discovery. Each
shot gets one independent, tool-free, ephemeral Codex CLI subagent with only its
own original keyframes and existing entities. It cannot change the inventory,
boxes or visibility, or see another shot's output. Defaults match discovery:
gpt-6-astra, medium reasoning, at most three concurrent shot subagents.

## Fixed vocabulary and granularity

| Predicate A → B | Required meaning | Reference |
|---|---|---|
| supported_by | B directly bears A's gravitational load through contact | intrinsic |
| inside | A's main body occupies B's actual containing interior | intrinsic |
| attached_to | A is fixed/fastened/connected to mounting entity B | intrinsic |
| touching | Direct physical surface contact; symmetric, canonical entity order | intrinsic |
| above | Direct vertical alignment along identifiable gravity, with a gap | gravity |
| in_front_of | Overlapping projected regions with evidence A is nearer than B | current camera |

Use the same definitions for every entity pair in every shot. No top-K selection,
human-only pairing, new endpoint, constituent-level scope, indirect support,
transitive closure, inverse aliases or typical-scene guesses. Contact can coexist
with support/attachment; containment can coexist with support. Name and bounding
box alone do not establish any predicate. Image left/right, vague near/far and
actions are outside v0.1. Camera depth order is not a camera-invariant consistency
judgment. "Intrinsic" describes the predicate's meaning, not proof of geometry.

This deliberately bounded vocabulary is an UEC-Bench pilot design, not a verbatim
SVG2 taxonomy. SVG2 motivates separating spatial from non-spatial extraction:
https://arxiv.org/html/2602.23543v1#A1.SS3 . Definitions are frozen before the pilot;
same vocabulary and rules constrain granularity but do not prove reproducibility.

## Evidence and outputs

The runner enumerates all unordered entity pairs. Those with no jointly visible
keyframe are recorded as `unobservable_pairs`; every other pair requires one
`pair_review`: `relations_found`, `none_supported` or `insufficient_evidence`.
The reviewer considers all six predicates and both applicable directions.
The ledger verifies pair coverage, not that every predicate was correctly judged.

Each emitted edge has subject_id, predicate, object_id and one observation per
input keyframe: frame_id, status, reason. Status is present, absent, uncertain or
not_observable. At least one frame must be present. Both endpoints must be visible
for the first three states. Hidden contact surfaces or uncertain depth require
uncertain even if both entities are visible. If either endpoint is not visible,
not_observable is mandatory; no assumed persistence. Absent requires affirmative
evidence that that particular predicate is false. No interpolation between samples.

The final `relations.json` adds canonical relation_id, reference_frame, the four
status frame-ID lists, source hashes, unobservable_pairs and coverage counts.
`graph.json` combines a copy of the frozen nodes with these edges and pair reviews.
Its node summaries use the current boxes_by_frame format. The upstream historical
files remain untouched. Raw `response.json`, exact prompt/input, schema, CLI
request/events, usage/status and source/code snapshots are retained for audit.

Missing edges and none_supported are NOT negative evidence. Uncertain-only
predicate candidates are not full edge records in v0.1; their pairs remain in the
ledger. This sparse graph alone cannot score every disappearance of a relation.
No cross-shot identity, prompt alignment or consistency scores are produced.

## Run

Use an existing owned compute allocation after checking CPU load; no GPU required
when consuming an existing entity run.

```bash
python EECBench/scripts/run_shot_spatial_relations.py \
  --entity-run /absolute/completed-entity-run \
  --output /absolute/new-spatial-run --shot-workers 3
```

Alternatively add `--spatial-relations` to run_wedetect_shot_entities.py. The stage
starts only when all entity outputs validate. `--prepare-only` on the standalone
entrypoint prepares inputs with zero model calls. A failed call/validation is
recorded and fails the batch; inflight calls finish, no hidden retry is performed.
