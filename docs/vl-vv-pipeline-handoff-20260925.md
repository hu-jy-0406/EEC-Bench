# V-L / V-V evaluation pipeline handoff — 2026-09-25

**Current operational map (2026-09-26):** See
`docs/vl-vv-pipeline-current-20260926.md` and
`scripts/run_vl_vv_pipeline.py` for the integrated four-stage entrypoint.
This handoff preserves the 2026-09-25 experiment history; its later sections
predate the current issue-discovery prompt and scoring v2.

This document transfers the active task to a new agent. Read the repository-level
`AGENTS.md` first, then read this document before making changes or running
experiments. In particular, comply with the existing Slurm/GPU safety rules and
do not expose API credentials.

**2026-09-25 later update:** The fourth scoring agent is implemented in
`scripts/run_vl_vv_episode_scoring.py`, with
`skills/vl-vv-episode-scorer/SKILL.md` and
`docs/vl-vv-episode-scoring-v2.md` (penalty rubric v2). The original v1
ten-episode, three-model scores remain at
`experiments/vl_vv_episode_scoring_20260925/REPORT.md`; v2 results are tracked
separately under `experiments/vl_vv_episode_scoring_penalty_v2_20260925/`.
Statements below about scoring not yet being implemented describe the earlier
handoff state.

## Active user goal

The project evaluates multi-shot video generation along two independent axes:

1. **Video-language (V-L):** whether each generated shot follows the episode
   prompt and its entity schedule.
2. **Video-video (V-V):** whether the generated video remains internally
   consistent, both within a shot and across shots.

The intended final system has four GPT-6 Luna low agents:

1. **Detector agent** — implemented and tested.
2. **Problem-discovery agent** — implemented and tested.
3. **Problem-review agent** — implemented; not yet run on the four-model candidate set.
4. **Scoring agent** — not yet implemented.

All new agent calls in this pipeline must use the deployed OpenAI API path, not
the interactive Codex CLI. Use `scripts/openai_api_env.sh` to load the existing
non-repository key and route requests. Do not read, echo, copy, or commit the
key. The selected model is `gpt-6-luna` with reasoning `low`.

## User decisions that must be preserved

- A fixed episode `contract.json` contains the entity schedule. It must include
  cross-shot instance IDs, so the schedule can explicitly say that an entity in
  Shot1 and an entity in Shot2 are the same instance.
- Every detected entity is either **prompt-bound** or **prompt-unbound**;
  there is no `prompt_unknown` category.
- In each shot, bind WeDetect clusters to the fixed schedule before downstream
  matching. For a scheduled bound entity that has no cluster, run **one
  targeted Grounding DINO pass** over that shot's keyframes. Do not re-run
  WeDetect for that recovery. Record detections directly; do not use a second
  Luna call to audit Grounding-DINO candidates.
- The user deliberately rejects manual correction of pipeline decisions. Report
  raw pipeline results, preserve failures and diagnostic artifacts, and never
  exclude a bad anchor or alter entity identity because an expected answer is
  known.
- A problem found by the discovery agent is a **candidate**, not a verified
  inconsistency. Do not turn candidate count directly into a final benchmark
  score before review and scoring are implemented.
- Keep the older geometry/registration pipeline intact as a historical,
  separately governed pipeline. The new agentic V-L/V-V pipeline is not a
  change to its frozen scoring rules.

## Implemented detector agent

Main entrypoint: `scripts/run_vl_vv_detection.py`.

For every shot it:

1. Uses six extracted keyframes.
2. Runs WeDetect-Anything independently on every keyframe.
3. Sends only that shot's detector results and its six frames to GPT-6 Luna low
   for within-shot entity clustering. A local entity records category, short
   description, owned original boxes and frame IDs.
4. Uses the contract entity schedule to label local entities prompt-bound or
   prompt-unbound, and identifies required scheduled instances that lack an
   observation.
5. Runs direct targeted Grounding DINO for those gaps. Recovered boxes retain
   their detector/frame provenance.
6. Performs one cross-shot GPT-6 Luna low matching call to create global entity
   groups. Each group contains one or more `(shot_id, local_entity_id)` members,
   is bound/unbound, and retains links to local/frame boxes.
7. Computes independent DINO appearance evidence and attaches it to the entity
   registry. This is not yet used to produce a final benchmark score.

Canonical per-episode output: `episode_entities.json`. Its top-level
`prompt_bound`, `prompt_unbound`, `unresolved_identity_links`, `counts`, and
`limitations` fields are the current output contract. The schema is
`schemas/vl-vv-episode-entities-v1.schema.json`.

Relevant implementation and documentation:

