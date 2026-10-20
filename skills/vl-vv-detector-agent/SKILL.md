---
name: vl-vv-detector-agent
description: Run or modify the multi-shot video detector agent from per-shot entities through prompt binding, cross-shot global identity matching, exact-once repair, and episode_entities.json export.
---

# VL/VV detector agent

Use `EECBench/scripts/run_vl_vv_detection.py`. For within-shot WeDetect
clustering, follow `EECBench/skills/wedetect-shot-entities/SKILL.md`; that skill
ends before cross-shot identity matching.

## Cross-shot identity partition

Treat every `(shot_id, local_entity_id)` pair as one indivisible candidate.
The global matcher must partition the complete frozen local inventory:

- every local candidate appears in exactly one group;
- no local candidate appears in two or more groups;
- no local candidate is omitted;
- no unknown local candidate is introduced;
- one valid group becomes one candidate global identity;
- a `confirmed` group contains the same physical entity across at least two
  shots and at most one member from each shot;
- `singleton` contains exactly one local candidate;
- `unresolved` is not merged into a confirmed global identity downstream.

State these constraints explicitly in the initial Luna request. Always run the
deterministic exact-once validator before exporting `episode_entities.json`.
Never pass an invalid partition downstream.

## Same-conversation repair loop

When exact-once validation fails, continue the original Luna Responses
conversation using `previous_response_id`. Do not start a fresh identity review.

The repair request must contain only the problematic local candidate keys and
the minimum ownership metadata needed to fix them: duplicate group indices,
missing status, or an unknown-key marker. Do not resend the complete previous
JSON, unaffected entity IDs, unaffected groups, frames, or detector payload.

Luna returns ownership decisions only for the listed problematic keys. It must
not rewrite the full partition, rename groups, change descriptions or reasons,
or move unaffected members. Apply the returned patch to the previous JSON in
code, then rerun exact-once validation. Repeat only while violations remain,
with a bounded retry limit and a complete per-attempt audit trail.

For a duplicate key, Luna selects exactly one of its existing group indices.
For a missing valid key, Luna selects one compatible existing group or creates
a new singleton. For an unknown invented key, Luna requests removal. Reject a
repair response that mentions an unlisted key, omits a listed key, repeats a
key, selects an invalid group, or proposes any other edit.

After applying a patch, remove empty groups. If removing a duplicate member
leaves a formerly confirmed group with one member, deterministically mark that
group singleton; this is structural cleanup, not a new identity judgment.
Preserve every other group field and member byte-for-byte.

Save the initial response, each repair request/response, response IDs, token
usage, validator findings, applied patch, and final passing audit. Only then
materialize `episode_entities.json` for the problem-discovery agent.
