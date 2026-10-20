# Shot assets

Status: complete. Verification and generation timing enabled.

- `assets/`: two background PNGs, one character PNG, two cup PNGs, and their exact prompts.
- `shot_1/`, `shot_2/`, `shot_3/`: accepted opening/ending PNGs, exact image-control prompts, and standalone English video prompts. Durations: 10, 6, and 14 seconds.
- `pipeline.json`: identities, world/image relationships, intentional cup discontinuity, assumptions, hashes, actual reference inputs, visual reviews and sequence review. All paths are relative.
- `reviews/`: archived candidates and exact prompts. `sequence_preview/` contains review-only JPEG previews; canonical PNGs are unchanged.
- `generation_timing.jsonl`: actual awaited built-in image-tool timings, including the rejected six-reference call.
- `verification_report.json`: passing integrity and completion checks. Recheck with `python3 verify_project.py` (requires Pillow).

All six scene PNGs are 1672 x 941, the built-in tool’s native landscape output, within one pixel of exact 16:9. No canonical cropping or resizing was used. Minor incidental texture differences are accepted under the skill’s continuity tolerance. The final close foreground composition crops the woman’s lower legs and top of hair while showing the required standing drinking action. No video was rendered.
