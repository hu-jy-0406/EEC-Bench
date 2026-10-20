# Full400 episode contract construction

Inputs are the current authoritative Full400 shared source prompts in the priority queue:
`source_video_priority_20260921/generation_queue_400.jsonl`.
The identical current records are in
`source_video_400_20260920/deliverables/candidates_400.jsonl`.
Model-specific Wan context additions are separate; these contracts describe the
shared original episode text, including its global and cross-shot context.

One isolated configured Astra/medium draft and one fresh-context independent
Astra/medium semantic audit per episode. Only exact global/per-shot text and
mechanically split source units enter model calls. The auditor can repair
specific entities, schedule rows, claims and coverage via an explicit patch.
All raw attempts are retained. Mechanical-invalid replies can receive bounded
correction attempts; errors never authorize dropping legitimate requirements.
User-authorized source corrections are synchronized across current source files and queues before fresh contract compilation/review. Final prompts and contracts do not add interpretation justifications. Unspecified identity relationships remain uncertain.

Outputs: per-episode `entity_descriptions`, `entity_schedule`, four-dimensional
`claims`, original text, source coverage and hashes. No extra scene_id.
EntityBench's places reference the same registered physical location when the
text supports recurrence. Schedule omission is not a negative requirement.
Every positive scheduled entity gets exactly one presence claim. Other claims
retain applicable presence dependencies and exact original quotes.

The old evaluator-format derivative is deterministic and checked by
`gs_prompt_alignment.validate_contract`; it does not change judgments, model
settings, scoring or historical outputs. It supplies prompt alignment input;
it does not solve arbitrary multi-shot geometry registration support.

Validation: 4/6/8-shot pilot; targeted Study3 compatibility and negative structural
fixtures; full independent per-episode text review; full on-disk source, quote,
reference, dependency, coverage, compatibility, subset-order and cost audit.
Model review plus structural checks cannot formally prove natural-language
semantic equivalence, and is not independent human annotation.

Resource policy: CPU/API only on a checked existing owned Slurm compute node,
GPUs hidden, bounded concurrency, low-priority CPU affinity. No new allocation.
All actual calls, including failed/invalid responses, enter cost accounting.
Pricing is the project's recorded 2026-09-20 verified Astra standard API
schedule, explicitly an estimate rather than actual billed charges; unknown
billing or unsupported usage is marked unavailable. No parent-chat/GPU costs.
