# Prompt-bound / prompt-unbound entity separation

The original first-version extractors remain unchanged:

- `scripts/extract_shot_entity_graph.py`
- `scripts/extract_episode_entity_graphs.py`

Two new episode-level entry points implement the two separation orders. Both
expect `EXPERIMENT_DIR/shots/` and default to
`EXPERIMENT_DIR/entity_schedule.json`. A full EntityBench script JSON can be
passed with `--schedule-file`; when it also contains `entity_descriptions`, the
registered descriptions are used as GroundingDINO queries. Otherwise the
scheduled entity name is the query.

Schedule keys are sorted numerically (`1:1`, `2:1`, ..., `10:1`) and paired
with naturally sorted shot filenames. Use `--shot-keys 1:1,1:2,2:1` when a
dataset needs an explicit mapping. A count mismatch is a hard error.

## Pipeline 1: full graph, then post-hoc separation

From the `EECBench` directory, inside an owned Slurm allocation on a verified
idle GPU:

```bash
python scripts/run_prompt_unbound_posthoc.py experiments/study --device cuda
```

This entry point runs the original episode graph extractor into a new,
timestamped run directory. It then independently grounds every scheduled
prompt-bound entity on every reference frame with the EntityBench
GroundingDINO + CLIP/quality selector. Full-graph entities and scheduled
entities are matched one-to-one using normalized name evidence and same-frame
box IoU. The final derived graph retains only unmatched graph entities and
relations whose two endpoints were retained.

To classify already-generated v1 graphs without repeating Codex or the first
grounding pass:

```bash
python scripts/run_prompt_unbound_posthoc.py experiments/study \
  --reuse-graphs-dir /path/to/entity_graphs \
  --reuse-reference-frames-dir /path/to/reference_frames \
  --device cuda
```

The default output layout is:

```text
experiments/study/prompt_unbound_posthoc/run_TIMESTAMP/
  codex_prompts/
  total_entity_graphs/
  prompt_bound_entity_graphs/
  prompt_unbound_entity_graphs/
  total_entity_grounding_results/SHOT/
  prompt_bound_entity_grounding_results/SHOT/
  prompt_unbound_entity_grounding_results/SHOT/
  prompt_bound_detections/
  separation_audits/
  reference_frames/
  run.log
  run_manifest.json

  # Original v1 intermediate artifacts are also retained.
  full_entity_graphs/
  full_graph_grounding_results/
  v1_logs/
```

`codex_prompts/` contains the complete v1 prompt that asks Codex to discover
all visible entities and construct the full graph, including the per-shot
frame/timestamp mapping.

## Pipeline 2: prompt-bound grounding, then focused Codex extraction

From the `EECBench` directory, under the same GPU-safety conditions:

```bash
python scripts/run_prompt_unbound_prefilter.py experiments/study --device cuda
```

This entry point samples the frames once, grounds the scheduled prompt-bound
entities first, and injects both their registry descriptions and detector
observations into a dedicated Codex prompt. Codex is instructed to emit only
extra physical entities and relations between those extras. Its output is then
grounded with the same first-version EntityBench-style selector. A deterministic
one-to-one post-check removes any leaked prompt-bound entity before the final
graph is written.

The default Pipeline 2 prompt is
`prompts/shot_prompt_unbound_entity_graph_v0.2.md`. It treats prompt-bound
registry membership as authoritative but GroundingDINO boxes as fallible
localization hints rather than exclusion masks. Codex first forms a high-recall
cross-frame inventory, explicitly revisits major support/container regions and
the neighborhoods of detector boxes, and only then removes the actual
prompt-bound instances. In particular, a prompt-bound location excludes the
scene node, not the desk, furnishings, fixtures, or movable contents inside it.
The earlier v0.1 template remains in the repository to reproduce prior runs.

### Optional same-shot Codex ensemble

Pipeline 2 keeps the single-call v0.2 extractor as its default for backward
compatibility. Enable the repository-local
`$ensemble-shot-entity-detection` protocol explicitly when higher recall and
an auditable same-shot review are wanted:

```bash
python scripts/run_prompt_unbound_prefilter.py experiments/study_inconsistent_2 \
  --entity-detection-mode ensemble \
  --ensemble-max-workers 4 \
  --ensemble-shuffle-seed 1729 \
  --codex-timeout-sec 1800 \
  --device cuda
```

