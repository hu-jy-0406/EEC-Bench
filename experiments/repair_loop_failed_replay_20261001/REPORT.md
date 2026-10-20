# Repair-loop replay of recorded VL/VV failures (2026-10-01)

Question: do the recorded validation failures of the first-200 multimodel run
resolve under the all-errors repair loop (`docs/vl-vv-validation-repair-loop-v1.md`),
and how many rounds are needed?

Method: `replay.py`. Each case starts from the exact failed production output
(round 0, not re-billed) and continues that stored API conversation with the
repair loop (max 8 rounds). Only the failing stage is replayed; downstream
stages were not rerun. Original experiment directories were read only. Run on
existing allocation 229943 (auh7-1b-gpu-317), CPU only, 6 concurrent.

## Population

21 recorded `full_pipeline_failed` events (controllers A and B):
- 18 validation failures: replayed (match 6, discovery 9, review 2, binding 1).
- 2 OpenAI API 500 server errors (p006 holocine review, p026 holocine
  discovery): transport failures, not addressed by this loop; excluded.
- 1 pre-fix failure (p004 wan21, 2026-09-28) whose directory was overwritten
  by a later success; no failed output available; excluded.

## Result

- 18/18 resolved; 0 continuation failures.
- Repair rounds: 0 rounds x1 (p003 wan21 review already passes current
  validation because of the earlier all-refutes normalization), 1 round x17.
- Round-0 error counts: 1 (x10), 2 (x3), 3 (x3), 9 (x1); all reached 0 after one round.
- New usage: 17 calls, 1,546,467 input tokens (0 cached), 15,958 output tokens;
  estimated USD 0.163 at GPT-6 Luna standard API prices (0.10/M uncached
  input, 0.01/M cached, 0.50/M output). Estimate, not a bill.

## How the model repaired (spot audit)

- Discovery `unknown global entity ID` (p073 x4): contract names
  `Character 2..7` replaced by ledger IDs `pb0002..pb0007`; issue kept.
- Discovery `witness outside scope` (x5): either out-of-scope witness removed
  (p025, p053) or scope extended to the witness shot (p056, p067 x2). Issue
  count unchanged in every discovery case; no other issue changed.
- Match `singleton` with two members: relabeled `confirmed` (p015, p057,
  p073 a03) or `unresolved` (p042). p072/p073 a06 also split one-member
  `confirmed` groups into singletons (previously a code normalization).
- Review p102: out-of-shot context evidence removed; no verdict changed.
- Binding p101: unsupported witness frame 5 removed (old code had failed three
  blind retries with this same error).

Whether each correction is semantically right (e.g. scope extension versus
witness removal, confirmed versus unresolved identity) was not human-audited.
The downstream scores for these replays were not computed.