- `scripts/run_vl_vv_detection.py`
- `scripts/run_vl_vv_issue_discovery.py`
- `scripts/gs_prompt_binding.py` — supports same-conversation
  `previous_response_id`
- `scripts/eec_api_codex_shim.py` — API transport, including
  `--previous-response-id`
- `prompts/vvvl_global_entity_match_v1.txt`
- `prompts/vvvl_global_entity_match_revise_v1.txt`
- `docs/vl-vv-detection-agent-v1.md`
- `docs/vl-vv-issue-discovery-agent-v1.md`
- `skills/vl-vv-detector-agent/SKILL.md`

### Exact-once global identity invariant and the new repair loop

Every eligible shot-local entity must appear **exactly once** in global matching:
it cannot be assigned to two global groups, cannot be missing, and no unknown
local ID may be invented. A global group is a candidate global entity identity.

The original approach asked Luna to rewrite the whole match JSON after a failed
audit. It caused repeated new conflicts. The current implementation is the
user-approved replacement:

1. Ask for a complete initial grouping, with the full local-entity inventory.
2. Run `ownership_problems()` in `run_vl_vv_detection.py`; it emits only
   `duplicate`, `missing`, and `unknown` local IDs.
3. If there are problems, call the **same API conversation** with
   `previous_response_id`, no images, and only those problematic IDs plus their
   allowed target groups.
4. The model outputs only patch rows, using
   `keep_existing`, `assign_existing`, `new_singleton`, or `remove_unknown`.
5. `apply_ownership_repairs()` validates that exact problem-key set and applies
   changes only to those IDs. Unrelated group membership, labels, descriptions
   and reasoning remain unchanged. Re-audit and repeat at most eight times.

Artifacts are saved under `global_match/`, including `raw_model_result.json`,
per-attempt patch/audit data when needed, `result.json`, and
`exact_once_audit.json`. This is a real local patch loop, not a prompt-only
request to rewrite the whole file.

The skill prompt was strengthened to say explicitly: each candidate ID must be
bound to one and only one global entity; no legal candidate can be omitted;
repair calls may modify only listed IDs.

Validation already completed:

- `quick_validate.py skills/vl-vv-detector-agent` passed.
- Python compilation for the changed scripts passed.
- A focused duplicate/missing/unknown local-repair test passed and confirmed
  unrelated group fields remained unchanged.

## Implemented problem-discovery agent

Entrypoint: `scripts/run_vl_vv_issue_discovery.py`; normally invoked by
`run_vl_vv_detection.py` as the final stage.

It receives all 6 keyframes for every shot, the original prompt, `contract.json`
and `episode_entities.json`. It returns
`issue_discovery/result.json`, conforming to
`schemas/vl-vv-issue-discovery-v1.schema.json`, with:

- `v_l_inconsistencies`
- `v_v_inconsistencies.within_shot`
- `v_v_inconsistencies.cross_shot`

Each issue contains a concise description, evidence, prompt evidence when
applicable, scope, affected entity IDs, `entity_self` versus `entity_relation`,
subcategory, and confidence. The prompt explicitly asks the model to inspect
appearance, presence, spatial/interaction relations, nonadjacent same-scene
shots, character identity, held objects, scene layout and global visual style.

No score is currently produced. The reviewer is implemented in
`scripts/run_vl_vv_issue_review.py` and documented in
`docs/vl-vv-issue-review-agent-v1.md`; it adds a per-candidate review while
preserving discovery fields and does not redefine discovery outputs. It has not
yet adjudicated the four-model candidate set below. Candidate counts remain
discovery-only and are not final scores.

## Current four-model experiment

Authoritative completed experiment root:

`experiments/vl_vv_multimodel_four_episode_exact_once_rerun_20260925/`

Models:

- `veo31`
- `wan22`
- `storymem`
- `holocine`

Episodes:

- `52apMIyJVlc_s00176_n6_clean_v2` (6 shots)
- `8iDEmCxXz-A_s00025_n6_clean_v2` (6 shots)
- `9ugYT3Xc59s_s00093_n4_clean_v2` (4 shots)
- `Wl6COOA3V6Y_s00022_n4_clean_v2` (4 shots)

All 16 detector + discovery cases completed. The initially failed Veo3.1
`9ugYT3Xc59s_s00093_n4_clean_v2` case was re-run after the repair-loop change
at:

`experiments/vl_vv_multimodel_four_episode_exact_once_rerun_20260925/veo31/9ugYT3Xc59s_s00093_n4_clean_v2/case_local_patch_rerun/`

