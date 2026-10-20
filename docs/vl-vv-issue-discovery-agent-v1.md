# VL/VV issue-discovery agent v1

> Superseded as the default on 2026-10-04 by discovery protocol v2 (checklist,
> continuity ledger, shot-transition checks, non-exclusive V-L/V-V labels):
> see `docs/vl-vv-issue-taxonomy-checklist-v2.md`. This v1 protocol remains
> available with `run_vl_vv_issue_discovery.py --protocol v1` and is the
> protocol of all first-200 multimodel results.

This is the second stage of the redesigned evaluator. It proposes candidate
problems for a later review agent; it does not make final judgments or produce
a score.

Operator skill: `EECBench/skills/vl-vv-issue-discovery-agent/SKILL.md`. The
runner sends `EECBench/prompts/vl_vv_issue_discovery_v1.txt` to Luna; keep its
candidate-family list synchronized with the skill.

## Inputs

The agent receives one frozen detection case:

- all six original keyframes for every shot, in chronological attachment order;
- the complete original `contract.json`, including `prompt`, entity schedule,
  entity descriptions, and claims;
- the complete prior-stage `episode_entities.json`, including prompt-bound and
  prompt-unbound records, per-frame boxes and DINO appearance output.

The call records the exact input, source hashes, request, raw response, schema,
and token usage under the output directory. No upstream JSON is mutated. The
complete ledger is passed verbatim; DINO values are clues, never an automatic
inconsistency decision.

## Output

`result.json` contains:

- `v_l_inconsistencies`: video-language candidates;
- `v_v_inconsistencies.within_shot`: internal shot candidates;
- `v_v_inconsistencies.cross_shot`: candidates across shots;
- per-candidate binary `kind`: `entity_self` or `entity_relation`;
- a subcategory, concise Chinese description, frozen global entity IDs,
  shot/frame evidence, literal prompt/contract evidence when v-l applies, and
  a qualitative confidence;
- model token usage and a separate standard-API USD estimate.

The schema rejects invented entity IDs and frame references, duplicates, an
entity/self-versus-relation category mismatch, v-l candidates without a prompt
quote, within-shot evidence that crosses shots, and cross-shot candidates
without two-shot evidence. It intentionally permits a visual-style candidate
without an entity ID.

## Candidate scope

The supplied prompt asks the model to inspect entity properties (appearance,
presence, visual style) and entity relations (space and interaction). It calls
out prompt-required entities/attributes, counts and instance duplication or
replacement, appearance and object-state changes, entity presence, recurring
room layout and distinctive set dressing, scene style, character-object
assignment and handoff, prompt-established action order/continuity, and
relative spatial arrangements. These are candidate families, not automatic
errors: the same entity/setting or required count must be established, and a
supported action or transition can explain change. Use the closest existing
schema subcategory; no new category was added.

Camera reframing, visibility gaps, plausible actions, occlusion, offscreen
objects, and detector misses alone are not candidates. The detector ledger is
a clue, not proof. The current six-keyframe input also limits detection of
short-lived events between sampled frames; do not claim that prompt edits alone
cover such events.

## Invocation

The API transport is mandatory for this stage and does not alter the Codex CLI
login used by the desktop conversation:

```bash
EECBench/scripts/openai_api_env.sh \
  /vast/users/guangyi.chen/anaconda3/bin/python \
  EECBench/scripts/run_vl_vv_issue_discovery.py \
  --case /abs/completed-detection-case \
  --output /abs/fresh-issue-discovery-output
```

`--model gpt-6-luna --reasoning low` is the fixed default. The lower-level
transport retains its CLI path for other legacy stages, but this agent refuses
to run unless the configured API-key transport is active.
