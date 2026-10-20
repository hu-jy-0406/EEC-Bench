# Study3 bounded concurrency validation — completed 2026-09-21

The complete fresh run from WeDetect finished successfully. Wall time **1674.647s (27m55s) →1398.875s (23m19s)**, a **275.772s /16.47% reduction**, or1.197× throughput for this one episode. This is two fresh runs with model/GPU/provider latency variation, not a controlled causal estimate or a general speed guarantee. A fixed-duration scheduling simulation independently estimates13.94% reduction (schedule_estimate.json).

## Implemented changes

- Four top-level stage workers with maximum nested-call reservations totaling eight API slots per invocation; actual measured peak8. GPU peak1, all10GPU stages serialized and UUID/VRAM/utilization/KFD guarded.
- Geometry runs cross-shot participants first while retaining manifest chronology. Each shot starts its independent motion classification/within review as soon as its own Boxer output is complete. Original shot isolation, frames and model settings remain.
- Boundary presence overlaps both local spatial calls and the following spatial verifier. Spatial verification still waits for both local results; final scoring still waits for validated presence and applies the original joint-presence gate.
- DINO and compact-sheet/Codex branches run independently after canonical preparation. Appearance Codex workers3→5; each entity still has one Astra/medium call with all original appearances. DINO inputs never enter model requests. Final report joins both branches and hashes/copies every DINO result; no null placeholder.
- Global registry/appearance already could overlap boundary evaluation in the previous integration; that existing overlap is retained, not claimed as new.
- Default temporal scheduling is `--schedule-profile parallel_v1`; `--schedule-profile legacy` exactly reproduces the old execution plan/worker counts. Prompts, schemas, runtime profile, registration objective/FPS32 method, scoring and early-stop scope unchanged. No extra verifier, model downgrade or automatic retry.

[Specification](../../docs/gs-parallel-scheduling-v1.md)

## Measured wall time and API use

| Metric | Previous fresh run | Parallel fresh run |
|---|---:|---:|
| Full runner wall seconds |1674.647|1398.875|
| Before aligned identity review |828.308|656.253|
| Aligned identity review stage |405.903|417.828|
| Boundary stage |437.039|324.713|
| Appearance Codex stage |325.348|214.742|
| Appearance DINO stage (guard/load included) |89.291|138.508|
| Model calls |48|48|
| Tokens |1,049,420|1,046,586|
| Input tokens |1,004,424|1,002,442|
| Cached input (subset) |19,968|60,672|
| Output tokens |44,996|44,144|
| Standard API equivalent USD |12.114328|11.685572|

Stages overlap: do not add stage durations to claim wall time. Not every stage became faster; the DINO stage was slower but its duration overlapped API work. Full runner timings exclude the outer allocation/GPU preflight and post-run audit in both runs. No workload was run on a login node; existing196093/node197, fourCPU/nice19, physicalGPU6 UUID GPU-9bd66cc06860c5b4, no new allocation.

Cost is the recorded standard Astra API equivalent, not an actual Codex bill, excluding parent chat and cluster charges. Applicable ordinary rates: USD10/1/12.5/50 per million uncached-input/cache-read/cache-write/output; per-call long-context rules retained. Cached input is not counted twice; no cache writes here. Previous run pricing verification retained; official basis https://developers.openai.com/api/docs/pricing . The small fee reduction primarily reflects cache variation, not a concurrency cost guarantee. Appearance alone:34calls/217402tokens/USD2.073868, already included. This task's new paid validation expense is exactly the new complete run; tests/frozen-response replay add0calls/0tokens/USD0.

## Quality and evidence

55 focused regression tests pass (`tests-final.log`). Scheduler tests cover bounded nested-call reservations, GPU exclusion, dependencies and draining siblings on failure. Deferred DINO tests cover missing results, changed populations and hash-pinned join. Legacy plan equality independently passes against the previous saved execution_plan.json.

Frozen Study3 replay (`frozen_validation.json`) uses the original raw model responses and verifies exact canonical boundary inputs/schemas/local prompt text and all final events/scores, including joint-presence gates. It verifies all36entities/240native appearance pixels, identical VLM wire payloads/sheets, and identical Codex/DINO scores. Directory-name metadata is excluded from per-entity equality. This is exact orchestration/aggregation validation, not fresh model agreement.

Fresh run:46local entities,36global records,10confirmed links,240appearances,34scored and2single-frame null entities. All10confirmed identity links unchanged. Known anomaly set preserved: tissue appearance, green-mug/pen-holder spatial reversal, black→ivory desk-lamp appearance (Codex25,DINO0.838022981323). All3within-shot spatial scores100; boundary spatial97.777777778 (1/45).

Fresh results are not entirely identical: side-table plants shot1/e20–shot3/e11 now form one ambiguous association (previously two unilateral records); neither is merged into a confirmed global identity. Boundary presence91.666667→92.307692 (C9/K1/U3/E16 versus C9/K1/U2/E18). One appearance entity, wooden console table ge0024, changes81.25→87.5; all other entity Codex scores unchanged. Episode Codex85.002383→85.195135; DINO exactly0.913816650903 in both. Do not interpret these stochastic fresh-run differences as algorithmic score improvement or claim every classification unchanged.

Final audit passed (`audit.json`, `scheduling_audit.json`):18original-frame hashes, all pinned source hashes,240appearance pixels, fresh frontend/geometry/DINO/model calls, unchanged prompts/settings, exact usage/cost reconciliation, every dependency barrier, GPU/API concurrency limits, and positive actual overlap for own-shot API vs next-shot geometry, DINO vs Codex, and boundary presence vs spatial calls.48calls all successful; no failed/retried inference. One initial test assertion and the legacy mock Stage interface were corrected before live inference; blocked Slurm/socket launches and intermittent local namespace-memory errors did not restart inference. Source snapshots and prior failed CPU-test logs are preserved.

All task inference and audit processes completed. Prior results untouched. Remaining wall-time bottlenecks are the single aligned-identity call and single boundary-presence call; concurrency preserves these decisions rather than splitting their evidence contexts.
