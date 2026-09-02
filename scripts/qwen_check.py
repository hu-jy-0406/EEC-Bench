#!/usr/bin/env python3
"""Secret-safe endpoint and credential check for the Qwen judge."""

import os
import sys
from urllib.parse import urlsplit

from openai import APIConnectionError, APIStatusError, OpenAI


def _cause_names(exc: BaseException) -> list[str]:
    names: list[str] = []
    current: BaseException | None = exc
    while current is not None:
        names.append(type(current).__name__)
        current = current.__cause__
    return names


def main() -> int:
    api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    base_url = os.environ.get("EECBENCH_VLM_BASE_URL", "")
    model = os.environ.get("EECBENCH_VLM_MODEL", "qwen3-vl-flash")
    host = urlsplit(base_url).hostname or "the configured Qwen endpoint"
    if not api_key or not base_url:
        print("qwen check: API key or Base URL was not loaded", file=sys.stderr)
        return 2

    try:
        response = OpenAI(api_key=api_key, base_url=base_url, max_retries=0, timeout=20).chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": 'Return only this JSON object: {"status": "ok"}'}],
            response_format={"type": "json_object"},
            max_tokens=32,
            extra_body={"enable_thinking": False},
        )
    except APIConnectionError as exc:
        causes = _cause_names(exc)
        if "ProxyError" in causes:
            print(f"qwen check: the cluster proxy denied or failed HTTPS CONNECT to {host}:443", file=sys.stderr)
            print("The request did not reach Alibaba Cloud; the API key and model were not tested.", file=sys.stderr)
            print(f"Ask the cluster network administrator to allow outbound HTTPS CONNECT to {host}:443.", file=sys.stderr)
            return 3
        print(f"qwen check: could not connect to {host}; the API key was not tested (cause chain: {' -> '.join(causes)})", file=sys.stderr)
        return 3
    except APIStatusError as exc:
        print(f"qwen check: Alibaba Cloud returned HTTP {exc.status_code}; check that the key and endpoint are from the same region and that qwen3-vl-flash is enabled.", file=sys.stderr)
        return 4

    print(response.model, response.choices[0].message.content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
