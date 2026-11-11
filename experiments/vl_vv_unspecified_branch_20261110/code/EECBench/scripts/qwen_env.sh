#!/usr/bin/env bash
# Load the private Alibaba Cloud Model Studio key kept outside repositories.
#
# Interactive shell:
#   source scripts/qwen_env.sh
#
# One scoped command:
#   scripts/qwen_env.sh command [args...]
#
# Real endpoint check (uses a few tokens):
#   scripts/qwen_env.sh --check

_eecbench_qwen_fail() {
    printf 'qwen_env.sh: %s\n' "$1" >&2
}

_eecbench_loader_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
_eecbench_owner_dir="$(cd -- "${_eecbench_loader_dir}/../../.." && pwd)"
_eecbench_key_file="${EECBENCH_QWEN_KEY_FILE:-${_eecbench_owner_dir}/.config/eecbench/qwen.key}"

if [[ ! -f "${_eecbench_key_file}" ]]; then
    _eecbench_qwen_fail "key file not found: ${_eecbench_key_file}"
    return 1 2>/dev/null || exit 1
fi

DASHSCOPE_API_KEY=''
IFS= read -r DASHSCOPE_API_KEY < "${_eecbench_key_file}" || true
DASHSCOPE_API_KEY="${DASHSCOPE_API_KEY%$'\r'}"

if [[ -z "${DASHSCOPE_API_KEY}" ]]; then
    _eecbench_qwen_fail "key file is empty; open it in Vim and paste only the API key on the first line"
    return 1 2>/dev/null || exit 1
fi

export DASHSCOPE_API_KEY
export EECBENCH_VLM_API_KEYS="${DASHSCOPE_API_KEY}"
export EECBENCH_VLM_BASE_URL="${EECBENCH_QWEN_BASE_URL:-https://dashscope-intl.aliyuncs.com/compatible-mode/v1}"
export EECBENCH_VLM_PROVIDER='alibaba-qwen-openai-compatible'
export EECBENCH_VLM_MODEL="${EECBENCH_QWEN_MODEL:-qwen3-vl-flash}"
export EECBENCH_VLM_INPUT_USD_PER_MILLION="${EECBENCH_QWEN_INPUT_USD_PER_MILLION:-0.05}"
export EECBENCH_VLM_OUTPUT_USD_PER_MILLION="${EECBENCH_QWEN_OUTPUT_USD_PER_MILLION:-0.4}"
export EECBENCH_VLM_PER_KEY_CONCURRENCY="${EECBENCH_VLM_PER_KEY_CONCURRENCY:-3}"
unset AZURE_OPENAI_ENDPOINT AZURE_OPENAI_API_KEY
export EECBENCH_VLM_BUDGET_USD="${EECBENCH_QWEN_BUDGET_USD:-1}"
unset GEMINI_API_KEY GEMINI_API_KEYS GEMINI_OPENAI_BASE_URL
unset EECBENCH_VLM_REASONING_EFFORT

_eecbench_qwen_check_script="${_eecbench_loader_dir}/qwen_check.py"
unset _eecbench_key_file _eecbench_owner_dir _eecbench_loader_dir
unset -f _eecbench_qwen_fail

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    printf 'Qwen API environment loaded for this shell (model=%s, budget=$%s).\n' \
        "${EECBENCH_VLM_MODEL}" "${EECBENCH_VLM_BUDGET_USD}"
    unset _eecbench_qwen_check_script
    return 0
fi

if [[ "${1:-}" == '--check' ]]; then
    exec /vast/users/guangyi.chen/anaconda3/envs/vace/bin/python \
        "${_eecbench_qwen_check_script}"
fi

if (( $# == 0 )); then
    printf '%s\n' \
        'Usage:' \
        '  source scripts/qwen_env.sh' \
        '  scripts/qwen_env.sh --check' \
        '  scripts/qwen_env.sh command [args...]'
    exit 0
fi

unset _eecbench_qwen_check_script
exec "$@"
