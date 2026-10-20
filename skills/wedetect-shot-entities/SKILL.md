---
name: wedetect-shot-entities
description: Detect all supplied shot keyframes with WeDetect-Anything and independently cluster each shot with Codex CLI, producing named candidate clusters and detector-backed per-frame boxes. Stops at within-shot clustering.
---

# WeDetect shot entities

Use `EECBench/scripts/run_wedetect_shot_entities.py` from the workspace root.
This replaces the previous ensemble entity-discovery workflow. Do not load its
skills, prompts, registry matching, verification panels, or graph partition rules.

## Orchestration

Input is a JSON manifest: `{"shots": [{"shot_id": "shot1", "frames":
[{"frame_id": 0, "path": "frames/000.jpg", "timestamp_sec": 0.0}]}]}`.
Paths are relative to the manifest; frames are in chronological order.
All shots and all supplied keyframes must be processed. Do not silently subsample.

Run on a compute node already allocated to guangyi.chen, following
`docs/cluster-runtime.md`. The runner checks allocation ownership, GPU utilization,
VRAM and KFD mappings immediately before detector launch. Use an explicit physical
GPU index. Default detector parameters and seed match the prior WeDetect study.

```
python EECBench/scripts/run_wedetect_shot_entities.py \
  --manifest /absolute/manifest.json --output /absolute/new-run --gpu 4 \
  --model gpt-6-astra --reasoning medium
```

The runner first detects all frames, then reviews shots in parallel with at most
`--shot-workers 3` independent calls (default); use `--shot-workers 1` for serial execution.
Each shot gets a fresh, ephemeral Codex CLI invocation with the same
reviewer contract, original images and only its own detections. No session resume,
other-shot results, story prompts, expected counts or legacy pipeline context.
Output is JSON validated against the schema and provenance checks. A failed shot
stops scheduling new shots; already running isolated calls finish and the run is
marked failed. Do not fabricate results or retry invisibly.
`--prepare-only` stages requests without Codex calls. `--detections PATH` explicitly
reuses a completed WeDetect run after checking exact shot/frame coverage and image
hashes. Reuse is recorded, never represented as new inference.

Optional downstream stage: `--spatial-relations` runs one fresh spatial-relation
subagent per shot only after ALL entity reviews succeed. The entity reviewers
still stop at clustering. The downstream stage receives frozen entities and that
shot's original keyframes, uses the shared spatial_v0.1 vocabulary/evidence rules,
and writes `spatial_relations/shots/<shot_id>/relations.json` plus `graph.json`.
To test relations using an already completed entity run without rerunning discovery:
`python EECBench/scripts/run_shot_spatial_relations.py --entity-run RUN --output NEW_RUN`.
See `EECBench/docs/spatial-relations-v0.1.md` for predicate definitions and limits.

## Reviewer contract

The runner sends [review_prompt.txt](review_prompt.txt) and a compact candidate
payload to each isolated reviewer. That file contains the complete identity,
same-category collection, constituent-merging, naming and rejection rules. Read it when reviewing candidates
or changing those rules. Operational instructions in this file are not sent to
reviewers.

The refined 2026-09-20 rule keeps clearly distinguishable individual objects
separate, including adjacent cups. Merge only genuine multi-item aggregates
such as a basket/pile of oranges or a bunch of pens in one holder; proximity or
same category alone is insufficient. Containers remain separate. See the
individual/collection criteria in review_prompt.txt. Preserve original candidate
ownership, box scopes and independent per-shot contexts.

The wire input uses short integer candidate IDs and a label dictionary; all box
coordinates, scores, frame times and original images retain their values. The
wire response follows [wire.schema.json](wire.schema.json). The runner restores
original candidate IDs, assigns entity IDs, and validates the canonical response
against [output.schema.json](output.schema.json). Missing/duplicate/unknown IDs
or invented fields fail validation. Full canonical input, ID mapping, wire input,
wire response and canonical response remain in the run record.

### Detector-backed observations

The runner materializes one observation per supplied frame in input order:

- With assigned candidates: use the highest-confidence candidate's original box
  unchanged. Break score ties by ascending candidate ID. Preserve all assigned
  candidate IDs and the selected `box_candidate_id`; do not union, average,
  smooth or expand boxes. Collection and constituent merges affect identity grouping only. A selected
  member box is not a whole-collection box; all member candidate IDs remain
  available with their original boxes in the canonical input.
- Without assigned candidates: `box_xyxy=null`; do not propagate another frame's
  box. No candidate can be added to a different frame.
- `visible` is derived as `box_xyxy != null` and means a retained detector
  observation is available. False is not proof of physical invisibility.
- `exist=true` for a retained observation and `exist=null` otherwise. Null means
  unknown: missing detection does not establish absence or continued presence.
- The runner derives `exist_frame_ids` (positively observed frames),
  `visible_frame_ids` and `boxes_by_frame`. Unlisted frames have unknown
  existence, not a negative existence verdict. These fields cover only supplied
  keyframes and are not part of the model response.

Original images support identity, naming and false-positive review; they do not
supply new box coordinates. Stop at within-shot clustering. Do not output
cross-shot identities, relation graphs, prompt-bound classification or scores.
