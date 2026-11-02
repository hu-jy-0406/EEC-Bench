# coordinate_frame sentence in the V-L prompts (2026-11-01)

Owner decision: add one sentence that defines `coordinate_frame` to the V-L
prompts. Requirements carried the field, but no prompt said what its values mean,
so a model could read "his left" as the left of the image.

- `prompts/vl_vv_issue_discovery_v5_vl.txt`: added after the row list in section 2.
- `prompts/vl_vv_issue_review_v6_vl.txt`: added at the start of section 3.
- V-V prompts and the shared definitions are unchanged.

Pre-change copies with SHA-256: `source_before/`. Tests only, no live run, so the
effect on V-L detection and review is unknown. It joins the live checks of
`docs/open-questions.md` Q2.
