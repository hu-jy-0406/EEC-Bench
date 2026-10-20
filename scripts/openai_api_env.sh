#!/usr/bin/env bash
# Use the independent OpenAI API transport for EEC-Bench model stages.
# This does not alter Codex CLI login or the desktop application's account.
set -euo pipefail
key_file="${EECBENCH_OPENAI_KEY_FILE:-/vast/users/guangyi.chen/causal_group/jinyuan.hu/.config/eecbench/openai.key}"
if [[ ! -s "$key_file" ]]; then
  echo "Missing or empty API key file: $key_file" >&2
  exit 2
fi
export EECBENCH_CODEX_BACKEND=api
export EECBENCH_API_MODEL="${EECBENCH_API_MODEL:-gpt-6-luna}"
export EECBENCH_OPENAI_KEY_FILE="$key_file"
exec "$@"
