# Independent OpenAI API transport

Set `EECBENCH_CODEX_BACKEND=api` to route pipeline model stages through the
Responses API instead of the locally logged-in Codex CLI. The API shim sends
only the stage prompt, stage JSON payload, attached original images, requested
reasoning effort and JSON schema. It does not send Codex system instructions,
desktop-task context, local skills or tool access.

The default API model is `gpt-6-luna`; set `EECBENCH_API_MODEL` only for an
explicit alternative. The existing `cli` mode remains the default and uses the
current Codex CLI login unchanged.

Create the private key file outside the repository with owner-only permissions:

```bash
mkdir -p /vast/users/guangyi.chen/causal_group/jinyuan.hu/.config/eecbench
chmod 700 /vast/users/guangyi.chen/causal_group/jinyuan.hu/.config/eecbench
vim /vast/users/guangyi.chen/causal_group/jinyuan.hu/.config/eecbench/openai.key
chmod 600 /vast/users/guangyi.chen/causal_group/jinyuan.hu/.config/eecbench/openai.key
```

The file contains exactly the API key on one line. Do not put it in the repo,
shell history, a command argument or Codex CLI login storage.

Launch a normal pipeline command through:

```bash
EECBench/scripts/openai_api_env.sh <existing-pipeline-command>
```

Switch back by running the same command normally, or explicitly setting
`EECBENCH_CODEX_BACKEND=cli`.

## Shot/frame image labels (default since 2026-10-20)

At the owner's direction, the API shim puts a short text label immediately
before each attached image, for example `Shot3 frame 2`, using the payload's
own `shot_id` and `frame_id`. Pixels, attachment order, prompts and the
payload's `image_order` are unchanged. Before this, the model received 24–48
unlabeled images after the prompt and had to count positions, and it
attributed images to the wrong shot (#002 Wan2.1: Shot3's collared shirt was
reported in Shot4 in every unlabeled run).

- Where: `run_wedetect_shot_entities.image_labels()` builds the labels;
  `gs_prompt_binding.call()` (every VL/VV stage that attaches keyframes:
  shot prompt binding, global entity matching, discovery, review) and the
  shot-clustering review pass them to the shim as `--image-label` arguments.
  Scoring stages attach no images.
- Labels are sent for every API call that attaches images. Since 2026-10-21
  (owner: labels on for all detection and evaluation runs) an attached image
  without `shot_id`/`frame_id` is an error, not a silent fallback to unlabeled
  images. The Codex CLI backend (`cli`) cannot interleave text with images
  and is unchanged; every VL/VV stage requires the API backend.
- Each call's `request.json` and `api_request.json` record `image_labels`
  (and `image_label_protocol: shot_frame_v1`); `run_vl_vv_pipeline.py`
  records the setting in `run.json` and hashes the transport files.
- `EECBENCH_IMAGE_LABELS=off` sends unlabeled images, only to reproduce
  historical results; `run_vl_vv_pipeline.py` (and therefore the batch
  controller) refuses it unless `--allow-unlabeled-images` is passed, which
  is recorded in the run plan. A stored shot-clustering response is reused
  only if it was made with the same labels.
- Tests: `tests/test_image_labels.py`. Live check:
  `experiments/vl_vv_image_labels_20261020/REPORT.md`.
