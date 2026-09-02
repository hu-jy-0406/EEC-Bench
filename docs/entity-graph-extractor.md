# Shot entity-graph extractor

`scripts/extract_shot_entity_graph.py` converts one video shot into the v0.1
open-vocabulary semantic observation graph. It samples reference frames, invokes
Codex CLI with a strict JSON output schema, and then uses GroundingDINO to add
normalized bounding boxes on the frames that support each entity.

## Requirements

- Codex CLI is installed and already authenticated (`codex login status`).
- The Python environment provides Pillow and NumPy. System `ffmpeg`/`ffprobe`
  are preferred for sparse decoding; imageio with a video backend is the fallback.
- Full grounding additionally requires the existing EECBench GroundingDINO and
  CLIP dependencies and checkpoints. On this AMD cluster, follow `AGENTS.md`: run
  GroundingDINO only inside an owned allocation on a verified-idle GPU, normally
  using the `vace` environment. The evaluator automatically selects its PyTorch
  MSDA fallback on ROCm and installs its process-local Transformers 5.x
  compatibility shims, so the normal extractor command needs no compatibility
  exports. Before importing PyTorch, it also assigns both MIOpen caches to a
  writable node-local `/tmp/eecbench-miopen-<uid>` directory unless the caller
  explicitly configured another cache.

The script reads the existing `GDINO_CONFIG`, `GDINO_WEIGHTS`, and
`GDINO_TEXT_ENCODER_PATH` variables through EECBench's evaluator adapter. It
does not require them when the standard models are already cached. These
variables remain available for pinned/offline runs. `GDINO_MSDA_BACKEND` can
still explicitly request `pytorch`; its default `auto` mode selects that backend
on ROCm. The script does not read or copy API keys. Codex uses the user's
existing CLI login.

## Episode-folder batch run

`scripts/extract_episode_entity_graphs.py` is the normal entry point when an
experiment directory contains one complete episode under `shots/`. It discovers
common video formats, sorts filenames naturally (`shot2` before `shot10`), and
runs the single-shot extractor strictly in that order.

From the `EECBench` directory:

```bash
python scripts/extract_episode_entity_graphs.py experiments/study --device cuda
```

Full GroundingDINO/CLIP execution must be launched from a verified-idle GPU in
an allocation owned by `guangyi.chen`, following the workspace cluster policy.
The command creates this layout without modifying the source `shots/` folder:

```text
experiments/study/
  shots/
  entity_graphs/
    SHOT.entity_graph.json
  reference_frames/
    SHOT/frame_XXXXXX.jpg
  grounding_results/
    SHOT/frame_XXXXXX.grounded.jpg
    SHOT/contact_sheet.png
  logs/
    entity_graph_episode_YYYYMMDDTHHMMSSZ.log
```

The original sampled JPEGs are retained in `reference_frames/`; exact boxes are
drawn independently into `grounding_results/`. Each final entity also contains
`reference_grounding`, a one-to-one expansion of its selected grounding boxes:

```json
{
  "frame_id": 72,
  "reference_frame_path": "/absolute/path/to/frame_000072.jpg",
  "bbox_xyxy_normalized": [0.1, 0.2, 0.5, 0.8],
  "score": 0.73
}
```

The episode log is written incrementally. It records the UTC start/end time,
top-level command, exact per-shot extractor command, per-shot and total runtime,
per-shot and total Codex token usage, output paths, frame/detection counts, and
success or failure status. Existing shot outputs are protected by default; use
`--overwrite` only when they should be replaced. Run `--help` for model,
threshold, sampling, directory-name, and explicit log-path options.

## Full run

From the `EECBench` directory:

```bash
python scripts/extract_shot_entity_graph.py \
  /path/to/shot.mp4 \
  --output /path/to/shot.entity_graph.json \
  --video-id episode_001 \
  --shot-id shot_003 \
  --device cuda
```