Use this `case_local_patch_rerun` output instead of its older `case/` directory.
It completed successfully. Its global-match exact-once audit passed on the
initial full response with `repair_attempts: 0`; its local Shot3 clustering had
two retry directories before valid output. The issue discovery found 2 V-L,
0 within-shot V-V and 2 cross-shot V-V candidates.

The 16-case candidate-count matrix is below, in the order
`V-L / V-V within-shot / V-V cross-shot`:

| Episode | Veo3.1 | Wan2.2 | StoryMem | HoloCine |
| --- | ---: | ---: | ---: | ---: |
| `52apMIyJVlc_s00176_n6_clean_v2` | 0 / 0 / 3 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `8iDEmCxXz-A_s00025_n6_clean_v2` | 0 / 0 / 1 | 1 / 0 / 1 | 1 / 0 / 0 | 1 / 0 / 0 |
| `9ugYT3Xc59s_s00093_n4_clean_v2` | 2 / 0 / 2 | 1 / 0 / 1 | 1 / 0 / 0 | 2 / 0 / 0 |
| `Wl6COOA3V6Y_s00022_n4_clean_v2` | 1 / 0 / 3 | 1 / 0 / 0 | 2 / 0 / 0 | 0 / 0 / 0 |

Candidate totals are Veo3.1 12, Wan2.2 5, StoryMem 4 and HoloCine 3. This
supports only a provisional discovery-only ordering:

1. HoloCine
2. StoryMem
3. Wan2.2
4. Veo3.1

Do not call this a final benchmark ranking until review removes false positives
and the scoring policy has been implemented.

Per-case result is always:

`<experiment>/<model>/<episode>/case/issue_discovery/result.json`

except for the Veo3.1 special rerun above. Entity registries are adjacent as
`episode_entities.json`; global exact-once audits are in
`global_match/exact_once_audit.json`.

## Generated-video locations used by the experiment

- Veo3.1:
  `experiments/veo_generation_priority100_20260923/run02/videos/<episode>/ShotN.mp4`
- Wan2.2:
  `experiments/wan_generation_400_20260921/videos/<episode>/ShotN.mp4`
- StoryMem:
  `data/generated/storymem_200_hf/storymem_outputs/priority100_hpsv3/episodes/<episode>/shots/01_*.mp4`
- HoloCine:
  `experiments/holocine_generation_200_20260922/attempts/<episode>/*/episode.mp4`
  (split into 5-second shot windows by the preparation workflow).

## Running and resource notes

- Never run GPU work on the login node. Follow `AGENTS.md`: inspect
  `squeue -u guangyi.chen`, then revalidate GPU use, VRAM and KFD processes
  inside an existing allocation immediately before launch. Do not disturb
  HoloCine or other workloads.
- The current four-model runner is
  `experiments/vl_vv_multimodel_four_episode_20260925/run_case.sh`. It invokes
  `scripts/openai_api_env.sh` and stages detector, prompt recovery, global
  matching, DINO appearance, attachment and issue discovery.
- GPU work uses WeDetect-Anything and Grounding DINO. GPT calls are remote API
  calls; record API input, cached input, output tokens and USD estimate in run
  records. The project requires a cost alongside any reported token count.
- The current case runner uses a fresh case directory. Never overwrite a
  completed case or silently reuse artifacts with a different source hash.

## Related earlier history, deliberately not active default

The repository contains a much larger earlier geometry-based GS consistency
pipeline: Pi3X, GeoCalib, RoMA, static/motion labels, 3D registration, spatial
cosines and standalone appearance scores. It has extensive frozen decisions in
`AGENTS.md`, `research-state.yaml`, `findings.md`, `research-log.md`,
`docs/continuity.md`, and its own documents. It was used to investigate prompt
binding, recovered parking pillars, displacement signals and multi-shot
registration. Keep its source and artifacts intact, but do not silently blend
it into the new V-L/V-V agentic benchmark or alter its objectives.

The user explored removing GeoCalib and multi-shot coordinate registration, but
the main current direction moved to the four-agent, image-and-contract-driven
V-L/V-V evaluation pipeline described here. The next work should focus on
running and assessing the implemented reviewer, then designing scoring or
user-directed evaluation analysis, unless the user explicitly returns to the
geometry pipeline.

## Suggested first actions for the new conversation

1. Read `AGENTS.md`, then this handoff, and inspect the authoritative completed
   experiment root.
2. If asked to report results, read JSON results rather than relying only on
   this summary.
3. Run the implemented reviewer on the authoritative candidate set and inspect
   its per-issue verdicts before any ranking claim.
4. If asked to build scoring, make V-L and V-V separate final scores, retain
   raw reviewed events and all weighting inputs for later adjustment. Seek user
   direction before choosing severity weights or aggregation rules.
