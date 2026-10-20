# VL/VV detection agent v1

This is the first stage of the new multi-shot consistency evaluator. Its sole
purpose is to create an auditable visual entity ledger; it does not decide
whether any inconsistency is an error.

## Inputs

- A manifest with exactly six chronological keyframes for every shot.
- The episode `contract.json`, including `entity_schedule` and, when available,
  `entity_descriptions`.
- A GPU only for WeDetect-Anything, targeted Grounding DINO, and DINOv2.

## Execution

1. WeDetect-Anything detects every supplied keyframe. A fresh GPT-6 Luna/low
   call independently clusters each shot detector inventory. It cannot add a
   box that WeDetect-Anything did not supply.
2. The schedule display names resolve to the stable instance IDs in
   contract.entity_descriptions. GPT-6 Luna/low assigns each shot-local cluster
   to bound or unbound. Ambiguous clusters are unbound.
3. Required schedule rows with no retained detection, or missing sampled
   frames, receive one targeted Grounding DINO run. Each prompt instance has
   its own detector query. The highest-score valid detector box for each
   instance/frame is attached directly. Other candidates remain raw rejected
   detector evidence. There is no post-recovery GPT call.
4. A separate GPT-6 Luna/low matching call partitions all shot-local entities
   across the episode. Every `(shot_id, local_entity_id)` must occur in exactly
   one group. A deterministic validator rejects duplicates, omissions and
   unknown IDs. On failure, the same Luna Responses conversation receives only
   the problematic IDs and returns a local ownership patch; unaffected groups
   and members cannot be rewritten. The patch is applied and checked again in
   a bounded loop. Only confirmed one-per-shot groups merge into a global
   entity. Ambiguous groups are retained as unresolved links. See
   `skills/vl-vv-detector-agent/SKILL.md`.
5. DINOv2 computes an independent appearance cosine for each global entity.

All GPT requests must use EECBench/scripts/openai_api_env.sh, which routes only
pipeline calls through the configured OpenAI API key. The desktop/CLI login is
not changed.

## Detection semantics

A retained box yields detector_observation observed; otherwise the schedule row
is not_detected. The detection ledger makes no separate physical-presence claim.

## Output

episode_entities.json separates prompt_bound and prompt_unbound entities. Each
occurrence retains every original candidate box, frame ID, detector provenance,
and schedule state. Recovered Grounding DINO candidates retain their own
category and never claim a WeDetect category.

## Commands

Prepare a case from an existing six-frame manifest and its contract:

```bash
EECBench/scripts/openai_api_env.sh \
  /vast/users/guangyi.chen/anaconda3/bin/python EECBench/scripts/run_vl_vv_detection.py prepare \
  --manifest /abs/keyframes.json --contract /abs/contract.json --case /abs/new-case
```

On a revalidated idle GPU inside an existing allocation, run detector, recovery,
and matching. `GPU_UUID` is the `GPU-...` UUID for the physical `GPU` index.

```bash
EECBench/scripts/openai_api_env.sh \
  /vast/users/guangyi.chen/anaconda3/bin/python EECBench/scripts/run_vl_vv_detection.py detect \
  --case /abs/new-case --gpu GPU --gpu-uuid GPU_UUID --shot-workers 3
EECBench/scripts/openai_api_env.sh \
  /vast/users/guangyi.chen/anaconda3/bin/python EECBench/scripts/run_vl_vv_detection.py match \
  --case /abs/new-case
EECBench/scripts/openai_api_env.sh \
  /vast/users/guangyi.chen/anaconda3/bin/python EECBench/scripts/run_vl_vv_detection.py dino_prepare \
  --case /abs/new-case
EECBench/scripts/openai_api_env.sh \
  /vast/users/guangyi.chen/anaconda3/bin/python EECBench/scripts/run_vl_vv_detection.py dino \
  --case /abs/new-case --gpu GPU --gpu-uuid GPU_UUID
EECBench/scripts/openai_api_env.sh \
  /vast/users/guangyi.chen/anaconda3/bin/python EECBench/scripts/run_vl_vv_detection.py attach_dino \
  --case /abs/new-case
```

The final ledger is `episode_entities.json`; the DINO-compatible view is
`global_entities/global_entities.json`. Per-shot detector and binding records
remain in `entities/` and `shot_prompt_recovery/`.

## Next stage: issue discovery

After `attach_dino`, run the independent discovery stage with the complete
ledger:

```bash
EECBench/scripts/openai_api_env.sh \
  /vast/users/guangyi.chen/anaconda3/bin/python \
  EECBench/scripts/run_vl_vv_detection.py discover_issues \
  --case /abs/completed-detection-case --issue-output /abs/fresh-issue-output
```

Its protocol is documented in `docs/vl-vv-issue-discovery-agent-v1.md`. It
creates candidates only; it does not change `episode_entities.json`.