After the validated graph is written, the same command automatically creates
OUTPUT_STEM.annotated.mp4. GroundingDINO only evaluates sampled reference
frames. The annotated video therefore shows detector scores on those exact
frames and labels linearly interpolated boxes between adjacent detections with
interp. Interpolation is visualization-only and is never written back into the
graph JSON. It is suppressed when an intervening reference frame has an
explicit detector miss or when the endpoint box areas differ by more than 8x.

Grounding candidate post-processing follows EntityBench. The extractor first
validates every threshold-passing GroundingDINO candidate and rejects malformed
or out-of-frame boxes. It does not cap or NMS the valid candidate list before
scoring. Each candidate is padded by 10%, cropped, and scored with the same
EntityBench components:

```
selection = CLIP(query, crop)
            * sigmoid(crop_sharpness; midpoint=100, scale=200)
            * sigmoid(crop_area_pct; midpoint=2, scale=5)
```

EntityBench chooses one canonical crop across all sampled frames. The entity
graph must retain a box for each semantic evidence frame, so it applies that
same score independently within each evidence frame and keeps the highest-score
candidate there. Strict ties keep the first detector candidate, matching
EntityBench's update rule. The v0.1 graph's existing
`grounded`, `partially_grounded`, and `not_found` status definitions are not
changed by this candidate-selection replacement.

The current path deliberately performs no temporal-support scoring, cross-entity
IoU competition, joint assignment, or unique-outlier rescue. Consequently two
different entity queries can select the same box, just as EntityBench evaluates
its scheduled entities independently. The selector is recorded as
`entitybench_clip_quality_v1_per_frame`. Key defaults are
`--box-threshold 0.25` and `--text-threshold 0.20`.

Use --annotation-box-mode exact to draw only real reference-frame detections,
--annotated-video PATH to choose another MP4 path, or --skip-annotated-video
to disable automatic rendering.

An existing graph can be rendered without repeating Codex or GroundingDINO:

~~~bash
python scripts/render_entity_graph_video.py \
  /path/to/shot.mp4 \
  /path/to/shot.entity_graph.json \
  --output /path/to/shot.entity_graph.annotated.mp4
~~~

The renderer prefers system ffmpeg/ffprobe. On compute nodes where those
commands are absent from PATH, it automatically uses the ffmpeg binary and
metadata reader bundled with the vace environment's imageio-ffmpeg package.

The default invocation supplies six frames to an ephemeral, read-only
`codex exec` session and inherits the model from the current Codex config. Use
`--codex-model MODEL` only when a run must pin an explicit available model.
After a Codex-backed run, the command prints a summary such as
`Codex token usage: input=1234, cached_input=0, output=456, total=1690`.
The same values are saved in
`extraction_metadata.codex_token_usage` in the output JSON. Cached input is a
subset of input tokens and is therefore not added to `total` a second time.
When `--semantic-json` bypasses Codex, the saved usage value is `null`.

To keep the sampled evidence frames for auditing:

```bash
python scripts/extract_shot_entity_graph.py shot.mp4 \
  --keep-reference-frames outputs/shot_frames \
  --output outputs/shot.entity_graph.json
```

## CPU/schema smoke test

This runs Codex but deliberately does not load GroundingDINO:

```bash
python scripts/extract_shot_entity_graph.py shot.mp4 \
  --skip-grounding \
  --output outputs/shot.semantic_only.json
```

To reuse a previously saved Codex semantic response and resume only the
grounding stage:

```bash
python scripts/extract_shot_entity_graph.py shot.mp4 \
  --semantic-json saved_codex_semantics.json \
  --output outputs/shot.entity_graph.json
```

`--semantic-json` must follow
`schemas/codex_shot_semantics_v0.1.schema.json`. Final output follows
`schemas/shot_entity_graph_v0.1.schema.json`.

## Failure behavior

The command exits nonzero instead of silently degrading when Codex fails,
returns malformed or dangling graph entries, video timing is unavailable, or
GroundingDINO cannot load. A detector miss is not an infrastructure failure: the
entity remains in the graph with `grounding.status="not_found"` and no boxes.
The script never interprets a missing relation as a negative relation.
