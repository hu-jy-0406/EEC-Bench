#!/usr/bin/env python3
"""Create Veo-specific prompts with only the five-second wording changed to six seconds."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


PATTERN = re.compile(r"(?<![A-Za-z0-9])(?:five|5)([ -])second(s)?(?![A-Za-z0-9])", re.IGNORECASE)


def convert(text: str) -> tuple[str, int]:
    def replacement(match: re.Match[str]) -> str:
        separator = match.group(1)
        plural = match.group(2) or ""
        original = match.group(0)
        number = "Six" if original[:1].isupper() else "six"
        return f"{number}{separator}second{plural}"

    return PATTERN.subn(replacement, text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    rows = []
    total_replacements = 0
    prompt_count = 0
    for line in args.input.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        for shot in row.get("shots", []):
            if "generation_prompt_en" not in shot:
                raise ValueError(f"missing generation_prompt_en in {row.get('episode_id')} {shot.get('shot_id')}")
            prompt_count += 1
            converted, count = convert(shot["generation_prompt_en"])
            shot["generation_prompt_en_veo_6s"] = converted
            shot["veo_prompt_transform"] = {
                "source_field": "generation_prompt_en",
                "rule": "replace only five/5-second wording with six/six-second wording",
                "replacement_count": count,
            }
            total_replacements += count
        rows.append(row)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n")

    print(json.dumps({
        "episodes": len(rows),
        "shot_prompts": prompt_count,
        "replacements": total_replacements,
        "input": str(args.input),
        "output": str(args.output),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
