#!/usr/bin/env bash
# Use OpenRouter for UEC-Bench model stages (owner, 2026-11-11): same API transport as openai_api_env.sh, sent to
# OpenRouter's Responses endpoint with model "openai/<model>", routed only to OpenAI (scripts/eec_api_codex_shim.py).
# The key is a single line in the key file below; it is never printed, logged or put on a command line.
#   scripts/openrouter_env.sh <command> [args...]     run one command with the OpenRouter backend
#   scripts/openai_api_env.sh <command> [args...]     direct OpenAI, unchanged
set -euo pipefail
key_file="${EECBENCH_OPENROUTER_KEY_FILE:-/vast/users/guangyi.chen/causal_group/jinyuan.hu/.config/eecbench/openrouter.key}"
if [[ ! -s "$key_file" ]]; then
  echo "Missing or empty OpenRouter key file: $key_file" >&2
  exit 2
fi
export EECBENCH_CODEX_BACKEND=api
export EECBENCH_API_PROVIDER=openrouter
export EECBENCH_API_MODEL="${EECBENCH_API_MODEL:-gpt-6-luna}"
export EECBENCH_OPENROUTER_KEY_FILE="$key_file"
exec "$@"