For each shot, Python launches four isolated detector calls with fixed
complementary scan orders. It then starts one persistent adjudicator: Phase A
creates a blind inventory and Phase B resumes the same Codex thread with only a
shuffled anonymous proposal union. Python restores source identities only after
the decisions are written and hashed. This is a verified union rather than
majority voting, so a visually confirmed singleton can survive and a repeated
unsupported proposal can still be rejected.

Detector independence is enforced with separate ephemeral Codex threads.
Adjudicator source blinding is currently a procedural prompt boundary, not an
OS-level filesystem read allowlist; the per-shot manifest records this
limitation explicitly. The reversible source map is nevertheless kept only in
Python memory and is not written until the adjudicator decisions are frozen and
hashed.

Every detector call uses a distinct output path. Codex JSONL events and stderr
are captured under `codex_attempts/` and are not copied to normal stdout. A
failed detector is retried once with the same role. Fewer than four valid
ledgers marks the shot and top-level run `incomplete`, skips adjudication and
GroundingDINO for that shot, emits no ensemble `final_semantics.json`, and
returns exit code 2.

The ensemble is strictly per-shot: another shot, its entities, and any expected
cross-shot agreement are never shown to detectors or the adjudicator. It
extracts entity nodes only, so its semantic `relations` array is empty.
GroundingDINO still runs once afterward on the accepted prompt-unbound entity
set; all existing graph and rendered-grounding outputs remain unchanged.

Additional per-shot artifacts are stored at:

```text
ensemble_detection/SHOT/
  run_manifest.json
  input_bundle/
    shot_manifest.json
    prompt_bound_registry.json
    frame_*.jpg
  detector_runs/
    detector_1_left_foreground.json
    detector_2_right_background.json
    detector_3_temporal_support.json
    detector_4_reverse_periphery.json
  codex_attempts/
    *.json
    *.events.jsonl
    *.stderr.log
  adjudication/
    adjudicator_blind.json
    anonymized_candidates.json
    source_map.json
    adjudicator_decisions.json
    ensemble_audit.json
  final_semantics.json
```

The default output layout is:

```text
experiments/study/prompt_unbound_prefilter/run_TIMESTAMP/
  reference_frames/
  prompt_bound_detections/
  codex_prompts/
  codex_raw_semantics/
  separation_audits/
  total_entity_graphs/
  prompt_bound_entity_graphs/
  prompt_unbound_entity_graphs/
  total_entity_grounding_results/SHOT/
  prompt_bound_entity_grounding_results/SHOT/
  prompt_unbound_entity_grounding_results/SHOT/
  run.log
  run_manifest.json
```

In both pipelines, every `*_entity_grounding_results/SHOT/` directory contains
all sampled keyframes with exact boxes (`frame_*.grounded.jpg`), a
`contact_sheet.png`, and `grounding_manifest.json` with frame/detection counts
and the source graph path. The unannotated keyframes remain in
`reference_frames/SHOT/`.

The prompt-bound graph is constructed from the frozen schedule plus positive
EntityBench-style detections. A scheduled entity with no positive box is not
fabricated as a visual graph node: it remains in
`prompt_bound_detections/SHOT.prompt_bound.json` with `status=not_found`, and
the graph warning names it. The prompt-bound graph intentionally contains no
relations because the scheduled grounding pass detects nodes, not semantic
edges.

Pipeline 2's total graph is the union of its schedule-grounded prompt-bound
graph and Codex-discovered prompt-unbound graph. It preserves relations among
unbound entities, but contains no bound-to-unbound cross-set relations because
the Pipeline 2 Codex prompt deliberately excludes prompt-bound nodes. This
limitation is also written into every total graph's warnings.

## Matching and accounting contract

The default one-to-one matcher accepts one of three auditable conditions:

1. normalized entity-name similarity is at least `0.88`;
2. name plus mean same-frame DINO-box IoU reaches the configured thresholds;
3. mean same-frame DINO-box IoU is at least `0.80`, catching a renamed visual
   instance.

All pairwise scores, selected matches, unmatched schedule entities, and final
unbound IDs are written to `separation_audits/`. Thresholds can be changed with
`--name-match-threshold`, `--box-iou-threshold`, and
`--combined-threshold`; do not tune them on the clips ultimately being scored.

Both pipelines update `run.log` and `run_manifest.json` after every completed
stage and shot. They record wall-clock duration per shot and per stage, exact
GroundingDINO call counts, per-shot Codex input/cached-input/output/total tokens,
and aggregate Codex tokens. GroundingDINO and CLIP use no language-model tokens.
If Codex does not report usage, the corresponding values remain `null` rather
than being converted to zero.
