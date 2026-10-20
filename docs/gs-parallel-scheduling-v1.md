# GS pipeline bounded concurrency v1

2026-09-21 user request: reduce wall time, including concurrency. This changes scheduling only. `run_gs_integrated.py --consistency-protocol temporal_v2` defaults to `--schedule-profile parallel_v1`; `--schedule-profile legacy` restores the previous stage dependencies/worker counts. Runtime/model profile remains `temporal_spatial_v1`, registration remains the selected FPS32/direct method, and all decision prompts/schemas, original frames, identities and gates remain unchanged.

## Scheduling

- Four simultaneous top-level stages. Each stage reserves the maximum number of its nested API calls, with an eight-call budget **per pipeline invocation**. This is not a service-wide limit for other independent jobs.
- GPU stages remain strictly serialized and keep the prelaunch utilization/VRAM/UUID/KFD guard. CPU/API work can overlap the GPU stage.
- Geometry processes cross-shot participants before auxiliary singleton shots, retaining manifest chronology, scene identities and original frame order. Each own-shot expectation call begins after that shot's Boxer finishes; it no longer waits for every other shot's geometry. Within-shot review waits for its own expectation.
- Existing raw RoMa/initial-identity overlap remains; lifting and registration still wait for matching/anchor evidence. Identity review remains a separate, fresh context.
- Boundary presence runs alongside the two isolated local spatial observations and subsequent spatial verifier. The spatial verifier continues to wait for both own-shot observations. Final spatial scoring joins the validated presence result and applies the original joint-presence gate. Neither branch can alter the other branch's model input.
- Global entity export still waits for final identity reviews; appearance may overlap boundary evaluation, as in the previous integration.
- After canonical appearance preparation, DINO and compact-sheet/Codex branches can run independently. Codex uses five entity workers, unchanged all-appearance evidence and one call per eligible entity. No DINO result enters the Codex request.
- Appearance report waits for both branches, verifies and copies all DINO results with source hashes, then runs the unchanged v6 aggregation. No null placeholders or speculative scores are created. `--defer-dino` is an integration option, not a change to the standalone default.
- On stage failure, stop scheduling new stages, drain already-running siblings and report failure. No automatic API retries; partial results are not a successful full evaluation.

## Audits and scope

`scheduling.json`, `execution_plan.json` and `pipeline_runtime.json` record configuration, dependencies, API reservations and actual timings. The legacy Flow1 execution path is unchanged. All explicit stopping points retain their previous task scope.

Validation and measured Study3 comparison: [report](../experiments/pipeline_parallel_20260921/REPORT.md). Frozen replay validates exactly preserved model inputs, schemas, images, event gates and score aggregation; a fresh run can still exhibit normal model/detector variability and cache/latency changes. Concurrency reduces waiting; it does not promise fewer tokens, lower bills, or identical fresh-model verdicts.
