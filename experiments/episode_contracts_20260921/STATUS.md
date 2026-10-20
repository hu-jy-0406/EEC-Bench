# Complete — Full400 delivered

All 400 episodes / 2,000 shots have independently reviewed primary contracts
with entity_descriptions, entity_schedule and claims. Totals: 7,425 entity
records and 64,724 claims. Source/quote/reference/dependency/coverage,
evaluator adapters, actual review responses and all queue subsets passed
full independent validation. The 17,350,429-byte archive has 1,217 entries
and passed archive integrity verification; final deliverable hashes recorded.

- Primary files: deliverables/episodes/<episode_id>/contract.json.
- Existing evaluator: adjacent alignment_contract.json; identical claims.
- Browse: deliverables/review.html; inventory: deliverables/index.json.
- Bundle: contracts_400_bundle.zip; see contracts_400_bundle.zip.sha256.
- Reports: REPORT.md, independent_validation.json, package_validation.json.
- All generation, review, rebuild, monitor, export, audit and packaging
  sessions are terminal. No task model request remains. No rerun is needed.
- Source corrections: three user-authorized current prompt revisions are
  synchronized; each affected contract received fresh independent review.
  No semantic explanation was inserted in final prompts/contracts.
- Match generation versions using source_revision.json. The three affected
  older model-specific adaptations need refresh before generation/evaluation
  against this source version. Other tasks' live generation was not modified.
- 63 source ambiguity notes remain explicit uncertainty. Model review and
  mechanical validation are not independent human annotation.
- All attempts: 848 model calls; 21,231,651 recorded tokens; known standard
  API equivalent subtotal USD 507.201030. Full cost unavailable because two
  timed-out attempts lack completed usage. Actual bill unavailable. Pricing:
  recorded verified 2026-09-20 Astra USD/M uncached input10, cached input1,
  output50; cached input is a subset, not double-counted.
- CPU/API only on existing allocation206117/node306, CPUs60–63/nice10,
  GPUs hidden. Main workers64; measured maximum overlapping calls65.

## Historical progress notes — superseded by completion above

# Running — not delivered yet

Requested Full400 contract compilation is active. Primary source is the original
400-episode priority queue, not source video facts or Wan-specific additions.
All prompts stay byte-exact in saved input.json files.

- Pilot coordinator: exec session37907, node auh7-1b-gpu-306, initial PID3983889;
  3 isolated episode jobs (first4/6/8-shot examples).
- Main coordinator: exec session44329, same existing allocation206117/node306;
  `run.py run --skip-pilot --workers 32`, CPU60–63/nice10, GPUs hidden.
- Main and pilot episode sets are disjoint. Do not launch another overlapping
  coordinator. Verify process identity/state before any recovery.
- `monitor.py` shows saved progress. `run.py usage` reconciles all attempts.
- After all calls finish, rerun only unfinished items with the fixed runner,
  then `run.py export`, then `audit_delivery.py`, followed by final report.

11 preflight checks pass, including original Study3 79-claim compatibility.
First6-shot pilot completed independent semantic review with specific fixes.
Other work remains active; no claim of400 completed contracts.

Initial pilot validator mistakenly rejected a completed4-shot draft solely
for two source-ambiguity notes and launched draft_2. This is corrected in the
main runner: grounded ambiguity is preserved and audited, not forced to a
particular interpretation. The original response, rejection and all usage
remain. The already-running pilot uses its initial code; reconcile its final
records after it exits. There is no production evaluator/gate change.

## User-requested acceleration update

Pilot session37907 is terminal. Pilot ambiguity reconciliation session89587 has
finished or is being closed; verify its result before final delivery.
Original main PID3988866/session44329 was sent SIGINT ONLY at the coordinator:
verified Executor.map cancellation drains active jobs and cancels queued futures
(test_drain.py passed4active/26queued/0child interruption). It is now draining,
not a second queue owner. Original runtime is preserved as runtime_32.json.

New main session5908: run.py run --skip-pilot --only-unstarted --scale --workers64.
It selected only episodes with no calls directory, so it is disjoint from every
old started episode. New API capacity starts32 while old<=32 drains, then expands
to64 only after the recorded old PID/startticks terminate. scaling.json and
scaling_released.json record this. Never independently restart an overlapping
coordinator while either is active. Aggregate actual calls across all phases.

## Latest quality/status checkpoint

103/400 final contracts were saved at the checkpoint; see progress.json for
live counts. Full64 capacity was still awaiting old32 coordinator drain.
Pilot ambiguity reconciliation has completed with both original ambiguity
notes retained. Repeated quote failures were audited against original text;
exact-quote validation remains strict.

A source conflict was found in5IykypzJT80_s00027_n6_clean_v2/Shot2:
handgun arrives until temple contact, versus temple contact throughout the
whole shot. A user clarification is pending: preserve both readings and
withhold conflicted claims from scoring, or explicitly adopt the sequential
contextual interpretation. Do not silently mark this episode conflict-free.
Other episodes continue independently. Contract construction is still active.

Report generator now permits truly unavailable call usage: report known
subtotal and missing-cost records, never fabricate zero for failed calls.

## Source revision authorized and applied

The user directed that genuinely contradictory source prompts be corrected
directly according to context, without adding interpretation justifications.
This supersedes the prior pending question and unchanged-source constraint.
The warehouse episode Shot2 source correction is synchronized into the current
extraction, both source candidate files, priority subsets/queue, browser text,
and current contract input/manifest. Queue order and population are unchanged.
Fresh independent reconstruction is running as exec session83618.
Historical model outputs and usage are retained. No explanation is added to
the final prompt or contract. Other ambiguous identities are not contradictions
and must not be silently forced into invented matches.

## Main64 fully enabled

The final old32 episode u_4L7Dx1rIg_s00001_n6_clean_v2 completed
with316claims. Old coordinator session44329 then exited after the previously
requested graceful SIGINT; its KeyboardInterrupt is expected. No active API
request was killed. Main session5908 emitted api_capacity_increased/workers64.
The optional tail-adoption preflight passed, but handoff_tail.py exited without
action because the old coordinator was already terminal.
Source-prompt reconstruction remains session83618. The priority dataset
independent validation passed all57checks after the source correction.

Source revision reconstruction session83618 completed successfully:185claims,
19entities; both compilation and independent review used the corrected source.
The extra reconstruction process is terminal. A partial independent audit of
180completed contracts also passed current-source/review-input equivalence.

## Two additional global summaries synchronized

User-authorized source synchronization also updated the global prompts of
8TM2yB381fc_s00037_n4_clean_v2 and jS4vMlzOaTI_s00013_n8_clean_v2.
The complete source-revision list is now3episodes in source_revision.json.
Original shot text for these2episodes is retained. Fresh isolated reconstruction
sessions:41140(ship,4shots) and68127(arcade,8shots). Historical results remain
under each episode revisions/pre_source_v2. No interpretation basis is added
to final prompt or contract. Current queue validation session71636.

## Tail checkpoint

398/400 current contracts are complete. Only the2source_v2 reconstructions
remain (sessions41140 and68127); main batch has finished its episode work.
Latest source/queue hashes are in manifest.json and source_revision.json;
priority validation again passed57/57 after all3source edits.
Final checks must use current accepted review inputs, not historical matches.
Known failed request ledgers contain complete usage for4of6failed calls;2
timeouts have no completed usage record and must remain cost-unavailable.
