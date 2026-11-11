#!/usr/bin/env bash
# Load the private Gemini key kept outside the repository.
#
# Interactive shell:
#   source scripts/gemini_env.sh
#
# One scoped command (also suitable for automation):
#   scripts/gemini_env.sh command [args...]
#
# Endpoint check:
#   scripts/gemini_env.sh --check

_eecbench_gemini_fail() {
    printf 'gemini_env.sh: %s\n' "$1" >&2
}

_eecbench_loader_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
_eecbench_owner_dir="$(cd -- "${_eecbench_loader_dir}/../../.." && pwd)"
_eecbench_key_file="${EECBENCH_GEMINI_KEY_FILE:-${_eecbench_owner_dir}/.config/eecbench/gemini.key}"

if [[ ! -f "${_eecbench_key_file}" ]]; then
    _eecbench_gemini_fail "key file not found: ${_eecbench_key_file}"
    return 1 2>/dev/null || exit 1
fi

GEMINI_API_KEY=''
IFS= read -r GEMINI_API_KEY < "${_eecbench_key_file}" || true
GEMINI_API_KEY="${GEMINI_API_KEY%$'\r'}"

if [[ -z "${GEMINI_API_KEY}" ]]; then
    _eecbench_gemini_fail "key file is empty; open it in Vim and paste only the API key on the first line"
    return 1 2>/dev/null || exit 1
fi

export GEMINI_API_KEY
export GEMINI_API_KEYS="${GEMINI_API_KEY}"
export GEMINI_OPENAI_BASE_URL='https://generativelanguage.googleapis.com/v1beta/openai/'
export EECBENCH_VLM_API_KEYS="${GEMINI_API_KEY}"
export EECBENCH_VLM_BASE_URL="${GEMINI_OPENAI_BASE_URL}"
export EECBENCH_VLM_PROVIDER='google-gemini-openai-compatible'
export EECBENCH_VLM_MODEL="${EECBENCH_GEMINI_MODEL:-gemini-3.1-pro-preview}"
export EECBENCH_VLM_REASONING_EFFORT="${EECBENCH_GEMINI_REASONING_EFFORT:-low}"
export EECBENCH_VLM_PER_KEY_CONCURRENCY="${EECBENCH_VLM_PER_KEY_CONCURRENCY:-3}"
export EECBENCH_VLM_BUDGET_USD="${EECBENCH_GEMINI_BUDGET_USD:-8}"
unset EECBENCH_VLM_INPUT_USD_PER_MILLION
unset EECBENCH_VLM_OUTPUT_USD_PER_MILLION
unset DASHSCOPE_API_KEY

unset _eecbench_key_file _eecbench_owner_dir _eecbench_loader_dir
unset -f _eecbench_gemini_fail

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    printf 'Gemini API environment loaded for this shell.\n'
    return 0
fi

if [[ "${1:-}" == '--check' ]]; then
    exec /vast/users/guangyi.chen/anaconda3/envs/vace/bin/python -c \
        'import os; from openai import OpenAI; c=OpenAI(api_key=os.environ["GEMINI_API_KEY"], base_url=os.environ["GEMINI_OPENAI_BASE_URL"]); r=c.chat.completions.create(model=os.environ["EECBENCH_VLM_MODEL"], messages=[{"role":"user","content":"Reply exactly: OK"}], max_tokens=8, reasoning_effort="low"); print(r.model, r.choices[0].message.content)'
fi

if (( $# == 0 )); then
    printf '%s\n' \
        'Usage:' \
        '  source scripts/gemini_env.sh' \
        '  scripts/gemini_env.sh --check' \
        '  scripts/gemini_env.sh command [args...]'
    exit 0
fi

exec "$@"
