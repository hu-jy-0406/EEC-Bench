# VL/VV validation repair loop v1 (2026-10-01, explicit user direction)

The user directed that every model stage loop on ALL validation problems, not
only exact-once ownership: report every detected problem to the model, let it
fix all of them, re-validate the corrected output from scratch, report any
remaining or new problems, and repeat.

## Mechanism

`scripts/vl_vv_repair_loop.py::call_with_repair`

- Errors = every JSON-schema violation (with path) plus every semantic
  violation from the stage's collector. Collectors no longer stop at the first
  problem; the raising `validate_*` wrappers are kept for other callers.
- Repair turn continues the same conversation (`previous_response_id`) with
  `prompts/vl_vv_validation_repair_v1.txt`, sending `validation_errors` and the
  complete `previous_output`; output schema unchanged. Without a response ID
  the original prompt, input and images are resent.
- At most 8 repair rounds, then the stage fails with the remaining errors.
- Audit: `<call>_repair_audit.json` (every round's errors and usage); repair
  calls are sibling folders `<call>_repair_NN`. Usage includes every round.
- Validation gates, original task prompts and pre-existing deterministic
  normalizations are unchanged; no output is repaired in code by this loop.

## Stages

| Stage | Before | Now |
|---|---|---|
| Shot clustering (`run_wedetect_shot_entities.py`) | fresh retries only for two exact-once messages | fresh retries for any validation failure of a completed model turn; correction lists missing/duplicate IDs plus schema, empty-name, empty-reason and out-of-range-ID problems (existing 12-round isolated design kept) |
| Shot prompt binding (`gs_shot_prompt_recovery.py`) | up to 3 blind fresh calls | all-errors loop; blind restart only for transport failures |
| Global matching (`run_vl_vv_detection.py match`) | patch loop for ownership only; singleton/confirmed label errors aborted | all `exact_once_errors` (ownership + identity labels) in one loop, full corrected output |
| Issue discovery | no retry | all-errors loop |
| Issue review | no retry | all-errors loop (frame-reference and all-refutes normalizations kept) |
| Episode scoring | no retry | all-errors loop |

Behavior change: matching outputs that the old code silently normalized (for
example a one-member `confirmed` group) are now first reported to the model;
the existing normalization still runs afterwards.

## Validation

`tests/test_vl_vv_repair_loop.py` (fake transport, no API). Offline replay of
the real priority-73 failures produced the messages the model would receive.
No live API run of the loop yet. The nine failures in
`tests/test_shot_prompt_recovery.py` predate this change (they reference the
removed `materialize_review`/`review_schema` of the older recovery protocol).

## Transient transport retry (2026-10-01, explicit user direction)

`run_wedetect_shot_entities.py::run_process` (the single transport used by
every model stage) retries a failed API-shim call up to 3 times (10/30/60 s)
when stderr shows a transient transport error: OpenAI API 429 or 5xx, or a
dropped/refused connection. 4xx client errors, whole-call timeouts and non-API
processes are not retried. Failed attempts' logs are kept as
`*.transport_failedN`. Tests: `tests/test_transport_retry.py`.
