# Gemini setup for EntityBench / EEC-Bench

## Required model

The benchmark configuration uses `gemini-2.5-pro` for all Gemini-derived
entity, scene, style, action, and intra-shot fidelity judgments. Keep this
stable model ID when reproducing the original protocol.

## Create and store an API key

1. Open Google AI Studio's API Keys page and create an API key for the
   intended Google Cloud project. Enable billing/paid tier if the project's
   quota is not sufficient for the evaluation volume.
2. Store the key outside this repository:

   ```bash
   mkdir -p ~/.config/eecbench
   chmod 700 ~/.config/eecbench
   umask 077
   $EDITOR ~/.config/eecbench/gemini.env
   ```

3. Put only these exports in that file:

   ```bash
   export GEMINI_API_KEY='replace-with-your-key'
   export GEMINI_API_KEYS="$GEMINI_API_KEY"
   export GEMINI_OPENAI_BASE_URL='https://generativelanguage.googleapis.com/v1beta/openai/'
   ```

4. Load the secret into the current shell:

   ```bash
   source ~/.config/eecbench/gemini.env
   ```

Never paste the key into a chat, commit it, or place it under the EECBench
workspace. Multiple keys may be supplied as a comma-separated
`GEMINI_API_KEYS` value; the evaluator rotates them.

## Validate the endpoint

The `vace` environment already includes the OpenAI Python client. This check
uses Google's documented OpenAI-compatible endpoint:

```bash
/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python -c \
  'import os; from openai import OpenAI; c=OpenAI(api_key=os.environ["GEMINI_API_KEY"], base_url=os.environ["GEMINI_OPENAI_BASE_URL"]); print(c.models.retrieve("gemini-2.5-pro").id)'
```

A successful check prints `gemini-2.5-pro`. The repository also retains the
old Azure-compatible gateway path: leave `GEMINI_OPENAI_BASE_URL` unset and
set `AZURE_OPENAI_ENDPOINT` plus `GEMINI_API_KEYS` instead.

## Run modes

- Before the key is configured, `--pillars 2,3 --non_vlm_only` runs only
  GroundingDINO+CLIP presence, DINOv2 cross-shot/transition metrics, and gap
  decay. The manifest labels this as incomplete and Gemini metrics remain
  absent.
- After the key is configured, omit `--non_vlm_only` for the complete Pillar
  2/3 evaluation.
- On this AMD/ROCm cluster, set `GDINO_MSDA_BACKEND=pytorch`; this selects
  GroundingDINO's bundled PyTorch deformable-attention implementation and is
  recorded in `run_manifest.json`.

Use the project runner as the template for local checkpoint paths and Slurm
GPU isolation:
`experiments/entitybench-wan21-smoke/run_non_vlm_in_allocation.sh`.
